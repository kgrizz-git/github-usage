"""Friendly schedule picker widgets for the Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Checkbox, Collapsible, Input, Label, Select, Static

from ...schedule_helpers import (
    DST_NOTE,
    WEEKDAY_CHOICES,
    build_weekly_cron_utc,
    describe_cron_human,
    describe_ga_schedule_local,
    describe_local_schedule,
    local_timezone,
    normalize_launchd_weekday,
    parse_weekly_cron_to_local,
)
from ...setup_workflow import validate_cron
from ..layout import FormGrid


@dataclass(frozen=True)
class LocalScheduleValues:
    """launchd weekday/hour/minute."""

    weekday: int
    hour: int
    minute: int


class SchedulePicker(Vertical):
    """Weekday + time pickers with human previews and optional advanced GA cron."""

    DEFAULT_CSS = """
    SchedulePicker {
        height: auto;
    }
    SchedulePicker .schedule-preview {
        color: $text-muted;
        margin: 0 0 1 0;
    }
    SchedulePicker .dst-note {
        color: $warning;
        margin-bottom: 1;
    }
    """

    class Changed(Message):
        """Posted when any schedule field changes."""

        bubble = True

        def __init__(self, picker: SchedulePicker) -> None:
            super().__init__()
            self.picker = picker

    def __init__(
        self,
        *,
        show_local: bool = True,
        show_ga: bool = True,
        ga_first: bool = False,
        id_prefix: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._show_local = show_local
        self._show_ga = show_ga
        self._ga_first = ga_first
        self._prefix = id_prefix
        self._ga_advanced = False
        self._loading = False

    def _field_id(self, suffix: str) -> str:
        """Return a child widget id, prefixed when this picker is embedded twice."""
        return f"{self._prefix}{suffix}" if self._prefix else suffix

    def compose(self) -> ComposeResult:
        parts: list[ComposeResult] = []
        if self._ga_first:
            if self._show_ga:
                parts.append(self._compose_ga())
            if self._show_local:
                parts.append(self._compose_local())
        else:
            if self._show_local:
                parts.append(self._compose_local())
            if self._show_ga:
                parts.append(self._compose_ga())
        for part in parts:
            yield from part

    def _compose_local(self) -> ComposeResult:
        yield Static("Local schedule (launchd, your timezone)", classes="SectionTitle")
        with FormGrid():
            yield Label("Day:")
            yield Select(
                [(label, str(value)) for label, value in WEEKDAY_CHOICES],
                id=self._field_id("local-weekday"),
                value="1",
            )
            yield Label("Hour:")
            yield Input(value="9", id=self._field_id("local-hour"), placeholder="0-23")
            yield Label("Minute:")
            yield Input(value="0", id=self._field_id("local-minute"), placeholder="0-59")
        yield Static("", id=self._field_id("local-preview"), classes="schedule-preview")

    def _compose_ga(self) -> ComposeResult:
        yield Static("GitHub Actions (cloud schedule)", classes="SectionTitle")
        yield Static(
            "Pick when reports should run in your local time. "
            "We convert to UTC for GitHub Actions.",
            classes="HelpText",
        )
        with FormGrid():
            yield Label("Day:")
            yield Select(
                [(label, str(value)) for label, value in WEEKDAY_CHOICES],
                id=self._field_id("ga-weekday"),
                value="1",
            )
            yield Label("Hour:")
            yield Input(value="9", id=self._field_id("ga-hour"), placeholder="0-23")
            yield Label("Minute:")
            yield Input(value="0", id=self._field_id("ga-minute"), placeholder="0-59")
        yield Static("", id=self._field_id("ga-preview"), classes="schedule-preview", markup=True)
        yield Static(DST_NOTE, classes="dst-note")
        with Collapsible(
            title="Advanced: edit cron directly (UTC)",
            collapsed=True,
            id=self._field_id("ga-cron-advanced"),
        ):
            yield Checkbox("Use custom cron expression", id=self._field_id("ga-advanced"))
            yield Input(value="0 9 * * 1", id=self._field_id("ga-cron"))
            yield Static(
                "Five fields: minute hour day-of-month month day-of-week (UTC). "
                "Use only if you need daily, monthly, or non-weekly schedules.",
                classes="HelpText",
            )

    def set_loading(self, loading: bool) -> None:
        """Suppress change events while programmatically updating fields."""
        self._loading = loading

    def set_local_schedule(self, weekday: int, hour: int, minute: int) -> None:
        """Populate local launchd fields."""
        if not self._show_local:
            return
        self._loading = True
        try:
            weekday = normalize_launchd_weekday(weekday)
            self.query_one(f"#{self._field_id('local-weekday')}", Select).value = str(weekday)
            self.query_one(f"#{self._field_id('local-hour')}", Input).value = str(hour)
            self.query_one(f"#{self._field_id('local-minute')}", Input).value = str(minute)
        finally:
            self._loading = False
        self._refresh_previews()

    def set_ga_cron(self, cron: str) -> None:
        """Populate GA fields from a cron expression or advanced mode."""
        if not self._show_ga:
            return
        self._loading = True
        try:
            parsed = parse_weekly_cron_to_local(cron, local_timezone())
            advanced = self.query_one(f"#{self._field_id('ga-advanced')}", Checkbox)
            cron_input = self.query_one(f"#{self._field_id('ga-cron')}", Input)
            if parsed is None:
                advanced.value = True
                cron_input.value = cron
                self._ga_advanced = True
            else:
                advanced.value = False
                cron_input.value = cron
                self._ga_advanced = False
                weekday, hour, minute = parsed
                self.query_one(f"#{self._field_id('ga-weekday')}", Select).value = str(weekday)
                self.query_one(f"#{self._field_id('ga-hour')}", Input).value = str(hour)
                self.query_one(f"#{self._field_id('ga-minute')}", Input).value = str(minute)
            self._set_ga_picker_disabled(self._ga_advanced)
            self._sync_advanced_panel()
        finally:
            self._loading = False
        self._refresh_previews()

    def _sync_advanced_panel(self) -> None:
        if not self._show_ga:
            return
        panel = self.query_one(f"#{self._field_id('ga-cron-advanced')}", Collapsible)
        panel.collapsed = not self._ga_advanced

    def get_local_schedule(self) -> LocalScheduleValues | None:
        """Return local schedule values or ``None`` when invalid."""
        if not self._show_local:
            return None
        error = self._validate_local_fields()
        if error:
            return None
        weekday = int(str(self.query_one(f"#{self._field_id('local-weekday')}", Select).value))
        hour = int(self.query_one(f"#{self._field_id('local-hour')}", Input).value)
        minute = int(self.query_one(f"#{self._field_id('local-minute')}", Input).value)
        return LocalScheduleValues(
            weekday=normalize_launchd_weekday(weekday),
            hour=hour,
            minute=minute,
        )

    def get_ga_cron(self) -> str | None:
        """Return GA cron expression or ``None`` when invalid."""
        if not self._show_ga:
            return None
        if self._ga_advanced:
            try:
                return validate_cron(
                    self.query_one(f"#{self._field_id('ga-cron')}", Input).value.strip()
                )
            except ValueError:
                return None
        values = self._read_ga_picker_values()
        if values is None:
            return None
        weekday, hour, minute = values
        return build_weekly_cron_utc(weekday, hour, minute, local_timezone())

    def validate(self) -> str | None:
        """Return an error message when fields are invalid."""
        if self._show_local:
            error = self._validate_local_fields()
            if error:
                return error
        if self._show_ga:
            if self._ga_advanced:
                try:
                    validate_cron(
                        self.query_one(f"#{self._field_id('ga-cron')}", Input).value.strip()
                    )
                except ValueError as exc:
                    return str(exc)
            elif self._read_ga_picker_values() is None:
                return "GitHub Actions day and time must be valid integers in range"
            elif self.get_ga_cron() is None:
                return "Invalid GitHub Actions schedule"
        return None

    def _validate_local_fields(self) -> str | None:
        try:
            weekday = int(str(self.query_one(f"#{self._field_id('local-weekday')}", Select).value))
            hour = int(self.query_one(f"#{self._field_id('local-hour')}", Input).value)
            minute = int(self.query_one(f"#{self._field_id('local-minute')}", Input).value)
        except (ValueError, TypeError):
            return "Local day and time must be valid integers"
        if not 0 <= normalize_launchd_weekday(weekday) <= 6:
            return "Local weekday is out of range"
        if not 0 <= hour <= 23:
            return "Local hour must be 0 through 23"
        if not 0 <= minute <= 59:
            return "Local minute must be 0 through 59"
        return None

    def _read_ga_picker_values(self) -> tuple[int, int, int] | None:
        try:
            weekday = int(str(self.query_one(f"#{self._field_id('ga-weekday')}", Select).value))
            hour = int(self.query_one(f"#{self._field_id('ga-hour')}", Input).value)
            minute = int(self.query_one(f"#{self._field_id('ga-minute')}", Input).value)
        except (ValueError, TypeError):
            return None
        if not 0 <= normalize_launchd_weekday(weekday) <= 6:
            return None
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None
        return normalize_launchd_weekday(weekday), hour, minute

    def _set_ga_picker_disabled(self, disabled: bool) -> None:
        for widget_id in (
            self._field_id("ga-weekday"),
            self._field_id("ga-hour"),
            self._field_id("ga-minute"),
        ):
            self.query_one(f"#{widget_id}").disabled = disabled
        self.query_one(f"#{self._field_id('ga-cron')}", Input).disabled = not disabled

    def _refresh_previews(self) -> None:
        if self._show_local:
            preview = self.query_one(f"#{self._field_id('local-preview')}", Static)
            values = self.get_local_schedule()
            preview.update(
                describe_local_schedule(values.weekday, values.hour, values.minute)
                if values
                else "Enter a valid local day and time"
            )
        if self._show_ga:
            ga_preview = self.query_one(f"#{self._field_id('ga-preview')}", Static)
            cron_text = self.query_one(f"#{self._field_id('ga-cron')}", Input).value.strip()
            if self._ga_advanced:
                human = describe_cron_human(cron_text)
                ga_preview.update(
                    f"[b]Saved:[/b] {human or cron_text}"
                    + (f" [dim](cron: {cron_text})[/dim]" if human else " UTC")
                )
            else:
                values = self._read_ga_picker_values()
                if values:
                    weekday, hour, minute = values
                    ga_preview.update(
                        describe_ga_schedule_local(weekday, hour, minute, local_timezone())
                        + (f" [dim](cron: {cron_text})[/dim]" if cron_text else "")
                    )
                else:
                    ga_preview.update("Enter a valid day and time")

    @on(Select.Changed)
    @on(Input.Changed)
    @on(Checkbox.Changed)
    def _on_field_changed(self, event: Checkbox.Changed | Input.Changed | Select.Changed) -> None:
        if self._loading:
            return
        control = event.control
        if control is not None and control.id == self._field_id("ga-advanced"):
            self._ga_advanced = bool(event.value)
            self._set_ga_picker_disabled(self._ga_advanced)
            self._sync_advanced_panel()
        self._refresh_previews()
        self.post_message(self.Changed(self))

    def on_mount(self) -> None:
        if self._show_ga:
            self._ga_advanced = self.query_one(f"#{self._field_id('ga-advanced')}", Checkbox).value
            self._set_ga_picker_disabled(self._ga_advanced)
        self._refresh_previews()
