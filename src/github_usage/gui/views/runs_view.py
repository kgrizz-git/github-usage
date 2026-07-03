"""Scheduled runs and drift dashboard for the Textual TUI."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, DataTable, RichLog, Static

from ...gui_backend import check_workflow_drift, formatted_scheduled_runs, load_setup_paths


class RunsView(VerticalScroll):
    """Read-only runs table and drift checker."""

    def compose(self) -> ComposeResult:
        yield Static("Scheduled Runs & Drift", classes="SectionTitle")
        with VerticalScroll():
            yield Button("Refresh runs", id="refresh-runs", variant="primary")
            yield Button("Check drift", id="check-drift")
            yield DataTable(id="runs-table")
            yield DataTable(id="drift-table")
        yield RichLog(id="runs-log", highlight=True)

    def on_mount(self) -> None:
        runs = self.query_one("#runs-table", DataTable)
        runs.add_columns("Active", "Profile", "Source", "Schedule")
        drift = self.query_one("#drift-table", DataTable)
        drift.add_columns("Path", "Drift", "Summary")
        self._paths = load_setup_paths()
        self._load_runs()

    def _load_runs(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.clear(columns=False)
        rows = formatted_scheduled_runs(self._paths)
        for row in rows:
            table.add_row(
                row["active"],
                row["profile_label"],
                row["source"],
                row["schedule"],
            )

    @on(Button.Pressed, "#refresh-runs")
    def _refresh(self) -> None:
        self._load_runs()
        self.query_one("#runs-log", RichLog).write("Runs refreshed.")

    @on(Button.Pressed, "#check-drift")
    def _check_drift(self) -> None:
        self._run_drift()

    @work(thread=True)
    def _run_drift(self) -> None:
        log = self.query_one("#runs-log", RichLog)
        self.call_from_thread(log.write, "Checking workflow drift…")
        result = check_workflow_drift(self._paths)
        self.call_from_thread(self._show_drift, result)

    def _show_drift(self, result) -> None:
        log = self.query_one("#runs-log", RichLog)
        for message in result.messages:
            log.write(message)
        table = self.query_one("#drift-table", DataTable)
        table.clear(columns=False)
        for row in result.rows:
            table.add_row(row.get("path", ""), row.get("drift", ""), row.get("summary", ""))
        if result.exit_code == 0:
            log.write(f"[green]Drift check complete ({len(result.rows)} file(s)).[/green]")
        else:
            log.write("[red]Drift check failed.[/red]")
