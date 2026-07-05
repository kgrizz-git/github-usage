"""Textual application entry for github-usage."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from ..gui_backend import status_summary
from .main_window import MainWindow
from .scroll_actions import run_scroll_action
from .state import AppState
from .wizard import SetupWizardScreen


class GitHubUsageApp(App):
    """Top-level Textual TUI for github-usage."""

    TITLE = "github-usage"
    theme = "monokai"  # type: ignore[assignment]
    CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("1", "show_view('setup')", "Setup"),
        ("2", "show_view('report')", "Report"),
        ("3", "show_view('email')", "Email"),
        ("4", "show_view('schedules')", "Schedules"),
        ("5", "show_view('runs')", "Runs"),
        ("k", "scroll_up_line", "Scroll up"),
        ("j", "scroll_down_line", "Scroll down"),
        ("pageup", "scroll_page_up", "Page up"),
        ("pagedown", "scroll_page_down", "Page down"),
        ("ctrl+home", "scroll_top", "Scroll top"),
        ("ctrl+end", "scroll_bottom", "Scroll end"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.app_state = AppState()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield MainWindow()
        yield Footer()

    def on_mount(self) -> None:
        self.app_state.reload()
        if self.app_state.prefs.high_contrast:
            self.add_class("-high-contrast")
        main = self.query_one(MainWindow)
        main.restore_last_view()
        self.call_after_refresh(self._maybe_offer_guided_setup)

    @work
    async def _maybe_offer_guided_setup(self) -> None:
        state = self.app_state
        if state.prefs.wizard_completed or state.prefs.dismissed_setup_wizard:
            return
        summary = status_summary(state.paths)
        if summary.get("configured"):
            return
        await self.push_screen_wait(SetupWizardScreen(first_run=True))

    def action_show_view(self, view_id: str) -> None:
        """Switch to a view by id (keyboard shortcut handler)."""
        main = self.query_one(MainWindow)
        main.action_show_view(view_id)

    def action_scroll_up_line(self) -> None:
        run_scroll_action(self, "scroll_up")

    def action_scroll_down_line(self) -> None:
        run_scroll_action(self, "scroll_down")

    def action_scroll_page_up(self) -> None:
        run_scroll_action(self, "page_up")

    def action_scroll_page_down(self) -> None:
        run_scroll_action(self, "page_down")

    def action_scroll_top(self) -> None:
        run_scroll_action(self, "scroll_home")

    def action_scroll_bottom(self) -> None:
        run_scroll_action(self, "scroll_end")
