"""Consistent RichLog formatting for the Textual TUI."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import RichLog

_LEVEL_STYLES = {
    "error": "red",
    "warning": "yellow",
    "success": "green",
    "info": "white",
    "progress": "yellow",
    "dim": "dim",
}


def write_log(log: RichLog, message: str, level: str = "info") -> None:
    """Write a timestamped, color-coded line to a RichLog widget.

    Args:
        log: Target RichLog widget.
        message: Body text (may include Rich markup).
        level: One of error, warning, success, info, progress, dim.
    """
    style = _LEVEL_STYLES.get(level, "white")
    stamp = datetime.now().strftime("%H:%M:%S")
    if message.startswith("["):
        log.write(f"[dim]{stamp}[/dim] {message}")
    else:
        log.write(f"[dim]{stamp}[/dim] [{style}]{message}[/{style}]")


def write_error(log: RichLog, message: str, *, hint: str = "") -> None:
    """Write an error line with optional hint."""
    write_log(log, message, level="error")
    if hint:
        write_log(log, f"Hint: {hint}", level="warning")
