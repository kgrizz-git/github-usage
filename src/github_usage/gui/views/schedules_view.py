"""Schedule configuration screen for the Textual TUI."""

from __future__ import annotations

import sys

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, RichLog, Select, Static

from ...gui_backend import (
    DEFAULT_PROFILE_NAME,
    configure_github_actions_fields,
    configure_schedule_fields,
    get_launch_agent_status,
    install_launch_agent_for_paths,
    load_profiles,
    load_setup_paths,
    regenerate_launchd_plist,
    regenerate_workflow_file,
)


class SchedulesView(VerticalScroll):
    """Local launchd and GitHub Actions schedule forms."""

    def compose(self) -> ComposeResult:
        yield Static("Schedules", classes="SectionTitle")
        with Horizontal(classes="FormRow"):
            yield Label("Profile:")
            yield Select([], id="profile-select")
        yield Static("Local schedule (launchd, local timezone)", classes="SectionTitle")
        with Horizontal(classes="FormRow"):
            yield Label("Weekday (0=Sun, 1=Mon):")
            yield Input(value="1", id="weekday")
            yield Label("Hour:")
            yield Input(value="9", id="hour")
            yield Label("Minute:")
            yield Input(value="0", id="minute")
        yield Static("GitHub Actions cron (UTC)", classes="SectionTitle")
        yield Input(value="0 9 * * 1", id="cron")
        yield Checkbox("GA: include consumers", id="ga-consumers")
        yield Checkbox("GA: include artifact storage", id="ga-artifact")
        yield Checkbox("GA: include release assets", id="ga-release")
        with Horizontal():
            yield Button("Save schedules", id="save-sched", variant="primary")
            yield Button("Regenerate plist", id="regen-plist")
            yield Button("Regenerate workflow", id="regen-workflow")
        if sys.platform == "darwin":
            with Horizontal():
                yield Button("Install LaunchAgent", id="install-la", variant="success")
        else:
            yield Static(
                "Local launchd scheduling is macOS-only. "
                "Use GitHub Actions for cross-platform cloud schedules.",
                id="macos-note",
            )
        yield RichLog(id="sched-log", highlight=True)

    def on_mount(self) -> None:
        self._paths = load_setup_paths()
        self._reload_form()

    def _profile_name(self) -> str:
        value = self.query_one("#profile-select", Select).value
        return str(value) if value is not Select.BLANK else DEFAULT_PROFILE_NAME

    def _reload_form(self) -> None:
        config = load_profiles(self._paths)
        names = [p["name"] for p in config.get("profiles", [])]
        select = self.query_one("#profile-select", Select)
        select.set_options([(n, n) for n in names])
        if names:
            select.value = names[0]
        profile = next(p for p in config["profiles"] if p["name"] == self._profile_name())
        sched = profile["schedule"]
        ga = profile["github_actions"]
        self.query_one("#weekday", Input).value = str(sched.get("weekday", 1))
        self.query_one("#hour", Input).value = str(sched.get("hour", 9))
        self.query_one("#minute", Input).value = str(sched.get("minute", 0))
        self.query_one("#cron", Input).value = str(ga.get("cron", "0 9 * * 1"))
        self.query_one("#ga-consumers", Checkbox).value = bool(ga.get("include_consumers"))
        self.query_one("#ga-artifact", Checkbox).value = bool(ga.get("include_artifact_storage"))
        self.query_one("#ga-release", Checkbox).value = bool(ga.get("include_release_assets"))

    @on(Select.Changed, "#profile-select")
    def _profile_changed(self) -> None:
        self._reload_form()

    @on(Button.Pressed, "#save-sched")
    def _save_schedules(self) -> None:
        log = self.query_one("#sched-log", RichLog)
        try:
            configure_schedule_fields(
                self._paths,
                self._profile_name(),
                weekday=int(self.query_one("#weekday", Input).value),
                hour=int(self.query_one("#hour", Input).value),
                minute=int(self.query_one("#minute", Input).value),
            )
            configure_github_actions_fields(
                self._paths,
                self._profile_name(),
                cron=self.query_one("#cron", Input).value,
                include_consumers=self.query_one("#ga-consumers", Checkbox).value,
                include_artifact_storage=self.query_one("#ga-artifact", Checkbox).value,
                include_release_assets=self.query_one("#ga-release", Checkbox).value,
            )
            log.write("[green]Schedules saved.[/green]")
        except (ValueError, KeyError) as exc:
            log.write(f"[red]{exc}[/red]")

    @on(Button.Pressed, "#regen-plist")
    def _regen_plist(self) -> None:
        if sys.platform != "darwin":
            return
        path = regenerate_launchd_plist(self._paths, self._profile_name())
        self.query_one("#sched-log", RichLog).write(f"Generated {path}")

    @on(Button.Pressed, "#regen-workflow")
    def _regen_workflow(self) -> None:
        try:
            path = regenerate_workflow_file(self._paths, self._profile_name())
            self.query_one("#sched-log", RichLog).write(f"Wrote workflow {path}")
        except (ValueError, FileNotFoundError, KeyError) as exc:
            self.query_one("#sched-log", RichLog).write(f"[red]{exc}[/red]")

    @on(Button.Pressed, "#install-la")
    @work(thread=True)
    def _install_la(self) -> None:
        code, message = install_launch_agent_for_paths(self._paths)
        status = get_launch_agent_status(self._paths)
        log = self.query_one("#sched-log", RichLog)
        self.call_from_thread(log.write, message or f"LaunchAgent status: {status}")
        if code != 0:
            self.call_from_thread(log.write, f"[red]Install exit code {code}[/red]")
