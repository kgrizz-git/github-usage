"""Textual application entry for github-usage."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult

from .main_window import MainWindow


class GitHubUsageApp(App):
    """Top-level Textual TUI for github-usage."""

    TITLE = "github-usage"
    CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield MainWindow()
