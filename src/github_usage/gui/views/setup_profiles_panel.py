"""Profile selection, report options, and save for the Setup screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from ...gui_backend import add_profile, delete_profile, load_profiles, save_profiles
from ..errors import format_error
from ..layout import FormGrid
from ..log_utils import write_log
from ..modals import ConfirmScreen

if TYPE_CHECKING:
    from .setup_view import SetupView


# Repeated selector/label literals, hoisted to satisfy S1192.
_ONLY_PUBLIC = "#only-public"
_ONLY_PRIVATE = "#only-private"


class SetupProfilesPanel(VerticalScroll):
    """Named profiles, report options, and save."""

    DEFAULT_CSS = """
    SetupProfilesPanel .profile-row {
        height: auto;
        margin-bottom: 1;
    }
    SetupProfilesPanel #profile-active-label {
        color: $text-muted;
        margin-left: 1;
    }
    SetupProfilesPanel .profile-field {
        margin-bottom: 1;
    }
    """

    def __init__(self, coordinator: SetupView, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._coordinator = coordinator

    def compose(self) -> ComposeResult:
        with Horizontal(classes="profile-row"):
            yield Label("Profile:")
            yield Select([], id="profile-select")
            yield Static("", id="profile-active-label")
            yield Static("", id="dirty-indicator")
            yield Button("Add", id="add-profile", variant="default")
            yield Button("Delete", id="delete-profile", variant="warning")
        yield Static(
            "[b]No profiles yet.[/b] Click Add to create one.",
            id="profiles-empty",
            classes="HelpText",
        )
        with Container(id="profiles-form", classes="profiles-form"):
            yield Static(
                "Each profile has its own report options, optional recipient override, "
                "and schedule (Schedules tab). Changes apply to the selected profile only.",
                classes="HelpText",
            )
            yield Static("Where profile options apply", classes="SectionTitle")
            yield Static(
                "· [b]Email Report[/b], [b]Verify Email Setup[/b], and [b]scheduled sends[/b] "
                "(launchd / GitHub Actions) use the options below.\n"
                "· [b]Local Full Report[/b] (main tab 2) is separate: fixed billing snapshot; "
                "it does not read these options.\n"
                "· [b]target_email[/b] overrides REPORT_EMAIL for this profile's email sends only.",
                classes="HelpText",
            )
            yield Static("Report options (config.toml)", classes="SectionTitle")
            yield Checkbox("Include forecast", id="include-forecast")
            yield Checkbox("Include top consumers", id="include-consumers")
            yield Checkbox("Include artifact storage", id="include-artifact")
            yield Checkbox("Include release assets", id="include-release")
            yield Checkbox("Only public repos", id="only-public")
            yield Checkbox("Only private repos (incl. internal)", id="only-private")
            with FormGrid():
                yield Label("Max repos", classes="field-key")
                yield Static(
                    "Repository scan limit when optional sections are enabled.",
                    classes="field-help",
                )
            yield Input(value="100", id="max-repos", classes="profile-field")
            with FormGrid():
                yield Label("target_email", classes="field-key")
                yield Static(
                    "Optional per-profile recipient. Blank uses REPORT_EMAIL from Secrets.",
                    classes="field-help",
                )
            yield Input(
                placeholder="team@example.com (optional)",
                id="target-email",
                classes="profile-field",
            )
            yield Button("Save", id="save-btn", variant="primary")

    def set_empty_state(self, empty: bool) -> None:
        """Toggle between empty-state message and the profile form."""
        self.query_one("#profiles-empty", Static).display = empty
        self.query_one("#profiles-form", Container).display = not empty

    def reload_profile_list(self, names: list[str], current: str) -> None:
        """Refresh the profile selector options and value."""
        select = self.query_one("#profile-select", Select)
        label = self.query_one("#profile-active-label", Static)
        if not names:
            select.set_options([])
            select.disabled = True
            label.update("")
            return

        select.disabled = False
        select.set_options([(name, name) for name in names])
        target = current if current in names else names[0]

        def _apply_selection() -> None:
            select.value = target
            label.update(f"Active: [b]{target}[/b]")
            if self.app.app_state.current_profile != target:  # type: ignore[attr-defined]
                self.app.app_state.set_current_profile(target, persist=False, notify=False)  # type: ignore[attr-defined]

        self.call_after_refresh(_apply_selection)

    def reload_profile_options(self, profile: dict[str, Any]) -> None:
        """Populate report-option fields for the active profile."""
        email = profile["email_report"]
        self.query_one("#include-forecast", Checkbox).value = bool(
            email.get("include_forecast", True)
        )
        self.query_one("#include-consumers", Checkbox).value = bool(email.get("include_consumers"))
        self.query_one("#include-artifact", Checkbox).value = bool(
            email.get("include_artifact_storage")
        )
        self.query_one("#include-release", Checkbox).value = bool(
            email.get("include_release_assets")
        )
        self.query_one(_ONLY_PUBLIC, Checkbox).value = bool(email.get("only_public"))
        self.query_one(_ONLY_PRIVATE, Checkbox).value = bool(email.get("only_private"))
        self.query_one("#max-repos", Input).value = str(email.get("max_repos", 100))
        self.query_one("#target-email", Input).value = profile.get("target_email", "")

    def read_profile_options(self) -> dict[str, Any]:
        """Return report-option values from the form."""
        max_repos_str = self.query_one("#max-repos", Input).value.strip() or "100"
        return {
            "include_forecast": self.query_one("#include-forecast", Checkbox).value,
            "include_consumers": self.query_one("#include-consumers", Checkbox).value,
            "include_artifact_storage": self.query_one("#include-artifact", Checkbox).value,
            "include_release_assets": self.query_one("#include-release", Checkbox).value,
            "only_public": self.query_one(_ONLY_PUBLIC, Checkbox).value,
            "only_private": self.query_one(_ONLY_PRIVATE, Checkbox).value,
            "max_repos_str": max_repos_str,
            "target_email": self.query_one("#target-email", Input).value.strip(),
        }

    def update_dirty_indicator(self, dirty: bool) -> None:
        indicator = self.query_one("#dirty-indicator", Static)
        indicator.update("[yellow]* unsaved[/yellow]" if dirty else "")

    @on(Select.Changed, "#profile-select")
    async def _on_profile_changed(self) -> None:
        if self._coordinator.is_form_loading():
            return
        new_name = self._coordinator.current_profile_name()
        previous = self._coordinator.previous_profile
        label = self.query_one("#profile-active-label", Static)
        if new_name:
            label.update(f"Active: [b]{new_name}[/b]")
        if self._coordinator.dirty and previous and new_name != previous:
            confirmed = await self.app.push_screen_wait(
                ConfirmScreen(
                    f"Switch to profile '{new_name}'? Unsaved changes will be lost.",
                    title="Unsaved changes",
                )
            )
            if not confirmed:
                select = self.query_one("#profile-select", Select)
                if previous:
                    select.value = previous
                return
        self.app.app_state.set_current_profile(new_name)  # type: ignore[attr-defined]
        self._coordinator.reload_form()

    @on(Checkbox.Changed, "#only-public, #only-private")
    def _on_visibility_filter_changed(self, event: Checkbox.Changed) -> None:
        if self._coordinator.is_form_loading():
            return
        if event.checkbox.id == "only-public" and event.value:
            self.query_one(_ONLY_PRIVATE, Checkbox).value = False
        elif event.checkbox.id == "only-private" and event.value:
            self.query_one(_ONLY_PUBLIC, Checkbox).value = False
        self._coordinator.mark_dirty()

    @on(Input.Changed)
    @on(Checkbox.Changed)
    def _on_field_changed(self) -> None:
        if self._coordinator.is_form_loading():
            return
        self._coordinator.mark_dirty()

    @on(Button.Pressed, "#save-btn")
    def _save_pressed(self) -> None:
        if self._coordinator.is_running:
            return
        self._coordinator.action_save()

    @on(Button.Pressed, "#add-profile")
    def _add_profile(self) -> None:
        if self._coordinator.is_running:
            return
        log = self._coordinator.verify_log
        paths = self.app.app_state.paths  # type: ignore[attr-defined]
        config = load_profiles(paths)
        name = f"profile{len(config.get('profiles', [])) + 1}"
        try:
            config = add_profile(config, name)
            save_profiles(paths, config)
            self.app.app_state.reload()  # type: ignore[attr-defined]
            write_log(log, f"Created profile '{name}'", level="success")
        except (ValueError, PermissionError, OSError) as exc:
            write_log(log, format_error(exc), level="error")

    @on(Button.Pressed, "#delete-profile")
    async def _delete_profile(self) -> None:
        if self._coordinator.is_running:
            return
        log = self._coordinator.verify_log
        profile_name = self._coordinator.current_profile_name()
        paths = self.app.app_state.paths  # type: ignore[attr-defined]

        config = load_profiles(paths)
        if len(config.get("profiles", [])) <= 1:
            write_log(log, "Cannot delete the only profile", level="error")
            return

        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Delete profile '{profile_name}'? This cannot be undone.",
                title="Delete profile",
            )
        )
        if not confirmed:
            return

        try:
            config = delete_profile(config, profile_name)
            save_profiles(paths, config)
            self.app.app_state.reload()  # type: ignore[attr-defined]
            write_log(log, f"Profile '{profile_name}' deleted", level="warning")
        except (ValueError, KeyError, PermissionError, OSError) as exc:
            write_log(log, format_error(exc), level="error")
