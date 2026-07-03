"""Email report preview and send screen for the Textual TUI."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Label, RichLog, Select, Static

from ...gui_backend import (
    load_profiles,
    load_setup_paths,
    run_email_dry_run,
    send_email_report,
)


class EmailReportView(VerticalScroll):
    """Dry-run preview and send for email reports."""

    def compose(self) -> ComposeResult:
        yield Static("Email Report", classes="SectionTitle")
        with Horizontal(classes="FormRow"):
            yield Label("Profile:")
            yield Select([], id="profile-select")
        with Horizontal():
            yield Button("Preview (dry-run)", id="preview-btn", variant="primary")
            yield Button("Send Email", id="send-btn", variant="warning")
        yield Static("Preview", classes="SectionTitle")
        yield RichLog(id="email-preview", highlight=True, markup=False)

    def on_mount(self) -> None:
        self._paths = load_setup_paths()
        self._reload_profiles()

    def _reload_profiles(self) -> None:
        config = load_profiles(self._paths)
        names = [p["name"] for p in config.get("profiles", [])]
        select = self.query_one("#profile-select", Select)
        select.set_options([(n, n) for n in names])
        if names:
            select.value = names[0]

    def _profile_name(self) -> str:
        value = self.query_one("#profile-select", Select).value
        return str(value)

    @on(Button.Pressed, "#preview-btn")
    def _preview(self) -> None:
        self._run_preview()

    @work(thread=True)
    def _run_preview(self) -> None:
        preview = self.query_one("#email-preview", RichLog)
        self.call_from_thread(preview.clear)
        self.call_from_thread(preview.write, "Generating dry-run preview…")
        code, body = run_email_dry_run(self._paths, self._profile_name())
        self.call_from_thread(self._show_preview, code, body)

    def _show_preview(self, code: int, body: str) -> None:
        preview = self.query_one("#email-preview", RichLog)
        preview.clear()
        if body.strip():
            preview.write(body.rstrip())
        if code == 0:
            preview.write("\n--- Preview complete (not sent) ---")
        else:
            preview.write("\n[Preview failed — check configuration and secrets]")

    @on(Button.Pressed, "#send-btn")
    def _send(self) -> None:
        self._run_send()

    @work(thread=True)
    def _run_send(self) -> None:
        preview = self.query_one("#email-preview", RichLog)
        self.call_from_thread(preview.write, "Sending email report…")
        code, message = send_email_report(self._paths, self._profile_name())
        self.call_from_thread(self._show_send_result, code, message)

    def _show_send_result(self, code: int, message: str) -> None:
        preview = self.query_one("#email-preview", RichLog)
        if code == 0:
            preview.write(f"[Sent] {message}")
        else:
            preview.write(message.rstrip())
