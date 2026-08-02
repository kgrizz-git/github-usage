"""Shared report formatting helpers."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from .visibility import visibility_label


def repo_label(full: str, visibility_by_repo: dict[str, str] | None) -> str:
    """Return ``full`` with a visibility tag when ``visibility_by_repo`` is provided."""
    if not visibility_by_repo:
        return full
    return f"{full}{visibility_label(visibility_by_repo.get(full, 'public'))}"


def hours_in_month(reference_date: date | None = None) -> int:
    """Return the number of hours in the reference date's calendar month."""
    today = reference_date or date.today()
    first_day = today.replace(day=1)
    next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (next_month - first_day).days * 24


def days_in_month(reference_date: date | None = None) -> int:
    """Return the number of days in the reference date's calendar month."""
    today = reference_date or date.today()
    return calendar.monthrange(today.year, today.month)[1]


def day_of_month(reference_date: date | None = None) -> int:
    """Return the day of the month for the reference date."""
    today = reference_date or date.today()
    return today.day


def gb_hours_to_avg_mb(gb_hours: float, reference_date: date | None = None) -> float:
    """Convert GB-hours for a month into average MB stored."""
    hours = hours_in_month(reference_date)
    return (gb_hours / hours) * 1024 if hours > 0 else 0.0


def fmt_price(value: float) -> str:
    """Format a dollar value consistently across reports."""
    return f"${value:.4f}"


def sanitize_item_amounts(item: dict) -> dict:
    """Return a copy with grossAmount/discountAmount/netAmount/grossQuantity None replaced by 0.0.

    Used at the *storage* site of billing-item dicts (where the raw API item
    is stored in a returned ``items`` or ``sku_breakdown`` dict). After
    sanitization, downstream consumers can trust the items and need no
    defensive ``.get(key, 0)`` defaults.
    """
    sanitized = dict(item)
    for key in ("grossAmount", "discountAmount", "netAmount", "grossQuantity"):
        if sanitized.get(key) is None:
            sanitized[key] = 0.0
    return sanitized
