"""Terminal rendering for the render-time usage forecast."""

from __future__ import annotations

from .report_forecast_data import build_report_forecast
from .terminal import print_header, print_sep


def render_forecast(
    data: dict,
    *,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> None:
    """Print the monthly usage forecast section for the legacy report."""
    forecast = build_report_forecast(
        data,
        premium_requests_limit=premium_requests_limit,
        reference_date=reference_date,
    )
    if forecast is None:
        return

    print_header()
    print_sep("Monthly Forecast")
    print(
        f"Day {forecast['day_of_month']} of {forecast['days_in_month']} "
        "(current → projected at month-end)"
    )

    def _limit(value: float | None) -> str:
        return f"{value:,.0f}" if value is not None else "--"

    def _run_out(value: int | None) -> str:
        return f"day {value}" if value is not None else "--"

    rows = [
        ("Actions Minutes", forecast["minutes"]),
        ("Storage (avg MB)", forecast["storage_avg_mb"]),
        ("Premium Requests", forecast["premium_requests"]),
    ]
    for label, metric in rows:
        print(
            f"  {label:18} "
            f"current {metric['current']:>10,.1f}  "
            f"projected {metric['projected']:>10,.1f}  "
            f"limit {_limit(metric['limit']):>8}  "
            f"run-out {_run_out(metric['run_out_day']):>8}"
        )
    if forecast.get("filtered_empty_private"):
        print("  (filtered scan with no private minutes — private free-tier projection suppressed)")
    if forecast.get("public_minutes"):
        print(f"  {'Public (free)':18} current {float(forecast['public_minutes']):>10,.1f} min")
    print()
