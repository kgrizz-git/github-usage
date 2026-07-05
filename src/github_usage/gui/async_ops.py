"""Shared async-operation helpers for Textual views."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.widgets import Button, RichLog

from .log_utils import write_log


class AsyncViewMixin:
    """Mixin providing loading-state and cancellation helpers for @work views.

    Host widgets should set ``_is_running`` and ``_cancel_requested`` in
    ``on_mount``.  Include ``("escape", "cancel_async", "Cancel")`` in
    BINDINGS to allow Escape to abort in-flight work.
    """

    _is_running: bool
    _cancel_requested: bool

    def _call_ui(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Schedule ``callback`` on the main UI thread from a ``@work`` worker."""
        self.app.call_from_thread(callback, *args, **kwargs)  # type: ignore[attr-defined]

    def _set_button_state(self, button: Button, disabled: bool, label: str) -> None:
        """Update a button label/disabled state from the main thread."""
        button.disabled = disabled
        button.label = label

    def _begin_async(
        self,
        button: Button,
        log: RichLog,
        *,
        running_label: str,
        start_message: str,
    ) -> None:
        """Mark work as running and update the triggering button."""
        self._is_running = True
        self._cancel_requested = False
        self._set_button_state(button, True, running_label)
        log.clear()
        write_log(log, start_message, level="progress")

    def _end_async(self, button: Button, idle_label: str) -> None:
        """Restore button state after async work completes."""
        self._set_button_state(button, False, idle_label)
        self._is_running = False
        self._cancel_requested = False

    def _is_cancelled(self) -> bool:
        """Return True when the user requested cancellation."""
        if self._cancel_requested:
            return True
        workers = getattr(self, "workers", None)
        if workers is None:
            return False
        return any(worker.is_cancelled for worker in workers)

    def action_cancel_async(self) -> None:
        """Cancel in-flight background work (bound to Escape)."""
        if not self._is_running:
            return
        self._cancel_requested = True
        workers = getattr(self, "workers", None)
        if workers is not None:
            for worker in workers:
                worker.cancel()
