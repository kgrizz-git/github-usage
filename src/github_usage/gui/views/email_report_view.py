"""Email report preview and send screen for the Textual TUI."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, Label, RichLog, Select

from ...gui_backend import run_email_dry_run, send_email_report
from ..async_ops import AsyncViewMixin
from ..errors import format_error, format_simple
from ..layout import FormGrid, ViewActions, ViewOutput, ViewSection
from ..log_utils import write_log


class EmailReportView(VerticalScroll, AsyncViewMixin):
    """Dry-run preview and send for email reports."""

    BINDINGS = [
        ("ctrl+r", "preview", "Preview"),
        ("escape", "cancel_async", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield ViewSection(
            "Email Report",
            "Builds the full email report (same pipeline as scheduled sends). "
            "Preview runs a dry-run locally without sending. Send delivers via Resend "
            "to REPORT_EMAIL. For a quick config check without sending, use Setup → Verify Email Setup.",
        )
        with FormGrid():
            yield Label("Profile:")
            yield Select([], id="profile-select")
        with ViewActions():
            yield Button("Preview (dry-run)", id="preview-btn", variant="primary")
            yield Button("Send Email", id="send-btn", variant="warning")
        with ViewOutput():
            yield RichLog(id="email-preview", highlight=True, markup=True)

    def on_mount(self) -> None:
        self._is_running = False
        self._cancel_requested = False
        self._loading = True
        state = self.app.app_state
        state.add_listener(self._on_state_changed)
        self._on_state_changed()
        if state.config_error:
            self._show_error(state.config_error)

    def on_unmount(self) -> None:
        self.app.app_state.remove_listener(self._on_state_changed)

    def _on_state_changed(self) -> None:
        self._reload_profiles()

    def _show_error(self, message: str) -> None:
        preview = self.query_one("#email-preview", RichLog)
        write_log(preview, format_simple(message), level="error")

    def _finish_reload(self) -> None:
        self._loading = False

    def _reload_profiles(self) -> None:
        self._loading = True
        try:
            state = self.app.app_state
            names = list(state.profile_names)
            select = self.query_one("#profile-select", Select)
            select.set_options([(n, n) for n in names])
            if names:
                current = state.current_profile
                select.value = current if current in names else names[0]
            else:
                self._show_error("No profiles found. Create one in Setup.")
        finally:
            self.call_after_refresh(self._finish_reload)

    def _profile_name(self) -> str:
        value = self.query_one("#profile-select", Select).value
        return str(value)

    @on(Select.Changed, "#profile-select")
    def _profile_selected(self) -> None:
        if self._loading:
            return
        name = self._profile_name()
        if name == self.app.app_state.current_profile:
            return
        self.app.app_state.set_current_profile(name)

    @on(Button.Pressed, "#preview-btn")
    def _preview(self) -> None:
        if self._is_running:
            return
        self._run_preview()

    def action_preview(self) -> None:
        if not self._is_running:
            self._run_preview()

    @work(thread=True)
    def _run_preview(self) -> None:
        button = self.query_one("#preview-btn", Button)
        preview = self.query_one("#email-preview", RichLog)
        self._call_ui(
            self._begin_async,
            button,
            preview,
            running_label="Running...",
            start_message="Generating dry-run preview...",
        )

        try:
            profile = self._profile_name()
            self._call_ui(write_log, preview, f"Using profile: {profile}", level="dim")
            if self._is_cancelled():
                self._call_ui(write_log, preview, "Preview cancelled", level="warning")
                return
            self._call_ui(write_log, preview, "Fetching report data...", level="progress")

            paths = self.app.app_state.paths
            code, body = run_email_dry_run(paths, profile)
            if self._is_cancelled():
                self._call_ui(write_log, preview, "Preview cancelled", level="warning")
                return
            self._call_ui(self._show_preview, code, body)
        except Exception as exc:
            self._call_ui(
                write_log, preview, format_error(exc, context="Preview error"), level="error"
            )
        finally:
            self._call_ui(self._end_async, button, "Preview (dry-run)")

    def _show_preview(self, code: int, body: str) -> None:
        preview = self.query_one("#email-preview", RichLog)
        preview.clear()
        if body.strip():
            preview.write(body.rstrip())
        if code == 0:
            write_log(preview, "--- Preview complete (not sent) ---", level="success")
        else:
            write_log(preview, "Preview failed", level="error")
            write_log(
                preview,
                "Check GITHUB_TOKEN, RESEND_API_KEY, and REPORT_EMAIL in Setup",
                level="warning",
            )

    @on(Button.Pressed, "#send-btn")
    def _send(self) -> None:
        if self._is_running:
            return
        self._run_send()

    @work(thread=True)
    def _run_send(self) -> None:
        button = self.query_one("#send-btn", Button)
        preview = self.query_one("#email-preview", RichLog)
        self._call_ui(
            self._begin_async,
            button,
            preview,
            running_label="Sending...",
            start_message="Sending email report...",
        )

        try:
            profile = self._profile_name()
            self._call_ui(write_log, preview, f"Using profile: {profile}", level="dim")
            if self._is_cancelled():
                self._call_ui(write_log, preview, "Send cancelled", level="warning")
                return

            paths = self.app.app_state.paths
            code, message = send_email_report(paths, profile)
            if self._is_cancelled():
                self._call_ui(write_log, preview, "Send cancelled", level="warning")
                return
            self._call_ui(self._show_send_result, code, message)
        except Exception as exc:
            self._call_ui(
                write_log, preview, format_error(exc, context="Send error"), level="error"
            )
        finally:
            self._call_ui(self._end_async, button, "Send Email")

    def _show_send_result(self, code: int, message: str) -> None:
        preview = self.query_one("#email-preview", RichLog)
        if code == 0:
            write_log(preview, message, level="success")
        else:
            write_log(preview, message.rstrip(), level="error")
            write_log(
                preview,
                "Verify RESEND_API_KEY and REPORT_EMAIL are configured correctly",
                level="warning",
            )
