"""Legacy usage report screen for the Textual TUI."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, RichLog, Select, Static

from ...gui_backend import export_legacy_report, run_legacy_report_data


class ReportView(VerticalScroll):
    """Fetch and display legacy usage report summary."""

    def compose(self) -> ComposeResult:
        yield Static("Legacy Usage Report", classes="SectionTitle")
        with Horizontal(classes="FormRow"):
            yield Label("Timeout:")
            yield Input(value="30", id="timeout")
            yield Label("Max retries:")
            yield Input(value="3", id="max-retries")
        with Horizontal(classes="FormRow"):
            yield Label("Export:")
            yield Select(
                [
                    ("none", "none"),
                    ("csv", "csv"),
                    ("json", "json"),
                    ("text", "text"),
                    ("xlsx", "xlsx"),
                    ("pdf", "pdf"),
                ],
                id="export-format",
                value="none",
            )
            yield Label("Output path:")
            yield Input(placeholder="/absolute/path/report.csv", id="output-path")
        yield Button("Run Report", id="run-report", variant="primary")
        yield Static("Summary", classes="SectionTitle")
        yield DataTable(id="summary-table")
        yield RichLog(id="report-log", highlight=True)

    def on_mount(self) -> None:
        table = self.query_one("#summary-table", DataTable)
        table.add_columns("Metric", "Value")
        self._report_data: dict | None = None
        self._username: str | None = None

    @on(Button.Pressed, "#run-report")
    def _run_report(self) -> None:
        self._fetch_report()

    @work(thread=True)
    def _fetch_report(self) -> None:
        log = self.query_one("#report-log", RichLog)
        self.call_from_thread(log.write, "Fetching report data…")
        timeout = float(self.query_one("#timeout", Input).value.strip() or "30")
        max_retries = int(self.query_one("#max-retries", Input).value.strip() or "3")
        code, data, username_or_err = run_legacy_report_data(
            timeout=timeout, max_retries=max_retries
        )
        self.call_from_thread(self._show_report_result, code, data, username_or_err)

    def _show_report_result(
        self, code: int, data: dict | None, username_or_err: str | None
    ) -> None:
        log = self.query_one("#report-log", RichLog)
        table = self.query_one("#summary-table", DataTable)
        table.clear()
        if code != 0 or data is None:
            log.write(f"[red]Report failed: {username_or_err or 'unknown error'}[/red]")
            return
        self._report_data = data
        self._username = username_or_err
        account = data.get("account", {})
        rows = [
            ("User", str(username_or_err)),
            ("Total spend", str(account.get("total_spend", "n/a"))),
            ("Actions minutes", str(data.get("actions", {}).get("total_minutes", "n/a"))),
            ("Storage GB", str(data.get("storage", {}).get("total_gb", "n/a"))),
        ]
        for metric, value in rows:
            table.add_row(metric, value)
        consumers = data.get("top_consumers") or []
        for item in consumers[:10]:
            table.add_row(
                f"Repo: {item.get('name', '?')}",
                str(item.get("minutes", item.get("cost", "n/a"))),
            )
        log.write("[green]Report data loaded.[/green]")
        export_format = str(self.query_one("#export-format", Select).value)
        if export_format and export_format != "none":
            output = self.query_one("#output-path", Input).value.strip() or None
            exp_code, message = export_legacy_report(
                data, str(username_or_err), export_format, output
            )
            if exp_code == 0:
                log.write(f"[green]{message}[/green]")
            else:
                log.write(f"[red]{message}[/red]")
