"""Keyboard scroll helpers for the Textual TUI.

Mouse wheel scrolling depends on terminal focus and emulator support. These
helpers route ``j``/``k`` and page keys to the focused scrollable widget, or
the active main view when nothing scrollable has focus.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from textual.containers import ScrollableContainer
from textual.scroll_view import ScrollView
from textual.widget import Widget

try:
    from textual.actions import SkipAction
except ImportError:  # pragma: no cover - older textual
    SkipAction = Exception  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from textual.app import App

_SCROLLABLE_TYPES = (ScrollableContainer, ScrollView)


def scroll_target(app: App) -> Widget | None:
    """Return the widget that should receive a scroll action."""
    widget: Widget | None = app.focused
    while widget is not None:
        if isinstance(widget, _SCROLLABLE_TYPES):
            return widget
        widget = widget.parent  # type: ignore[assignment]

    from .main_window import MainWindow

    try:
        main = app.query_one(MainWindow)
        view = main._current_view_widget()
    except Exception:
        return None

    if isinstance(view, _SCROLLABLE_TYPES):
        return view
    return None


def run_scroll_action(app: App, action: str) -> bool:
    """Invoke a scroll action on the resolved target. Returns True if handled."""
    target = scroll_target(app)
    if target is None:
        return False
    method = getattr(target, f"action_{action}", None)
    if method is None:
        return False
    with suppress(SkipAction):
        method()
    return True
