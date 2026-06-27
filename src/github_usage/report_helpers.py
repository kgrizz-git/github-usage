"""Shared report formatting helpers."""

from __future__ import annotations

from datetime import date, timedelta


def hours_in_month(reference_date: date | None = None) -> int:
    """Return the number of hours in the reference date's calendar month."""
    today = reference_date or date.today()
    first_day = today.replace(day=1)
    next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (next_month - first_day).days * 24


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
