"""Main window layout with top-level tab navigation."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane

from .modals import ConfirmScreen
from .views.email_report_view import EmailReportView
from .views.report_view import ReportView
from .views.runs_view import RunsView
from .views.schedules_view import SchedulesView
from .views.setup_view import SetupView


class MainWindow(Container):
    """Top tab navigation and content area."""

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

    VIEW_ORDER: list[str] = ["setup", "report", "email", "schedules", "runs"]

    # Views whose behavior is driven by the selected config.toml profile.
    _PROFILE_AWARE_VIEWS: frozenset[str] = frozenset({"setup", "email", "schedules"})

    _VIEW_CLASSES: dict[str, type[Widget]] = {
        "setup": SetupView,
        "report": ReportView,
        "email": EmailReportView,
        "schedules": SchedulesView,
        "runs": RunsView,
    }

    BINDINGS = [
        ("up", "nav_prev", "Prev view"),
        ("down", "nav_next", "Next view"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._active_view_id = "setup"
        self._programmatic_tab_change = False

    def compose(self) -> ComposeResult:
        with TabbedContent(id="main-tabs", initial="setup"):
            with TabPane("1. Setup & Profiles", id="setup"):
                yield SetupView()
            with TabPane("2. Usage Report", id="report"):
                yield ReportView()
            with TabPane("3. Email Report", id="email"):
                yield EmailReportView()
            with TabPane("4. Schedules", id="schedules"):
                yield SchedulesView()
            with TabPane("5. Runs & Drift", id="runs"):
                yield RunsView()

    def on_mount(self) -> None:
        self._set_active("setup")

    def restore_last_view(self) -> None:
        """Open the view the user last visited."""
        view_id = self.app.app_state.prefs.last_view  # type: ignore[attr-defined]
        if view_id in self.VIEWS:
            self._set_active(view_id)

    def _view_for_id(self, view_id: str) -> Widget:
        cls = self._VIEW_CLASSES[view_id]
        return self.query_one(cls)

    def _current_view_widget(self) -> Widget:
        return self._view_for_id(self._active_view_id)

    def _has_unsaved_changes_for(self, view_id: str) -> bool:
        view = self._view_for_id(view_id)
        return bool(getattr(view, "has_unsaved_changes", lambda: False)())

    def _has_unsaved_changes(self) -> bool:
        return self._has_unsaved_changes_for(self._active_view_id)

    async def request_view(self, view_id: str) -> None:
        """Switch views, confirming when the current view has unsaved edits."""
        if view_id not in self.VIEWS:
            return
        if view_id == self._active_view_id:
            return
        if self._has_unsaved_changes():
            confirmed = await self.app.push_screen_wait(
                ConfirmScreen(
                    "You have unsaved changes. Switch views anyway?",
                    title="Unsaved changes",
                )
            )
            if not confirmed:
                return
        self._set_active(view_id)

    def _subtitle_for(self, view_id: str) -> str:
        """Build header subtitle; profile name only where profiles matter."""
        title = self.VIEWS[view_id]
        if view_id not in self._PROFILE_AWARE_VIEWS:
            return title
        profile = (self.app.app_state.current_profile or "").strip() or "(none)"  # type: ignore[attr-defined]
        return f"{title} · profile: {profile}"

    def _commit_tab_switch(self, view_id: str) -> None:
        """Update tracked view state after the tab widget has switched."""
        self._active_view_id = view_id
        self.app.sub_title = self._subtitle_for(view_id)
        self.app.app_state.set_last_view(view_id)  # type: ignore[attr-defined]

    def _set_active(self, view_id: str) -> None:
        """Switch tabs programmatically (keyboard shortcuts and restore)."""
        if view_id not in self.VIEWS:
            return
        tabs = self.query_one("#main-tabs", TabbedContent)
        self._programmatic_tab_change = True
        try:
            self._active_view_id = view_id
            if tabs.active != view_id:
                tabs.active = view_id
            self.app.sub_title = self._subtitle_for(view_id)
            self.app.app_state.set_last_view(view_id)  # type: ignore[attr-defined]
        finally:
            self._programmatic_tab_change = False

    def action_show_view(self, view_id: str) -> None:
        """Switch view from app-level keyboard shortcuts (1-5)."""
        if view_id not in self.VIEWS:
            return
        if self._has_unsaved_changes():
            self.run_worker(self.request_view(view_id), exclusive=True)
        else:
            self._set_active(view_id)

    def action_nav_prev(self) -> None:
        try:
            index = self.VIEW_ORDER.index(self._active_view_id)
        except ValueError:
            index = 0
        prev_id = self.VIEW_ORDER[(index - 1) % len(self.VIEW_ORDER)]
        if self._has_unsaved_changes():
            self.run_worker(self.request_view(prev_id), exclusive=True)
        else:
            self._set_active(prev_id)

    def action_nav_next(self) -> None:
        try:
            index = self.VIEW_ORDER.index(self._active_view_id)
        except ValueError:
            index = 0
        next_id = self.VIEW_ORDER[(index + 1) % len(self.VIEW_ORDER)]
        if self._has_unsaved_changes():
            self.run_worker(self.request_view(next_id), exclusive=True)
        else:
            self._set_active(next_id)

    @on(TabbedContent.TabActivated, "#main-tabs")
    def _tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle mouse/tab clicks without blocking the UI thread."""
        if self._programmatic_tab_change:
            return
        new_id = event.pane.id
        if not new_id or new_id == self._active_view_id:
            return

        old_id = self._active_view_id
        if self._has_unsaved_changes_for(old_id):
            self.run_worker(self._confirm_tab_switch(old_id, new_id), exclusive=True)  # type: ignore[arg-type]
            return
        self._commit_tab_switch(new_id)

    @work
    async def _confirm_tab_switch(self, old_id: str, new_id: str) -> None:
        """Confirm discarding unsaved edits when the user clicks another tab."""
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                "You have unsaved changes. Switch views anyway?",
                title="Unsaved changes",
            )
        )
        tabs = self.query_one("#main-tabs", TabbedContent)
        if not confirmed:
            self._programmatic_tab_change = True
            try:
                tabs.active = old_id
            finally:
                self._programmatic_tab_change = False
            return
        self._commit_tab_switch(new_id)
