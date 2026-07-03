"""Textual application entry for github-usage."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from .main_window import MainWindow
from .state import AppState


class GitHubUsageApp(App):
    """Top-level Textual TUI for github-usage."""

    TITLE = "github-usage"
    CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("1", "show_view('setup')", "Setup"),
        ("2", "show_view('report')", "Report"),
        ("3", "show_view('email')", "Email"),
        ("4", "show_view('schedules')", "Schedules"),
        ("5", "show_view('runs')", "Runs"),
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

    def action_show_view(self, view_id: str) -> None:
        """Switch to a view by id (keyboard shortcut handler)."""
        main = self.query_one(MainWindow)
        main.action_show_view(view_id)
