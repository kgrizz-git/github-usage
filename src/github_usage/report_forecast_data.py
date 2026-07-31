"""Report-dict adapter for usage forecasts.

Derives a forecast from current usage values already present in a fetched
report dict. The forecast is computed at render/export time so cached reports
never show stale projections.
"""

from __future__ import annotations

from datetime import date

from .forecast import compute_forecast
from .report_helpers import day_of_month, days_in_month
from .usage_split import flat_equivalent_gb_hours


def _private_quota_inputs(actions: dict) -> tuple[float, float]:
    """Return (minutes, storage_avg_mb) preferring private-split keys."""
    if "private_minutes" in actions:
        minutes = float(actions.get("private_minutes") or 0.0)
    else:
        minutes = float(actions.get("minutes") or 0.0)
    if "private_storage_avg_mb" in actions:
        storage_avg_mb = float(actions.get("private_storage_avg_mb") or 0.0)
    else:
        storage_avg_mb = float(actions.get("storage_avg_mb") or 0.0)
    # Under --only-public (filtered + no private), do not project against the
    # free-tier limit — a partial empty private slice is not quota pressure.
    if actions.get("filtered") and float(actions.get("private_minutes") or 0.0) <= 0:
        return 0.0, 0.0
    return minutes, storage_avg_mb


def _attach_forecast_extras(forecast: dict, actions: dict, *, ref: date) -> None:
    """Add public / accrual informational fields onto ``forecast`` in place."""
    if actions.get("public_minutes") is not None:
        forecast["public_minutes"] = float(actions.get("public_minutes") or 0.0)
    if actions.get("public_storage_avg_mb") is not None:
        forecast["public_storage_avg_mb"] = float(actions.get("public_storage_avg_mb") or 0.0)
    if actions.get("private_storage_gb_hours") is not None:
        private_gb = float(actions.get("private_storage_gb_hours") or 0.0)
        dim = days_in_month(ref)
        ratio = dim / day_of_month(ref) if day_of_month(ref) else 1.0
        projected_gb = private_gb * ratio
        forecast["private_gb_hours_projected"] = projected_gb
        forecast["flat_equivalent_mb"] = flat_equivalent_gb_hours(projected_gb, dim) * 1024.0
    if actions.get("filtered") and float(actions.get("private_minutes") or 0.0) <= 0:
        forecast["filtered_empty_private"] = True


def build_report_forecast(
    report: dict,
    *,
    premium_requests_limit: float | None = None,
    reference_date: date | None = None,
) -> dict | None:
    """Return a forecast dict from ``report`` or ``None`` if not computable.

    Prefers ``private_minutes`` / ``private_storage_avg_mb`` when the visibility
    split is present so free-tier projections match private-only quota.
    Missing ``actions`` / ``copilot`` sections default to ``0.0`` so cached or
    partial reports still render safely. Limits fall back to ``2000`` minutes
    and ``500`` MB when the report does not include them.
    """
    actions = report.get("actions") or {}
    minutes, storage_avg_mb = _private_quota_inputs(actions)
    copilot = report.get("copilot") or {}
    premium_requests = float(copilot.get("total_requests") or 0.0)
    ref = reference_date or date.today()
    forecast = compute_forecast(
        day_of_month=day_of_month(ref),
        days_in_month=days_in_month(ref),
        minutes=minutes,
        minutes_limit=float(actions.get("minutes_limit") or 2000),
        storage_avg_mb=storage_avg_mb,
        storage_limit_mb=float(actions.get("storage_limit_mb") or 500),
        premium_requests=premium_requests,
        premium_requests_limit=premium_requests_limit,
    )
    if forecast is None:
        return None
    _attach_forecast_extras(forecast, actions, ref=ref)
    return forecast
