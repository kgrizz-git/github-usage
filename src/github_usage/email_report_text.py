"""Plain-text email report formatter (section formatters + format_report_email)."""

from __future__ import annotations

from ._email_report_common import _bytes_to_mb, _generated_line
from .report_forecast_data import build_report_forecast
from .report_helpers import fmt_price
from .visibility import (
    group_by_visibility,
    repo_visibility,
    visibility_group_header,
    visibility_label,
)


def _annotated_repo_name(row: dict) -> str:
    return f"{row['repo']}{visibility_label(repo_visibility(row))}"


def _cost_line(label: str, cost: dict[str, float]) -> str:
    return (
        f"- {label}: gross {fmt_price(cost.get('gross', 0.0))}, "
        f"discount {fmt_price(cost.get('discount', 0.0))}, "
        f"net {fmt_price(cost.get('net', 0.0))}"
    )


_BILLING_CONTEXT_URL = "https://docs.github.com/en/billing/concepts/product-billing/github-actions"


def _format_billing_context_section(data: dict) -> list[str]:
    return [
        "Billing Note",
        "- Actions minutes and storage are free for public repositories.",
        "- Private and internal repositories consume your plan's monthly quota.",
        f"- See {_BILLING_CONTEXT_URL} for details.",
        "",
    ]


def _format_actions_section(data: dict) -> list[str]:
    actions = data.get("actions")
    if not actions:
        return []
    net = (data.get("monthly_costs") or {}).get("actions", {}).get("net", 0.0)
    return [
        "Actions",
        (
            f"- Minutes: {actions.get('minutes', 0.0):,.1f} / "
            f"{actions.get('minutes_limit', 0):,} "
            f"({actions.get('minutes_percent', 0.0):.1f}%)"
        ),
        (
            f"- Storage: {actions.get('storage_avg_mb', 0.0):,.1f} MB / "
            f"{actions.get('storage_limit_mb', 0):,} MB "
            f"({actions.get('storage_percent', 0.0):.1f}%)"
        ),
        f"- Net cost: {fmt_price(net)}",
        "",
    ]


def _format_copilot_section(data: dict) -> list[str]:
    copilot = data.get("copilot")
    if not copilot:
        return []
    lines = [
        "Copilot Premium Requests",
        f"- Total requests: {copilot.get('total_requests', 0.0):,.1f}",
        f"- Net cost: {fmt_price(copilot.get('total_net', 0.0))}",
    ]
    by_model = copilot.get("by_model") or {}
    if by_model:
        lines.append("- By model:")
        for model, values in sorted(by_model.items()):
            requests = values.get("requests", values.get("total_requests", 0.0))
            lines.append(f"  - {model}: {requests:,.1f} requests")
    lines.append("")
    return lines


def _format_git_lfs_section(data: dict) -> list[str]:
    git_lfs = data.get("git_lfs")
    if not git_lfs:
        return []
    return ["Git LFS", f"- Net cost: {fmt_price(git_lfs.get('total_net', 0.0))}", ""]


def _format_monthly_costs_section(data: dict) -> list[str]:
    monthly = data.get("monthly_costs") or {}
    if not monthly:
        return []
    lines = ["Monthly Cost Estimate"]
    for key, label in [
        ("actions", "Actions"),
        ("copilot", "Copilot"),
        ("git_lfs", "Git LFS"),
        ("total", "Total"),
    ]:
        lines.append(_cost_line(label, monthly.get(key, {})))
    lines.append("")
    return lines


def _visibility_usage_summary_lines(consumers: dict) -> list[str]:
    """Private/public totals block prepended above grouped consumer lists."""
    by_vis = consumers.get("by_visibility")
    if not by_vis:
        return []
    priv = by_vis.get("private") or {}
    pub = by_vis.get("public") or {}
    priv_min = float(priv.get("minutes", 0.0) or 0.0)
    pub_min = float(pub.get("minutes", 0.0) or 0.0)
    priv_mb = float(priv.get("storage_avg_mb", 0.0) or 0.0)
    pct = (priv_min / 2000.0 * 100.0) if priv_min else 0.0
    return [
        "Private vs public Actions (scanned repos)",
        f"- Private repos:  {priv_min:,.1f} min / 2,000 free ({pct:.0f}%) · {priv_mb:,.1f} MB avg storage",
        f"- Public repos:   {pub_min:,.1f} min (free)",
        "- Artifacts:      retention defaults to 90 days; artifacts auto-expire.",
        "",
    ]


def _format_consumers_section(data: dict) -> list[str]:
    consumers = data.get("repo_consumers")
    if not consumers:
        return []

    def _grouped_list(title: str, rows: list[dict], *, value_fn) -> list[str]:
        lines = [title]
        groups = group_by_visibility(rows)
        if len(groups) <= 1:
            for row in rows:
                lines.append(f"- {_annotated_repo_name(row)}: {value_fn(row)}")
        else:
            for vis, group_rows in groups.items():
                lines.append(f"\n  {visibility_group_header(vis)}")
                for row in group_rows:
                    lines.append(f"  - {_annotated_repo_name(row)}: {value_fn(row)}")
        return lines

    def _minutes_value(r: dict) -> str:
        return (
            f"{r['minutes']:,.1f} min, "
            f"{fmt_price(r['gross'])}, {r['storage_avg_mb']:,.1f} MB avg storage"
        )

    def _cost_value(r: dict) -> str:
        return (
            f"{fmt_price(r['gross'])}, "
            f"{r['minutes']:,.1f} min, {r['storage_avg_mb']:,.1f} MB avg storage"
        )

    lines: list[str] = []
    lines.extend(_visibility_usage_summary_lines(consumers))
    lines.extend(
        _grouped_list(
            "Top Repositories by Actions Minutes",
            consumers.get("by_minutes", []),
            value_fn=_minutes_value,
        )
    )
    lines.append("")
    lines.extend(
        _grouped_list(
            "Top Repositories by Actions Cost", consumers.get("by_cost", []), value_fn=_cost_value
        )
    )
    if consumers.get("truncated"):
        lines.append(f"- Repo list truncated at {consumers.get('max_repos')} repositories.")
    lines.append("")
    return lines


def _format_artifact_storage_section(data: dict) -> list[str]:
    artifact_storage = data.get("artifact_storage")
    if not artifact_storage:
        return []
    repos = artifact_storage.get("top_repos", [])
    lines = ["Actions Artifact Storage"]
    groups = group_by_visibility(repos)
    if len(groups) <= 1:
        for row in repos:
            lines.append(
                f"- {_annotated_repo_name(row)}: {_bytes_to_mb(row['artifact_bytes']):,.1f} MB artifacts"
            )
    else:
        for vis, group_rows in groups.items():
            lines.append(f"\n  {visibility_group_header(vis)}")
            for row in group_rows:
                lines.append(
                    f"  - {_annotated_repo_name(row)}: {_bytes_to_mb(row['artifact_bytes']):,.1f} MB artifacts"
                )
    if artifact_storage.get("truncated"):
        lines.append(
            f"- Artifact scan truncated at {artifact_storage.get('max_repos')} repositories."
        )
    lines.append("")
    return lines


def _format_release_assets_section(data: dict) -> list[str]:
    release_assets = data.get("release_assets")
    if not release_assets:
        return []
    repos = release_assets.get("top_repos", [])
    lines = ["Release Asset Inventory"]
    groups = group_by_visibility(repos)
    if len(groups) <= 1:
        for row in repos:
            lines.append(
                f"- {_annotated_repo_name(row)}: "
                f"{_bytes_to_mb(row['release_asset_bytes']):,.1f} MB release assets"
            )
    else:
        for vis, group_rows in groups.items():
            lines.append(f"\n  {visibility_group_header(vis)}")
            for row in group_rows:
                lines.append(
                    f"  - {_annotated_repo_name(row)}: "
                    f"{_bytes_to_mb(row['release_asset_bytes']):,.1f} MB release assets"
                )
    if release_assets.get("truncated"):
        lines.append(
            f"- Release asset scan truncated at {release_assets.get('max_repos')} repositories."
        )
    lines.append("")
    return lines


def _format_insights_section(data: dict) -> list[str]:
    insights = data.get("insights") or []
    if not insights:
        return []
    return ["Key Insights", *[f"- {insight}" for insight in insights], ""]


def _format_errors_section(data: dict) -> list[str]:
    errors = data.get("errors") or {}
    if not errors:
        return []
    lines = ["Unavailable Data"]
    for section, message in sorted(errors.items()):
        lines.append(f"- {section.replace('_', ' ').title()} data unavailable - {message}")
    lines.append("")
    return lines


def _format_forecast_section(
    data: dict,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> list[str]:
    """Format the monthly usage forecast as an aligned text table."""
    if not include_forecast:
        return []
    forecast = build_report_forecast(
        data,
        premium_requests_limit=premium_requests_limit,
        reference_date=reference_date,
    )
    if forecast is None:
        return []

    lines = [
        f"Monthly Forecast (day {forecast['day_of_month']} of {forecast['days_in_month']})",
        "───────────────────────────────────────────",
        "Metric              Current    Projected  Limit    Run-out",
    ]

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
        lines.append(
            f"{label:19} {metric['current']:>9,.1f} {metric['projected']:>10,.1f} "
            f"{_limit(metric['limit']):>8} {_run_out(metric['run_out_day']):>8}"
        )
    lines.append("")
    return lines


_SECTION_FORMATTERS = (
    _format_billing_context_section,
    _format_actions_section,
    _format_copilot_section,
    _format_git_lfs_section,
    _format_monthly_costs_section,
    _format_consumers_section,
    _format_artifact_storage_section,
    _format_release_assets_section,
    _format_insights_section,
    _format_errors_section,
    _format_forecast_section,
)


def format_report_email(
    data: dict,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> str:
    """Format report data as a plain-text email body."""
    lines = [
        f"GitHub Usage Report for {data.get('username', '?')}",
        _generated_line(data.get("generated_at")),
        "Period: current month",
        "",
    ]

    warnings = data.get("warnings") or []
    if warnings:
        lines.extend(["WARNING", *[f"- {warning}" for warning in warnings], ""])

    for formatter in _SECTION_FORMATTERS:
        if formatter is _format_forecast_section:
            lines.extend(
                formatter(
                    data,
                    include_forecast=include_forecast,  # type: ignore[call-arg]
                    premium_requests_limit=premium_requests_limit,  # type: ignore[call-arg]
                    reference_date=reference_date,  # type: ignore[call-arg]
                )
            )
        else:
            lines.extend(formatter(data))

    estimate = data.get("api_estimate") or {}
    notes = estimate.get("notes") or []
    if notes:
        lines.extend(["REST API Quota Notes", *[f"- {note}" for note in notes], ""])

    sources = data.get("sources") or {}
    if sources:
        lines.extend(
            [
                "Sources",
                f"- Actions billing: {sources.get('actions_billing', '')}",
                f"- Runner pricing: {sources.get('runner_pricing', '')}",
                f"- Release assets: {sources.get('releases_storage', '')}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"
