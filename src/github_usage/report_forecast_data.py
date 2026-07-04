"""Report-dict adapter for usage forecasts.

Derives a forecast from current usage values already present in a fetched
report dict. The forecast is computed at render/export time so cached reports
never show stale projections.
"""

from __future__ import annotations

from datetime import date

from .forecast import compute_forecast
from .report_helpers import day_of_month, days_in_month


def build_report_forecast(
    report: dict,
    *,
    premium_requests_limit: float | None = None,
    reference_date: date | None = None,
) -> dict | None:
    """Return a forecast dict from ``report`` or ``None`` if not computable.

    Missing ``actions`` / ``copilot`` sections default to ``0.0`` so cached or
    partial reports still render safely. Limits fall back to ``2000`` minutes
    and ``500`` MB when the report does not include them.
    """
    actions = report.get("actions") or {}
    minutes = float(actions.get("minutes") or 0.0)
    storage_avg_mb = float(actions.get("storage_avg_mb") or 0.0)
    minutes_limit = float(actions.get("minutes_limit") or 2000)
    storage_limit_mb = float(actions.get("storage_limit_mb") or 500)

    copilot = report.get("copilot") or {}
    premium_requests = float(copilot.get("total_requests") or 0.0)

    ref = reference_date or date.today()
    return compute_forecast(
        day_of_month=day_of_month(ref),
        days_in_month=days_in_month(ref),
        minutes=minutes,
        minutes_limit=minutes_limit,
        storage_avg_mb=storage_avg_mb,
        storage_limit_mb=storage_limit_mb,
        premium_requests=premium_requests,
        premium_requests_limit=premium_requests_limit,
    )
