"""Reusable layout widgets for TUI views."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import Static


class ViewSection(Vertical):
    """Title + help text block."""

    DEFAULT_CSS = """
    ViewSection {
        height: auto;
    }
    .view-title { text-style: bold; }
    .view-help { color: $text-muted; margin-bottom: 1; }
    """

    def __init__(self, title: str, help_text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._help = help_text

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="view-title")
        yield Static(self._help, classes="view-help")


class FormGrid(Grid):
    """Two-column form layout: fixed label column, flexible value column."""

    DEFAULT_CSS = """
    FormGrid {
        grid-size: 2;
        grid-columns: 16 1fr;
        grid-gutter: 0 1;
        height: auto;
        margin-bottom: 1;
    }
    """


class ViewActions(Horizontal):
    """Horizontal row for primary/secondary action buttons."""

    DEFAULT_CSS = """
    ViewActions {
        height: auto;
        margin: 1 0;
    }
    """


class ViewOutput(Container):
    """Bordered output area for tables, logs, and status panels."""

    DEFAULT_CSS = """
    ViewOutput {
        height: 1fr;
        min-height: 8;
        border: solid $primary;
        padding: 0 1;
    }
    """
