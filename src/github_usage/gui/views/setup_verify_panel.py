"""Verify action, status summary, and log for the Setup screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, RichLog, Static

from ...gui_backend import VerifyResult
from ..layout import ViewSection
from ..log_utils import write_log

if TYPE_CHECKING:
    from .setup_view import SetupView


class SetupVerifyPanel(VerticalScroll):
    """Dry-run verification and configuration status."""

    def __init__(self, coordinator: SetupView, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._coordinator = coordinator

    def compose(self) -> ComposeResult:
        yield ViewSection(
            "Verify email setup",
            "Runs the [b]email report[/b] pipeline end-to-end for the active profile "
            "(same command as scheduled sends, with --dry-run): reads config.toml options, "
            "loads secrets, calls GitHub, builds the email body. Nothing is mailed.\n\n"
            "[b]Not the same as Usage Report:[/b] Usage Report is a separate, older "
            "terminal-only billing summary. It ignores profile options, does not build "
            "email, and does not test Resend. Use Verify Email Setup to confirm email "
            "configuration; use Usage Report only for a quick account usage snapshot.",
        )
        yield Button("Verify Email Setup", id="verify-btn", variant="success")
        yield Static("Status", classes="SectionTitle")
        yield Static("", id="status-panel", classes="StatusPanel")
        yield RichLog(id="verify-log", highlight=True, markup=True)

    def reload_status(self, status_text: str) -> None:
        """Update the read-only status summary."""
        self.query_one("#status-panel", Static).update(status_text)

    def show_error(self, message: str) -> None:
        """Show an error in the status panel and log."""
        from ..errors import format_simple

        status = self.query_one("#status-panel", Static)
        status.update(f"[red]Error: {message}[/red]")
        log = self.query_one("#verify-log", RichLog)
        write_log(log, format_simple(message), level="error")

    def show_verify_result(self, result: VerifyResult) -> None:
        """Render dry-run verification output."""
        log = self.query_one("#verify-log", RichLog)
        if result.output.strip():
            log.write(result.output.rstrip())
        if result.exit_code == 0:
            write_log(log, "Verification passed - configuration is valid", level="success")
        else:
            write_log(log, "Verification failed", level="error")
            write_log(
                log,
                "Check that GITHUB_TOKEN and RESEND_API_KEY are set correctly",
                level="warning",
            )

    @property
    def log(self) -> RichLog:  # type: ignore[override]
        return self.query_one("#verify-log", RichLog)

    @on(Button.Pressed, "#verify-btn")
    def _verify_pressed(self) -> None:
        if self._coordinator.is_running:
            return
        self._coordinator.run_verify()
