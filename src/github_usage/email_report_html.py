"""HTML email report formatter (section formatters + format_html_report)."""

from __future__ import annotations

import html

from ._email_report_common import _bytes_to_mb, _generated_line
from ._email_report_html_tables import (
    html_cost_consumer_row,
    html_flat_table,
    html_grouped_table,
    html_minutes_row,
    html_repo_cell,
    html_storage_row,
    html_workflow_breakdown_table,
)
from .repo_consumers import private_list_is_redundant
from .report_forecast_data import build_report_forecast
from .report_helpers import fmt_price
from .visibility import (
    group_by_visibility,
    visibility_group_header,
)


def _html_cost_row(label: str, cost: dict[str, float]) -> str:
    return (
        f"<tr><td>{html.escape(label)}</td>"
        f"<td>{fmt_price(cost.get('gross', 0.0))}</td>"
        f"<td>{fmt_price(cost.get('discount', 0.0))}</td>"
        f"<td>{fmt_price(cost.get('net', 0.0))}</td></tr>"
    )


_BILLING_CONTEXT_URL = "https://docs.github.com/en/billing/concepts/product-billing/github-actions"


def _format_html_billing_context_section(data: dict) -> list[str]:
    return [
        "<h2>Billing Note</h2>",
        "<ul>",
        "<li>Actions minutes and storage are free for public repositories.</li>",
        "<li>Private and internal repositories consume your plan's monthly quota.</li>",
        f'<li>See <a href="{_BILLING_CONTEXT_URL}">GitHub Actions billing</a> for details.</li>',
        "</ul>",
    ]


def _format_html_actions_section(data: dict) -> list[str]:
    actions = data.get("actions")
    if not actions:
        return []
    net = (data.get("monthly_costs") or {}).get("actions", {}).get("net", 0.0)
    return [
        "<h2>Actions</h2>",
        "<table>",
        "<tr><th>Metric</th><th>Value</th></tr>",
        (
            f"<tr><td>Minutes</td><td>{actions.get('minutes', 0.0):,.1f} / "
            f"{actions.get('minutes_limit', 0):,} "
            f"({actions.get('minutes_percent', 0.0):.1f}%)</td></tr>"
        ),
        (
            f"<tr><td>Storage</td><td>{actions.get('storage_avg_mb', 0.0):,.1f} MB / "
            f"{actions.get('storage_limit_mb', 0):,} MB "
            f"({actions.get('storage_percent', 0.0):.1f}%)</td></tr>"
        ),
        f"<tr><td>Net cost</td><td>{fmt_price(net)}</td></tr>",
        "</table>",
    ]


def _format_html_copilot_section(data: dict) -> list[str]:
    copilot = data.get("copilot")
    if not copilot:
        return []
    parts = [
        "<h2>Copilot Premium Requests</h2>",
        "<ul>",
        f"<li>Total requests: {copilot.get('total_requests', 0.0):,.1f}</li>",
        f"<li>Net cost: {fmt_price(copilot.get('total_net', 0.0))}</li>",
    ]
    by_model = copilot.get("by_model") or {}
    if by_model:
        parts.append("</ul>")
        parts.append("<h3>By model</h3>")
        parts.append("<ul>")
        for model, values in sorted(by_model.items()):
            requests = values.get("requests", values.get("total_requests", 0.0))
            parts.append(f"<li>{html.escape(model)}: {requests:,.1f} requests</li>")
    parts.append("</ul>")
    return parts


def _format_html_git_lfs_section(data: dict) -> list[str]:
    git_lfs = data.get("git_lfs")
    if not git_lfs:
        return []
    return [
        "<h2>Git LFS</h2>",
        f"<p>Net cost: {fmt_price(git_lfs.get('total_net', 0.0))}</p>",
    ]


def _format_html_monthly_costs_section(data: dict) -> list[str]:
    monthly = data.get("monthly_costs") or {}
    if not monthly:
        return []
    rows = []
    for key, label in [
        ("actions", "Actions"),
        ("copilot", "Copilot"),
        ("git_lfs", "Git LFS"),
        ("total", "Total"),
    ]:
        rows.append(_html_cost_row(label, monthly.get(key, {})))
    return [
        "<h2>Monthly Cost Estimate</h2>",
        "<table>",
        "<tr><th>Category</th><th>Gross</th><th>Discount</th><th>Net</th></tr>",
        *rows,
        "</table>",
    ]


def _html_private_public_summary(by_vis: dict) -> list[str]:
    priv = by_vis.get("private") or {}
    pub = by_vis.get("public") or {}
    priv_min = float(priv.get("minutes", 0.0) or 0.0)
    pub_min = float(pub.get("minutes", 0.0) or 0.0)
    priv_mb = float(priv.get("storage_avg_mb", 0.0) or 0.0)
    pub_mb = float(pub.get("storage_avg_mb", 0.0) or 0.0)
    pct = (priv_min / 2000.0 * 100.0) if priv_min else 0.0
    return [
        "<h2>Private vs public Actions</h2>",
        '<p class="visibility-tag">'
        f"Private: {priv_min:,.1f} min / 2,000 free ({pct:.0f}%) · "
        f"{priv_mb:,.1f} MB avg · Public: {pub_min:,.1f} min (free) · "
        f"{pub_mb:,.1f} MB avg (free)"
        "</p>",
        '<p class="visibility-tag">Retention: 90 days default; artifacts auto-expire.</p>',
    ]


def _format_html_consumers_section(data: dict) -> list[str]:
    consumers = data.get("repo_consumers")
    if not consumers:
        return []
    parts: list[str] = []
    by_vis = consumers.get("by_visibility")
    if by_vis:
        parts.extend(_html_private_public_summary(by_vis))
    by_minutes = consumers.get("by_minutes") or []
    parts.extend(
        html_grouped_table(
            "Top Repositories by Actions Minutes",
            by_minutes,
            headers=["Repo", "Minutes", "Gross", "Storage"],
            value_fn=html_minutes_row,
        )
    )
    parts.extend(
        html_grouped_table(
            "Top Repositories by Actions Cost",
            consumers.get("by_cost", []),
            headers=["Repo", "Gross", "Minutes", "Storage"],
            value_fn=html_cost_consumer_row,
        )
    )
    by_storage = consumers.get("by_storage") or []
    if by_storage:
        parts.extend(
            html_grouped_table(
                "Top Repositories by Actions Storage (all)",
                by_storage,
                headers=["Repo", "Storage", "Minutes", "Gross"],
                value_fn=html_storage_row,
            )
        )
    by_minutes_private = consumers.get("by_minutes_private") or []
    if by_minutes_private and not private_list_is_redundant(by_minutes, by_minutes_private):
        parts.extend(
            html_flat_table(
                "Top Private Repositories by Actions Minutes",
                by_minutes_private,
                headers=["Repo", "Minutes", "Gross", "Storage"],
                value_fn=html_minutes_row,
            )
        )
    by_storage_private = consumers.get("by_storage_private") or []
    if by_storage_private and not private_list_is_redundant(by_storage, by_storage_private):
        parts.extend(
            html_flat_table(
                "Top Private Repositories by Actions Storage",
                by_storage_private,
                headers=["Repo", "Storage", "Minutes", "Gross"],
                value_fn=html_storage_row,
            )
        )
    if consumers.get("truncated"):
        parts.append(
            f"<p><em>Repo list truncated at {consumers.get('max_repos')} repositories.</em></p>"
        )
    return parts


def _format_html_workflow_breakdown_section(data: dict) -> list[str]:
    breakdown = data.get("workflow_breakdown")
    if not breakdown:
        return []
    return html_workflow_breakdown_table(breakdown, limit=5)


def _format_html_artifact_storage_section(data: dict) -> list[str]:
    artifact_storage = data.get("artifact_storage")
    if not artifact_storage:
        return []
    repos = artifact_storage.get("top_repos", [])
    parts = ["<h2>Actions Artifact Storage</h2>"]
    groups = group_by_visibility(repos)
    if len(groups) <= 1:
        parts.append("<ul>")
        for row in repos:
            parts.append(
                f"<li>{html_repo_cell(row)}: "
                f"{_bytes_to_mb(row['artifact_bytes']):,.1f} MB artifacts</li>"
            )
        parts.append("</ul>")
    else:
        for vis, group_rows in groups.items():
            parts.append(f"<h3>{html.escape(visibility_group_header(vis))}</h3>")
            parts.append("<ul>")
            for row in group_rows:
                parts.append(
                    f"<li>{html_repo_cell(row)}: "
                    f"{_bytes_to_mb(row['artifact_bytes']):,.1f} MB artifacts</li>"
                )
            parts.append("</ul>")
    if artifact_storage.get("truncated"):
        parts.append(
            f"<p><em>Artifact scan truncated at "
            f"{artifact_storage.get('max_repos')} repositories.</em></p>"
        )
    return parts


def _format_html_release_assets_section(data: dict) -> list[str]:
    release_assets = data.get("release_assets")
    if not release_assets:
        return []
    repos = release_assets.get("top_repos", [])
    parts = ["<h2>Release Asset Inventory</h2>"]
    groups = group_by_visibility(repos)
    if len(groups) <= 1:
        parts.append("<ul>")
        for row in repos:
            parts.append(
                f"<li>{html_repo_cell(row)}: "
                f"{_bytes_to_mb(row['release_asset_bytes']):,.1f} MB release assets</li>"
            )
        parts.append("</ul>")
    else:
        for vis, group_rows in groups.items():
            parts.append(f"<h3>{html.escape(visibility_group_header(vis))}</h3>")
            parts.append("<ul>")
            for row in group_rows:
                parts.append(
                    f"<li>{html_repo_cell(row)}: "
                    f"{_bytes_to_mb(row['release_asset_bytes']):,.1f} MB release assets</li>"
                )
            parts.append("</ul>")
    if release_assets.get("truncated"):
        parts.append(
            f"<p><em>Release asset scan truncated at "
            f"{release_assets.get('max_repos')} repositories.</em></p>"
        )
    return parts


def _format_html_insights_section(data: dict) -> list[str]:
    insights = data.get("insights") or []
    if not insights:
        return []
    return [
        "<h2>Key Insights</h2>",
        "<ul>",
        *[f"<li>{html.escape(insight)}</li>" for insight in insights],
        "</ul>",
    ]


def _format_html_errors_section(data: dict) -> list[str]:
    errors = data.get("errors") or {}
    if not errors:
        return []
    parts = ["<h2>Unavailable Data</h2>", "<ul>"]
    for section, message in sorted(errors.items()):
        parts.append(
            f"<li>{html.escape(section.replace('_', ' ').title())} "
            f"data unavailable - {html.escape(message)}</li>"
        )
    parts.append("</ul>")
    return parts


def _format_html_forecast_section(
    data: dict,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> list[str]:
    """Format the monthly usage forecast as an HTML table."""
    if not include_forecast:
        return []
    forecast = build_report_forecast(
        data,
        premium_requests_limit=premium_requests_limit,
        reference_date=reference_date,
    )
    if forecast is None:
        return []

    def _limit(value: float | None) -> str:
        return f"{value:,.0f}" if value is not None else "--"

    def _run_out(value: int | None) -> str:
        return f"day {value}" if value is not None else "--"

    has_split = "public_minutes" in forecast
    scope_note = (
        ' <span class="visibility-tag">(private repos — quota-counted)</span>' if has_split else ""
    )

    rows = [
        ("Actions Minutes", forecast["minutes"]),
        ("Storage (avg MB)", forecast["storage_avg_mb"]),
        ("Premium Requests", forecast["premium_requests"]),
    ]

    parts = [
        f"<h2>Monthly Forecast{scope_note}</h2>",
        (f"<p>Day {forecast['day_of_month']} of {forecast['days_in_month']}</p>"),
        "<table>",
        "<tr><th>Metric</th><th>Current</th><th>Projected</th><th>Limit</th><th>Run-out</th></tr>",
    ]
    for label, metric in rows:
        parts.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{metric['current']:,.1f}</td>"
            f"<td>{metric['projected']:,.1f}</td>"
            f"<td>{_limit(metric['limit'])}</td>"
            f"<td>{html.escape(_run_out(metric['run_out_day']))}</td>"
            "</tr>"
        )
    parts.append("</table>")
    if has_split:
        pub_min = float(forecast.get("public_minutes") or 0.0)
        pub_mb = float(forecast.get("public_storage_avg_mb") or 0.0)
        if pub_min > 0 or pub_mb > 0:
            storage_part = f" · {pub_mb:,.1f} MB avg storage" if pub_mb > 0 else ""
            parts.append(
                f'<p class="visibility-tag">+ Public repos (free): '
                f"{pub_min:,.1f} min{html.escape(storage_part)}</p>"
            )
    return parts


_SECTION_HTML_FORMATTERS = (
    _format_html_billing_context_section,
    _format_html_actions_section,
    _format_html_copilot_section,
    _format_html_git_lfs_section,
    _format_html_monthly_costs_section,
    _format_html_consumers_section,
    _format_html_workflow_breakdown_section,
    _format_html_artifact_storage_section,
    _format_html_release_assets_section,
    _format_html_insights_section,
    _format_html_errors_section,
    _format_html_forecast_section,
)


_HTML_DOCUMENT_HEAD = (
    "<!DOCTYPE html>\n"
    '<html lang="en">\n'
    "<head>\n"
    '  <meta charset="utf-8">\n'
    "  <title>GitHub Usage Report</title>\n"
    "  <style>\n"
    '    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; margin: 0; padding: 20px; color: #24292f; }\n'
    "    h1 { font-size: 20px; border-bottom: 1px solid #d0d7de; padding-bottom: 8px; }\n"
    "    h2 { font-size: 16px; margin-top: 20px; }\n"
    "    h3 { font-size: 14px; margin-top: 12px; }\n"
    "    table { border-collapse: collapse; width: 100%; margin: 8px 0; }\n"
    "    th, td { text-align: left; padding: 6px 10px; border: 1px solid #d0d7de; }\n"
    "    th { background: #f6f8fa; }\n"
    "    ul { padding-left: 20px; }\n"
    "    .warning { background: #fff8c5; border: 1px solid #d4a72c; padding: 8px; border-radius: 4px; }\n"
    "    .meta, p em { color: #656d76; }\n"
    "    .meta { font-size: 14px; }\n"
    "    .visibility-tag { color: #656d76; font-weight: normal; }\n"
    "  </style>\n"
    "</head>\n"
    "<body>\n"
)
_HTML_DOCUMENT_TAIL = "</body>\n</html>\n"


def _html_warning_block(warnings: list) -> list[str]:
    if not warnings:
        return []
    parts = ['<div class="warning"><strong>Warnings</strong><ul>']
    for warning in warnings:
        parts.append(f"<li>{html.escape(warning)}</li>")
    parts.append("</ul></div>")
    return parts


def _html_api_notes_block(estimate: dict) -> list[str]:
    notes = estimate.get("notes") or []
    if not notes:
        return []
    parts = ["<h2>REST API Quota Notes</h2>", "<ul>"]
    for note in notes:
        parts.append(f"<li>{html.escape(note)}</li>")
    parts.append("</ul>")
    return parts


def _html_sources_block(sources: dict) -> list[str]:
    if not sources:
        return []
    parts = ['<h2>Sources</h2><ul class="visibility-tag">']
    for key, label in (
        ("actions_billing", "Actions billing"),
        ("runner_pricing", "Runner pricing"),
        ("releases_storage", "Release assets"),
    ):
        url = sources.get(key)
        if not url:
            continue
        parts.append(
            f"<li>{html.escape(label)}: "
            f'<a href="{html.escape(str(url))}">{html.escape(str(url))}</a></li>'
        )
    parts.append("</ul>")
    return parts


def format_html_report(
    data: dict,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> str:
    """Format report data as an HTML email body."""
    username = html.escape(data.get("username") or "?")
    parts: list[str] = [_HTML_DOCUMENT_HEAD]
    parts.append(f"<h1>GitHub Usage Report for {username}</h1>")
    parts.append(f'<p class="meta">{html.escape(_generated_line(data.get("generated_at")))}</p>')
    parts.append('<p class="meta">Period: current month</p>')
    parts.extend(_html_warning_block(data.get("warnings") or []))
    for formatter in _SECTION_HTML_FORMATTERS:
        if formatter is _format_html_forecast_section:
            parts.extend(
                formatter(
                    data,
                    include_forecast=include_forecast,  # type: ignore[call-arg]
                    premium_requests_limit=premium_requests_limit,  # type: ignore[call-arg]
                    reference_date=reference_date,  # type: ignore[call-arg]
                )
            )
        else:
            parts.extend(formatter(data))
    parts.extend(_html_api_notes_block(data.get("api_estimate") or {}))
    parts.extend(_html_sources_block(data.get("sources") or {}))
    parts.append(_HTML_DOCUMENT_TAIL)
    return "".join(parts)
