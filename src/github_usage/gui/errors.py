"""Actionable error messages for the Textual TUI."""

from __future__ import annotations


def format_error(exc: BaseException, *, context: str = "") -> str:
    """Map an exception to a user-facing message with next steps.

    Args:
        exc: The caught exception.
        context: Optional short label for where the error occurred.

    Returns:
        A Rich-markup string suitable for RichLog output.
    """
    prefix = f"{context}: " if context else ""
    hint = _hint_for(exc)
    message = f"[red]✗ {prefix}{exc}[/red]"
    if hint:
        message += f"\n[yellow]Hint: {hint}[/yellow]"
    return message


def format_simple(message: str, *, hint: str = "") -> str:
    """Format a plain error message with an optional hint."""
    text = f"[red]✗ {message}[/red]"
    if hint:
        text += f"\n[yellow]Hint: {hint}[/yellow]"
    return text


def _hint_for(exc: BaseException) -> str:
    """Return a contextual hint for common exception types."""
    if isinstance(exc, FileNotFoundError):
        return "Config missing. Run setup first or click Add Profile."
    if isinstance(exc, PermissionError):
        return "Cannot write config. Check file permissions for .github-usage/."
    if isinstance(exc, KeyError):
        return "Profile not found. It may have been deleted — refresh or pick another."
    if isinstance(exc, ValueError):
        return "Check the field values and try again."
    if isinstance(exc, OSError):
        return "A file operation failed. Verify disk space and permissions."
    return ""
