"""Scheduled runs and drift dashboard for the Textual TUI."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, DataTable, RichLog

from ...gui_backend import check_workflow_drift, formatted_scheduled_runs
from ..async_ops import AsyncViewMixin
from ..errors import format_error
from ..layout import ViewActions, ViewOutput, ViewSection
from ..log_utils import write_log


class RunsView(VerticalScroll, AsyncViewMixin):
    """Read-only runs table and drift checker."""

    BINDINGS = [
        ("ctrl+r", "refresh_runs", "Refresh"),
        ("escape", "cancel_async", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield ViewSection(
            "Scheduled Runs & Drift",
            "Refresh lists configured schedules from local config. "
            "Check drift compares workflow files to remote. Ctrl+R refreshes.",
        )
        with ViewActions():
            yield Button("Refresh runs", id="refresh-runs", variant="primary")
            yield Button("Check drift", id="check-drift")
        with ViewOutput():
            yield DataTable(id="runs-table")
            yield DataTable(id="drift-table")
            yield RichLog(id="runs-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        runs = self.query_one("#runs-table", DataTable)
        runs.add_columns("Active", "Profile", "Source", "Schedule")
        drift = self.query_one("#drift-table", DataTable)
        drift.add_columns("Path", "Drift", "Summary")
        self._is_running = False
        self._cancel_requested = False
        self._load_runs()

    def _load_runs(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.clear(columns=False)
        try:
            paths = self.app.app_state.paths  # type: ignore[attr-defined]
            rows = formatted_scheduled_runs(paths)
            for row in rows:
                table.add_row(
                    row["active"],
                    row["profile_label"],
                    row["source"],
                    row["schedule"],
                )
        except Exception as exc:
            log = self.query_one("#runs-log", RichLog)
            write_log(log, format_error(exc, context="Failed to load runs"), level="error")

    @on(Button.Pressed, "#refresh-runs")
    def _refresh(self) -> None:
        self._load_runs()
        write_log(self.query_one("#runs-log", RichLog), "Runs refreshed", level="success")

    def action_refresh_runs(self) -> None:
        self._load_runs()
        write_log(self.query_one("#runs-log", RichLog), "Runs refreshed", level="success")

    @on(Button.Pressed, "#check-drift")
    def _check_drift(self) -> None:
        if self._is_running:
            return
        self._run_drift()

    @work(thread=True)
    def _run_drift(self) -> None:
        button = self.query_one("#check-drift", Button)
        log = self.query_one("#runs-log", RichLog)
        self._call_ui(
            self._begin_async,
            button,
            log,
            running_label="Checking...",
            start_message="Checking workflow drift...",
        )
        try:
            if self._is_cancelled():
                self._call_ui(write_log, log, "Drift check cancelled", level="warning")
                return
            paths = self.app.app_state.paths  # type: ignore[attr-defined]
            result = check_workflow_drift(paths)
            if self._is_cancelled():
                self._call_ui(write_log, log, "Drift check cancelled", level="warning")
                return
            self._call_ui(self._show_drift, result)
        except Exception as exc:
            self._call_ui(write_log, log, format_error(exc), level="error")
        finally:
            self._call_ui(self._end_async, button, "Check drift")

    def _show_drift(self, result) -> None:
        log = self.query_one("#runs-log", RichLog)
        for message in result.messages:
            log.write(message)
        table = self.query_one("#drift-table", DataTable)
        table.clear(columns=False)
        for row in result.rows:
            table.add_row(row.get("path", ""), row.get("drift", ""), row.get("summary", ""))
        if result.exit_code == 0:
            write_log(log, f"Drift check complete ({len(result.rows)} file(s))", level="success")
        else:
            write_log(log, "Drift check failed", level="error")
