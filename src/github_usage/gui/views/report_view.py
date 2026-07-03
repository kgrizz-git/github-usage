"""Legacy usage report screen for the Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    DataTable,
    Input,
    Label,
    RichLog,
    Select,
    Static,
)

from ...gui_backend import export_legacy_report, run_legacy_report_data
from ...legacy_report_summary import legacy_report_detail_rows
from ...report_cache import format_cache_hit_message
from ..async_ops import AsyncViewMixin
from ..errors import format_error
from ..layout import FormGrid, ViewActions, ViewOutput, ViewSection
from ..log_utils import write_log


@dataclass(frozen=True)
class _ReportRunParams:
    """Form values read on the UI thread before background work starts."""

    timeout: float
    max_retries: int
    export_format: str
    output_path: str | None
    refresh: bool


class ReportView(VerticalScroll, AsyncViewMixin):
    """Fetch and display legacy usage report summary."""

    BINDINGS = [
        ("ctrl+r", "run_report", "Run"),
        ("escape", "cancel_async", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield ViewSection(
            "Legacy Usage Report",
            "Separate from the email report system. Fetches a fixed GitHub billing / "
            "Actions snapshot (does not read profile options from config.toml) and shows "
            "a summary table here. Useful for a quick usage check, not for validating "
            "email setup — use Setup → Verify Email Setup for that.",
        )
        with FormGrid():
            yield Label("Timeout:")
            yield Input(value="30", id="timeout")
            yield Label("Max retries:")
            yield Input(value="3", id="max-retries")
            yield Label("Fetch fresh:")
            yield Checkbox("Ignore cache (--refresh)", id="report-refresh")
        with Collapsible(title="Export options", collapsed=True), FormGrid():
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
        with ViewActions():
            yield Button("Run Report", id="run-report", variant="primary")
        with ViewOutput():
            yield Static("Report details", classes="SectionTitle")
            yield DataTable(id="summary-table")
            yield RichLog(id="report-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        table = self.query_one("#summary-table", DataTable)
        table.add_columns("Metric", "Value")
        self._report_data: dict | None = None
        self._username: str | None = None
        self._is_running = False
        self._cancel_requested = False
        prefs = self.app.app_state.prefs
        self.query_one("#timeout", Input).value = str(prefs.report_timeout)
        self.query_one("#max-retries", Input).value = str(prefs.report_max_retries)

    @on(Button.Pressed, "#run-report")
    def _run_report(self) -> None:
        if self._is_running:
            return
        params = self._read_run_params()
        if params is None:
            return
        button = self.query_one("#run-report", Button)
        log = self.query_one("#report-log", RichLog)
        self._fetch_report(params, button, log)

    def action_run_report(self) -> None:
        if not self._is_running:
            params = self._read_run_params()
            if params is not None:
                button = self.query_one("#run-report", Button)
                log = self.query_one("#report-log", RichLog)
                self._fetch_report(params, button, log)

    def _read_run_params(self) -> _ReportRunParams | None:
        """Validate form fields on the UI thread."""
        log = self.query_one("#report-log", RichLog)
        timeout_str = self.query_one("#timeout", Input).value.strip() or "30"
        max_retries_str = self.query_one("#max-retries", Input).value.strip() or "3"

        try:
            timeout = float(timeout_str)
        except ValueError:
            write_log(
                log, f"Invalid timeout value '{timeout_str}' (must be a number)", level="error"
            )
            return None

        try:
            max_retries = int(max_retries_str)
        except ValueError:
            write_log(
                log,
                f"Invalid max retries value '{max_retries_str}' (must be an integer)",
                level="error",
            )
            return None

        if timeout <= 0:
            write_log(log, "Timeout must be greater than 0", level="error")
            return None

        if max_retries < 0:
            write_log(log, "Max retries cannot be negative", level="error")
            return None

        export_format = str(self.query_one("#export-format", Select).value)
        output_path = self.query_one("#output-path", Input).value.strip() or None
        refresh = bool(self.query_one("#report-refresh", Checkbox).value)
        self.app.app_state.save_report_settings(timeout, max_retries)
        return _ReportRunParams(timeout, max_retries, export_format, output_path, refresh)

    @work(thread=True)
    def _fetch_report(self, params: _ReportRunParams, button: Button, log: RichLog) -> None:
        self._call_ui(
            self._begin_async,
            button,
            log,
            running_label="Running...",
            start_message="Starting report generation...",
        )

        try:
            self._call_ui(
                write_log,
                log,
                f"Timeout: {params.timeout}s, Max retries: {params.max_retries}",
                level="dim",
            )
            if self._is_cancelled():
                self._call_ui(write_log, log, "Report cancelled", level="warning")
                return

            self._call_ui(write_log, log, "Fetching GitHub token...", level="progress")
            self._call_ui(write_log, log, "Fetching billing data...", level="progress")

            code, data, username_or_err, cache_hit = run_legacy_report_data(
                timeout=params.timeout,
                max_retries=params.max_retries,
                refresh=params.refresh,
                paths=self.app.app_state.paths,
                gui_cache_max_age_seconds=self.app.app_state.prefs.report_cache_max_age_seconds,
            )

            if self._is_cancelled():
                self._call_ui(write_log, log, "Report cancelled", level="warning")
                return

            self._call_ui(write_log, log, "Processing report data...", level="progress")
            self._call_ui(self._show_report_result, code, data, username_or_err, cache_hit)

            if code == 0 and data is not None and username_or_err:
                self._maybe_export(log, data, username_or_err, params)
        except Exception as exc:
            self._call_ui(
                write_log, log, format_error(exc, context="Unexpected error"), level="error"
            )
        finally:
            self._call_ui(self._end_async, button, "Run Report")

    def _maybe_export(
        self,
        log: RichLog,
        data: dict,
        username: str,
        params: _ReportRunParams,
    ) -> None:
        """Export on the worker thread so file I/O does not block the UI."""
        export_format = params.export_format
        if not export_format or export_format == "none":
            return
        self._call_ui(write_log, log, f"Exporting to {export_format}...", level="progress")
        exp_code, message = export_legacy_report(data, username, export_format, params.output_path)
        level = "success" if exp_code == 0 else "error"
        self._call_ui(write_log, log, message, level=level)

    def _show_report_result(
        self,
        code: int,
        data: dict | None,
        username_or_err: str | None,
        cache_hit,
    ) -> None:
        log = self.query_one("#report-log", RichLog)
        table = self.query_one("#summary-table", DataTable)
        table.clear()

        if code != 0 or data is None:
            error_msg = username_or_err or "unknown error"
            write_log(log, f"Report failed: {error_msg}", level="error")
            if "token" in error_msg.lower():
                write_log(log, "Check that GITHUB_TOKEN is set and valid", level="warning")
            elif "rate limit" in error_msg.lower():
                write_log(log, "Wait a few minutes before retrying", level="warning")
            elif "timeout" in error_msg.lower():
                write_log(log, "Try increasing the timeout value", level="warning")
            return

        self._report_data = data
        self._username = username_or_err
        if getattr(cache_hit, "from_cache", False) and cache_hit.age_seconds is not None:
            write_log(
                log,
                format_cache_hit_message(cache_hit.age_seconds, cache_hit.max_age_seconds or 0),
                level="dim",
            )
        write_log(log, "Populating report table...", level="progress")

        detail_rows = legacy_report_detail_rows(data, str(username_or_err))
        for metric, value in detail_rows:
            table.add_row(metric, value)

        write_log(
            log,
            f"Report loaded ({len(detail_rows)} rows). Scroll the table for full details.",
            level="success",
        )
