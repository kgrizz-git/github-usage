"""Human-friendly schedule helpers for CLI and TUI.

Converts between launchd weekday/hour/minute (local timezone), GitHub Actions
5-field UTC cron expressions, and plain-language descriptions. GitHub Actions
cron is fixed at save time; daylight saving time can shift the effective local
run time until the user re-saves.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# launchd weekday: 0/7 = Sunday, 1 = Monday, …, 6 = Saturday.
WEEKDAY_NAMES: dict[int, str] = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

WEEKDAY_PLURAL: dict[int, str] = {
    0: "Sundays",
    1: "Mondays",
    2: "Tuesdays",
    3: "Wednesdays",
    4: "Thursdays",
    5: "Fridays",
    6: "Saturdays",
    7: "Sundays",
}

# (label, launchd weekday value) for Select widgets.
WEEKDAY_CHOICES: tuple[tuple[str, int], ...] = tuple((WEEKDAY_NAMES[day], day) for day in range(7))

DST_NOTE = (
    "GitHub Actions uses a fixed UTC schedule. After daylight saving changes, "
    "the job may run one hour earlier or later in your local time until you "
    "re-save the schedule."
)


def normalize_launchd_weekday(weekday: int) -> int:
    """Normalize launchd weekday (0–6 or 7 for Sunday) to 0–6."""
    if weekday == 7:
        return 0
    return weekday


def launchd_to_python_weekday(weekday: int) -> int:
    """Map launchd weekday (0=Sun) to ``datetime.weekday()`` (Mon=0, Sun=6)."""
    weekday = normalize_launchd_weekday(weekday)
    return 6 if weekday == 0 else weekday - 1


def python_to_launchd_weekday(python_weekday: int) -> int:
    """Map ``datetime.weekday()`` to launchd weekday (0=Sun)."""
    return 0 if python_weekday == 6 else python_weekday + 1


def python_to_cron_dow(python_weekday: int) -> int:
    """Map ``datetime.weekday()`` to cron day-of-week (0=Sun)."""
    return (python_weekday + 1) % 7


def cron_dow_to_python_weekday(cron_dow: int) -> int:
    """Map cron day-of-week (0=Sun) to ``datetime.weekday()``."""
    return 6 if cron_dow == 0 else cron_dow - 1


def local_timezone() -> ZoneInfo:
    """Return the system local timezone."""
    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")  # type: ignore[return-value]


def build_weekly_cron_utc(
    weekday: int,
    hour: int,
    minute: int,
    tz: ZoneInfo | None = None,
) -> str:
    """Convert a weekly local day/time to a GitHub Actions UTC cron expression.

    Args:
        weekday: launchd weekday (0/7=Sun … 6=Sat).
        hour: Local hour 0–23.
        minute: Local minute 0–59.
        tz: IANA timezone; defaults to system local timezone.

    Returns:
        Five-field cron string ``minute hour * * dow`` in UTC.
    """
    if tz is None:
        tz = local_timezone()
    weekday = normalize_launchd_weekday(weekday)
    python_dow = launchd_to_python_weekday(weekday)
    now = datetime.now(tz)
    days_ahead = (python_dow - now.weekday()) % 7
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )
    if target <= now:
        target += timedelta(days=7)
    utc = target.astimezone(ZoneInfo("UTC"))
    cron_dow = python_to_cron_dow(utc.weekday())
    return f"{utc.minute} {utc.hour} * * {cron_dow}"


def parse_weekly_cron_to_local(
    expr: str,
    tz: ZoneInfo | None = None,
) -> tuple[int, int, int] | None:
    """Parse a simple weekly UTC cron into local launchd weekday, hour, minute.

    Only supports ``minute hour * * dow`` with numeric minute, hour, and dow.
    Returns ``None`` for daily, monthly, or complex expressions.
    """
    if tz is None:
        tz = local_timezone()
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute_s, hour_s, dom_s, month_s, dow_s = parts
    if (
        dom_s != "*"
        or month_s != "*"
        or not all(part.isdigit() for part in (minute_s, hour_s, dow_s))
    ):
        return None
    minute, hour, cron_dow = int(minute_s), int(hour_s), int(dow_s)
    if not (0 <= cron_dow <= 6 and 0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    # Anchor week: 2024-01-07 is Sunday UTC; avoids depending on "now" for DOW.
    anchor_sunday = datetime(2024, 1, 7, hour=hour, minute=minute, second=0, tzinfo=ZoneInfo("UTC"))
    target_utc = anchor_sunday + timedelta(days=cron_dow)
    local = target_utc.astimezone(tz)
    return (
        python_to_launchd_weekday(local.weekday()),
        local.hour,
        local.minute,
    )


def describe_local_schedule(weekday: int, hour: int, minute: int) -> str:
    """Return a short phrase for a launchd local schedule."""
    name = WEEKDAY_PLURAL.get(normalize_launchd_weekday(weekday), f"weekday {weekday}")
    return f"{name} at {hour:02d}:{minute:02d} local time"


def _describe_dow_field(field: str) -> str | None:
    """Return a human phrase for a cron day-of-week field, or ``None`` if unsupported."""
    if field.isdigit():
        return WEEKDAY_PLURAL.get(int(field))
    if "," in field:
        names = [WEEKDAY_PLURAL.get(int(part)) for part in field.split(",") if part.isdigit()]
        if names and all(names):
            if len(names) == 1:
                return names[0]
            return ", ".join(names[:-1]) + f", and {names[-1]}"  # type: ignore[call-overload]
    if "-" in field and not field.startswith("*/"):
        start, end = field.split("-", 1)
        if start.isdigit() and end.isdigit():
            start_name = WEEKDAY_NAMES.get(int(start), start)
            end_name = WEEKDAY_NAMES.get(int(end), end)
            return f"{start_name} through {end_name}"
    return None


def describe_cron_human(expr: str) -> str | None:
    """Return a short human description for common 5-field GitHub Actions cron expressions.

    GitHub Actions evaluates cron in UTC. Only simple fixed minute/hour patterns with
    ``*`` wildcards for month (and usually day-of-month) are translated; complex
    expressions return ``None`` so callers can show the raw cron only.
    """
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute_s, hour_s, dom_s, month_s, dow_s = parts
    if month_s != "*" or not minute_s.isdigit() or not hour_s.isdigit():
        return None

    minute, hour = int(minute_s), int(hour_s)
    time_str = f"{hour:02d}:{minute:02d}"

    if dom_s == "*" and dow_s == "*":
        return f"Daily at {time_str} UTC"

    if dom_s == "*" and dow_s != "*":
        dow_desc = _describe_dow_field(dow_s)
        if dow_desc:
            return f"{dow_desc} at {time_str} UTC"

    if dom_s.isdigit() and dow_s == "*":
        return f"Day {int(dom_s)} of each month at {time_str} UTC"

    return None


def describe_ga_schedule_local(
    weekday: int,
    hour: int,
    minute: int,
    tz: ZoneInfo | None = None,
) -> str:
    """Describe a GA schedule from local picker values, including UTC preview."""
    local_phrase = describe_local_schedule(weekday, hour, minute)
    cron = build_weekly_cron_utc(weekday, hour, minute, tz)
    utc_phrase = describe_cron_human(cron) or f"cron {cron} UTC"
    return f"{local_phrase} → {utc_phrase}"
