"""Main window layout with sidebar navigation."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, ContentSwitcher, Static

from .views.email_report_view import EmailReportView
from .views.report_view import ReportView
from .views.runs_view import RunsView
from .views.schedules_view import SchedulesView
from .views.setup_view import SetupView


class MainWindow(Container):
    """Sidebar navigation and content area."""

    DEFAULT_CSS = """
    MainWindow {
        width: 100%;
        height: 100%;
    }
    """

    VIEWS: dict[str, str] = {
        "setup": "Setup & Profiles",
        "report": "Usage Report",
        "email": "Email Report",
        "schedules": "Schedules",
        "runs": "Runs & Drift",
    }

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Container(id="sidebar"):
                yield Static("NAVIGATION", classes="sidebar-title")
                for view_id, label in self.VIEWS.items():
                    yield Button(label, id=f"nav-{view_id}", classes="SidebarButton")
            with ContentSwitcher(initial="setup", id="content-switcher"):
                yield SetupView(id="setup")
                yield ReportView(id="report")
                yield EmailReportView(id="email")
                yield SchedulesView(id="schedules")
                yield RunsView(id="runs")

    def on_mount(self) -> None:
        self._set_active("setup")

    def _set_active(self, view_id: str) -> None:
        switcher = self.query_one("#content-switcher", ContentSwitcher)
        switcher.current = view_id
        for button in self.query(".SidebarButton"):
            button.remove_class("-active")
        nav = self.query_one(f"#nav-{view_id}", Button)
        nav.add_class("-active")

    @on(Button.Pressed)
    def _nav_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("nav-"):
            return
        view_id = button_id.removeprefix("nav-")
        if view_id in self.VIEWS:
            self._set_active(view_id)
