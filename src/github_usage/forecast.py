"""Pure forecast computation for GitHub usage metrics.

Computes end-of-month projections and run-out day estimates from current
usage values, day-of-month trajectory, and known limits. This module has no
I/O, no caching, and no report-structure awareness; see
:mod:`github_usage.report_forecast_data` for the report-dict adapter.
"""

from __future__ import annotations

from math import ceil


def compute_forecast(
    *,
    day_of_month: int,
    days_in_month: int,
    minutes: float,
    minutes_limit: float,
    storage_avg_mb: float,
    storage_limit_mb: float,
    premium_requests: float,
    premium_requests_limit: float | None,
) -> dict | None:
    """Return a forecast dict or ``None`` when projection is not useful.

    Guards:
    - ``day_of_month < 3`` → ``None`` (early-month projections are too volatile).
    - ``day_of_month > days_in_month`` or ``day_of_month < 1`` → ``None``.
    - All three current values are ``0.0`` → ``None``.

    Run-out day for a metric is ``ceil(day_of_month * limit / current_value)``
    when ``current_value > 0`` and the projected value reaches or exceeds the
    limit. It is ``None`` when the metric won't exhaust its limit, the limit is
    unknown, or ``current_value`` is zero.
    """
    if day_of_month < 1 or day_of_month > days_in_month or day_of_month < 3:
        return None
    if not minutes and not storage_avg_mb and not premium_requests:
        return None

    ratio = days_in_month / day_of_month
    projected_minutes = minutes * ratio
    projected_storage_avg_mb = storage_avg_mb * ratio
    projected_premium_requests = premium_requests * ratio

    def _run_out(current: float, limit: float | None, projected: float) -> int | None:
        if current <= 0 or limit is None or limit <= 0:
            return None
        if projected >= limit:
            return int(ceil(day_of_month * limit / current))
        return None

    return {
        "day_of_month": day_of_month,
        "days_in_month": days_in_month,
        "minutes": {
            "current": float(minutes),
            "projected": float(projected_minutes),
            "limit": float(minutes_limit),
            "run_out_day": _run_out(minutes, minutes_limit, projected_minutes),
        },
        "storage_avg_mb": {
            "current": float(storage_avg_mb),
            "projected": float(projected_storage_avg_mb),
            "limit": float(storage_limit_mb),
            "run_out_day": _run_out(storage_avg_mb, storage_limit_mb, projected_storage_avg_mb),
        },
        "premium_requests": {
            "current": float(premium_requests),
            "projected": float(projected_premium_requests),
            "limit": float(premium_requests_limit) if premium_requests_limit is not None else None,
            "run_out_day": _run_out(
                premium_requests, premium_requests_limit, projected_premium_requests
            ),
        },
    }
