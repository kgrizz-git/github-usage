"""Secrets inputs for the Setup screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Checkbox, Input, Label, Static

from ..layout import FormGrid

if TYPE_CHECKING:
    from .setup_view import SetupView

# (widget id, env key, description, hidden by default)
SECRET_FIELDS: tuple[tuple[str, str, str, bool], ...] = (
    (
        "github-token",
        "GITHUB_TOKEN",
        "GitHub API token — billing, Actions usage, and repository metadata",
        True,
    ),
    (
        "resend-key",
        "RESEND_API_KEY",
        "Resend API key — required to send email reports",
        True,
    ),
    (
        "report-email",
        "REPORT_EMAIL",
        "Default inbox when a profile has no target_email override",
        False,
    ),
    (
        "resend-from",
        "RESEND_FROM",
        "Sender address shown to recipients (verify domain in Resend)",
        False,
    ),
)

_HIDDEN_INPUT_IDS = tuple(field_id for field_id, _, _, hidden in SECRET_FIELDS if hidden)


class SetupSecretsPanel(VerticalScroll):
    """GitHub token and Resend secrets stored in .env.email-report."""

    def __init__(self, coordinator: SetupView, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._coordinator = coordinator

    def compose(self) -> ComposeResult:
        yield Static("Secrets (.env.email-report)", classes="SectionTitle")
        yield Static(
            "Stored locally at file mode 600. Save on the Profiles tab after editing. "
            "Each value maps to an environment variable used by reports and email delivery.",
            classes="HelpText",
        )
        yield Checkbox("Show hidden values", id="show-secrets")
        for field_id, env_key, description, hidden in SECRET_FIELDS:
            with FormGrid():
                yield Label(env_key, classes="field-key")
                yield Static(description, classes="field-help")
            yield Input(id=field_id, password=hidden)

    def reload_secrets(self, secrets: dict[str, str]) -> None:
        """Populate secret fields from disk."""
        self.query_one("#github-token", Input).value = secrets.get("GITHUB_TOKEN", "")
        self.query_one("#resend-key", Input).value = secrets.get("RESEND_API_KEY", "")
        self.query_one("#report-email", Input).value = secrets.get("REPORT_EMAIL", "")
        self.query_one("#resend-from", Input).value = secrets.get("RESEND_FROM", "")

    def read_secrets(self) -> dict[str, str]:
        """Return trimmed secret values from the form."""
        return {
            "GITHUB_TOKEN": self.query_one("#github-token", Input).value.strip(),
            "RESEND_API_KEY": self.query_one("#resend-key", Input).value.strip(),
            "REPORT_EMAIL": self.query_one("#report-email", Input).value.strip(),
            "RESEND_FROM": self.query_one("#resend-from", Input).value.strip(),
        }

    def _set_hidden_fields_visible(self, visible: bool) -> None:
        """Toggle masking for API keys and tokens (not email addresses)."""
        for field_id in _HIDDEN_INPUT_IDS:
            self.query_one(f"#{field_id}", Input).password = not visible

    @on(Checkbox.Changed, "#show-secrets")
    def _toggle_secret_visibility(self, event: Checkbox.Changed) -> None:
        self._set_hidden_fields_visible(bool(event.value))

    @on(Input.Changed)
    def _on_field_changed(self) -> None:
        if self._coordinator.is_form_loading():
            return
        self._coordinator.mark_dirty()
