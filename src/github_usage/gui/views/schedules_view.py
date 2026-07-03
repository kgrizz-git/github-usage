"""Schedule configuration screen for the Textual TUI."""

from __future__ import annotations

import sys

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Checkbox, Collapsible, Input, Label, RichLog, Select, Static

from ...gui_backend import (
    configure_github_actions_fields,
    configure_schedule_fields,
    get_launch_agent_status,
    install_launch_agent_for_paths,
    load_profiles,
    regenerate_launchd_plist,
    regenerate_workflow_file,
)
from ..async_ops import AsyncViewMixin
from ..errors import format_error
from ..layout import ViewActions, ViewOutput, ViewSection
from ..log_utils import write_log
from ..modals import ConfirmScreen
from ..widgets.schedule_picker import SchedulePicker


class SchedulesView(VerticalScroll, AsyncViewMixin):
    """Local launchd and GitHub Actions schedule forms."""

    DEFAULT_CSS = """
    SchedulesView {
        height: auto;
    }
    SchedulesView .profile-row {
        height: auto;
        margin-bottom: 1;
    }
    SchedulesView #profile-active-label {
        color: $text-muted;
        margin-left: 1;
    }
    SchedulesView ViewOutput {
        height: auto;
        min-height: 0;
        margin-top: 1;
    }
    SchedulesView ViewOutput RichLog {
        height: 12;
        min-height: 8;
    }
    """

    BINDINGS = [
        ("ctrl+s", "save_schedules", "Save"),
        ("escape", "cancel_async", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield ViewSection(
            "Schedules",
            "Per-profile timing for local launchd (macOS) and GitHub Actions (cloud). "
            "Pick day and time — no cron knowledge required. Ctrl+S saves. "
            "GA option checkboxes control scheduled workflow defaults "
            "(regenerate workflow after changing).",
        )
        with Horizontal(classes="profile-row"):
            yield Label("Profile:")
            yield Select([], id="profile-select")
            yield Static("", id="profile-active-label")
            yield Static("", id="dirty-indicator")
        yield SchedulePicker(id="schedule-picker", show_local=True, show_ga=True, ga_first=True)
        with Collapsible(title="GitHub Actions report options", collapsed=False):
            yield Static(
                "Defaults for cron runs and workflow_dispatch. "
                "Match Setup → Include top consumers / artifact / release for parity with local email.",
                classes="HelpText",
            )
            yield Checkbox("GA: include top repos (consumers)", id="ga-consumers")
            yield Checkbox("GA: include artifact storage", id="ga-artifact")
            yield Checkbox("GA: include release assets", id="ga-release")
        with ViewActions():
            yield Button("Save schedules", id="save-sched", variant="primary")
            yield Button("Regenerate plist", id="regen-plist")
            yield Button("Regenerate workflow", id="regen-workflow")
            if sys.platform == "darwin":
                yield Button("Install LaunchAgent", id="install-la", variant="success")
        if sys.platform != "darwin":
            yield Static(
                "Local launchd scheduling is macOS-only. "
                "Use GitHub Actions for cross-platform cloud schedules.",
                id="macos-note",
                classes="HelpText",
            )
        with ViewOutput():
            yield RichLog(id="sched-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        self._is_running = False
        self._cancel_requested = False
        self._dirty = False
        self._loading = True
        self._applying_selection = False
        self._previous_profile: str | None = None
        state = self.app.app_state
        state.add_listener(self._on_state_changed)
        try:
            self._on_state_changed()
        except FileNotFoundError:
            write_log(
                self.query_one("#sched-log", RichLog),
                "Config file not found. Run setup first.",
                level="error",
            )
        except PermissionError:
            write_log(
                self.query_one("#sched-log", RichLog),
                "Permission denied reading config.",
                level="error",
            )
        except Exception as exc:
            write_log(
                self.query_one("#sched-log", RichLog),
                format_error(exc, context="Failed to load schedules"),
                level="error",
            )

    def on_unmount(self) -> None:
        self.app.app_state.remove_listener(self._on_state_changed)

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def _on_state_changed(self) -> None:
        self._reload_form()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.query_one("#dirty-indicator", Static).update("[yellow]* unsaved[/yellow]")

    def _clear_dirty(self) -> None:
        self._dirty = False
        self.query_one("#dirty-indicator", Static).update("")

    def _profile_name(self) -> str:
        value = self.query_one("#profile-select", Select).value
        if value == Select.BLANK or str(value) == "Select.NULL" or value is None:
            return self.app.app_state.current_profile
        return str(value)

    def _reload_form(self) -> None:
        self._loading = True
        try:
            state = self.app.app_state
            paths = state.paths
            names = list(state.profile_names)
            select = self.query_one("#profile-select", Select)
            label = self.query_one("#profile-active-label", Static)
            if not names:
                select.set_options([])
                select.disabled = True
                label.update("")
                self._loading = False
                return

            select.disabled = False
            select.set_options([(name, name) for name in names])
            current = state.current_profile
            target = current if current in names else names[0]

            config = load_profiles(paths)
            profile = next(p for p in config["profiles"] if p["name"] == target)
            sched = profile["schedule"]
            ga = profile["github_actions"]
            picker = self.query_one("#schedule-picker", SchedulePicker)
            picker.set_loading(True)
            try:
                picker.set_local_schedule(
                    int(sched.get("weekday", 1)),
                    int(sched.get("hour", 9)),
                    int(sched.get("minute", 0)),
                )
                picker.set_ga_cron(str(ga.get("cron", "0 9 * * 1")))
            finally:
                picker.set_loading(False)
            self.query_one("#ga-consumers", Checkbox).value = bool(ga.get("include_consumers"))
            self.query_one("#ga-artifact", Checkbox).value = bool(
                ga.get("include_artifact_storage")
            )
            self.query_one("#ga-release", Checkbox).value = bool(ga.get("include_release_assets"))
            self._previous_profile = target

            def _apply_selection() -> None:
                self._applying_selection = True
                try:
                    select.value = target
                    label.update(f"Active: [b]{target}[/b]")
                    if self.app.app_state.current_profile != target:
                        self.app.app_state.set_current_profile(target, persist=False, notify=False)
                finally:
                    self._applying_selection = False
                    self._loading = False
                    self._clear_dirty()

            self.call_after_refresh(_apply_selection)
        except FileNotFoundError:
            self._loading = False
            raise
        except Exception:
            self._loading = False
            raise

    @on(Select.Changed, "#profile-select")
    def _profile_changed(self) -> None:
        if self._loading or self._applying_selection:
            return
        self._confirm_profile_switch()

    @work
    async def _confirm_profile_switch(self) -> None:
        new_name = self._profile_name()
        label = self.query_one("#profile-active-label", Static)
        if new_name:
            label.update(f"Active: [b]{new_name}[/b]")
        if self._dirty and self._previous_profile and new_name != self._previous_profile:
            confirmed = await self.app.push_screen_wait(
                ConfirmScreen(
                    f"Switch to profile '{new_name}'? Unsaved schedule changes will be lost.",
                    title="Unsaved changes",
                )
            )
            if not confirmed:
                select = self.query_one("#profile-select", Select)
                if self._previous_profile:
                    self._applying_selection = True
                    try:
                        select.value = self._previous_profile
                    finally:
                        self._applying_selection = False
                return
        self.app.app_state.set_current_profile(new_name)
        self._reload_form()

    @on(SchedulePicker.Changed)
    def _on_schedule_picker_changed(self, event: SchedulePicker.Changed) -> None:
        if self._loading:
            return
        picker = self.query_one("#schedule-picker", SchedulePicker)
        if getattr(event, "picker", None) is not picker:
            return
        self._mark_dirty()

    @on(Input.Changed)
    @on(Checkbox.Changed)
    def _on_field_changed(self) -> None:
        if self._loading:
            return
        self._mark_dirty()

    def _validate_schedule_fields(self, log: RichLog) -> bool:
        picker = self.query_one("#schedule-picker", SchedulePicker)
        error = picker.validate()
        if error:
            write_log(log, error, level="error")
            return False
        return True

    @on(Button.Pressed, "#save-sched")
    def _save_schedules(self) -> None:
        self.action_save_schedules()

    def action_save_schedules(self) -> None:
        log = self.query_one("#sched-log", RichLog)
        if not self._validate_schedule_fields(log):
            return
        paths = self.app.app_state.paths
        picker = self.query_one("#schedule-picker", SchedulePicker)
        local = picker.get_local_schedule()
        cron = picker.get_ga_cron()
        if local is None or cron is None:
            write_log(log, "Fix schedule fields before saving", level="error")
            return
        try:
            configure_schedule_fields(
                paths,
                self._profile_name(),
                weekday=local.weekday,
                hour=local.hour,
                minute=local.minute,
            )
            configure_github_actions_fields(
                paths,
                self._profile_name(),
                cron=cron,
                include_consumers=self.query_one("#ga-consumers", Checkbox).value,
                include_artifact_storage=self.query_one("#ga-artifact", Checkbox).value,
                include_release_assets=self.query_one("#ga-release", Checkbox).value,
            )
            self._clear_dirty()
            self.app.app_state.reload()
            write_log(log, "Schedules saved", level="success")
        except (ValueError, KeyError, PermissionError, OSError) as exc:
            write_log(log, format_error(exc), level="error")

    @on(Button.Pressed, "#regen-plist")
    def _regen_plist(self) -> None:
        if sys.platform != "darwin":
            return
        log = self.query_one("#sched-log", RichLog)
        try:
            path = regenerate_launchd_plist(self.app.app_state.paths, self._profile_name())
            write_log(log, f"Generated {path}", level="success")
        except (ValueError, FileNotFoundError, KeyError, OSError) as exc:
            write_log(log, format_error(exc), level="error")

    @on(Button.Pressed, "#regen-workflow")
    def _regen_workflow_pressed(self) -> None:
        self._confirm_regen_workflow()

    @work
    async def _confirm_regen_workflow(self) -> None:
        log = self.query_one("#sched-log", RichLog)
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                "Regenerate workflow file? This overwrites the existing workflow on disk.",
                title="Regenerate workflow",
            )
        )
        if not confirmed:
            return
        try:
            path = regenerate_workflow_file(self.app.app_state.paths, self._profile_name())
            write_log(log, f"Wrote workflow {path}", level="success")
        except (ValueError, FileNotFoundError, KeyError, OSError) as exc:
            write_log(log, format_error(exc), level="error")

    @on(Button.Pressed, "#install-la")
    def _install_la_pressed(self) -> None:
        if self._is_running:
            return
        self._confirm_install_la()

    @work
    async def _confirm_install_la(self) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                "Install or update the LaunchAgent plist for this profile?",
                title="Install LaunchAgent",
            )
        )
        if confirmed:
            self._install_la()

    @work(thread=True)
    def _install_la(self) -> None:
        button = self.query_one("#install-la", Button)
        log = self.query_one("#sched-log", RichLog)
        self._call_ui(
            self._begin_async,
            button,
            log,
            running_label="Installing...",
            start_message="Installing LaunchAgent...",
        )
        try:
            if self._is_cancelled():
                self._call_ui(write_log, log, "Install cancelled", level="warning")
                return
            paths = self.app.app_state.paths
            code, message = install_launch_agent_for_paths(paths)
            status = get_launch_agent_status(paths)
            self._call_ui(write_log, log, message or f"LaunchAgent status: {status}", level="info")
            if code != 0:
                self._call_ui(write_log, log, f"Install exit code {code}", level="error")
            else:
                self._call_ui(write_log, log, "LaunchAgent installed", level="success")
        except Exception as exc:
            self._call_ui(write_log, log, format_error(exc), level="error")
        finally:
            self._call_ui(self._end_async, button, "Install LaunchAgent")
