"""Background worker helpers for the Textual TUI."""

from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from typing import TypeVar

T = TypeVar("T")


def capture_output(func: Callable[[], T]) -> tuple[T, str]:
    """Run ``func`` with stdout/stderr captured; return ``(result, combined_output)``."""
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = func()
    return result, buffer.getvalue()
