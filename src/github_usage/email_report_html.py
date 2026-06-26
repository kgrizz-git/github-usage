"""HTML email report formatter (section formatters + format_html_report)."""

from __future__ import annotations

import html

from ._email_report_common import _bytes_to_mb, _generated_line
from .report_helpers import fmt_price


def _html_cost_row(label: str, cost: dict[str, float]) -> str:
    return (
        f"<tr><td>{html.escape(label)}</td>"
        f"<td>{fmt_price(cost.get('gross', 0.0))}</td>"
        f"<td>{fmt_price(cost.get('discount', 0.0))}</td>"
        f"<td>{fmt_price(cost.get('net', 0.0))}</td></tr>"
    )


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


def _format_html_consumers_section(data: dict) -> list[str]:
    consumers = data.get("repo_consumers")
    if not consumers:
        return []
    parts = [
        "<h2>Top Repositories by Actions Minutes</h2>",
        "<table>",
        "<tr><th>Repo</th><th>Minutes</th><th>Gross</th><th>Storage</th></tr>",
    ]
    for row in consumers.get("by_minutes", []):
        parts.append(
            f"<tr><td>{html.escape(row['repo'])}</td>"
            f"<td>{row['minutes']:,.1f} min</td>"
            f"<td>{fmt_price(row['gross'])}</td>"
            f"<td>{row['storage_avg_mb']:,.1f} MB avg</td></tr>"
        )
    parts.append("</table>")
    parts.append("<h2>Top Repositories by Actions Cost</h2>")
    parts.append("<table>")
    parts.append("<tr><th>Repo</th><th>Gross</th><th>Minutes</th><th>Storage</th></tr>")
    for row in consumers.get("by_cost", []):
        parts.append(
            f"<tr><td>{html.escape(row['repo'])}</td>"
            f"<td>{fmt_price(row['gross'])}</td>"
            f"<td>{row['minutes']:,.1f} min</td>"
            f"<td>{row['storage_avg_mb']:,.1f} MB avg</td></tr>"
        )
    parts.append("</table>")
    if consumers.get("truncated"):
        parts.append(
            f"<p><em>Repo list truncated at {consumers.get('max_repos')} repositories.</em></p>"
        )
    return parts


def _format_html_artifact_storage_section(data: dict) -> list[str]:
    artifact_storage = data.get("artifact_storage")
    if not artifact_storage:
        return []
    parts = [
        "<h2>Actions Artifact Storage</h2>",
        "<ul>",
    ]
    for row in artifact_storage.get("top_repos", []):
        parts.append(
            f"<li>{html.escape(row['repo'])}: "
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
    parts = [
        "<h2>Release Asset Inventory</h2>",
        "<ul>",
    ]
    for row in release_assets.get("top_repos", []):
        parts.append(
            f"<li>{html.escape(row['repo'])}: "
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


_SECTION_HTML_FORMATTERS = (
    _format_html_actions_section,
    _format_html_copilot_section,
    _format_html_git_lfs_section,
    _format_html_monthly_costs_section,
    _format_html_consumers_section,
    _format_html_artifact_storage_section,
    _format_html_release_assets_section,
    _format_html_insights_section,
    _format_html_errors_section,
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
    "  </style>\n"
    "</head>\n"
    "<body>\n"
)
_HTML_DOCUMENT_TAIL = "</body>\n</html>\n"


def format_html_report(data: dict) -> str:
    """Format report data as an HTML email body."""
    username = html.escape(data.get("username") or "?")
    parts: list[str] = [_HTML_DOCUMENT_HEAD]
    parts.append(f"<h1>GitHub Usage Report for {username}</h1>")
    parts.append(f'<p class="meta">{html.escape(_generated_line(data.get("generated_at")))}</p>')
    parts.append('<p class="meta">Period: current month</p>')

    warnings = data.get("warnings") or []
    if warnings:
        parts.append('<div class="warning"><strong>Warnings</strong><ul>')
        for warning in warnings:
            parts.append(f"<li>{html.escape(warning)}</li>")
        parts.append("</ul></div>")

    for formatter in _SECTION_HTML_FORMATTERS:
        parts.extend(formatter(data))

    estimate = data.get("api_estimate") or {}
    notes = estimate.get("notes") or []
    if notes:
        parts.append("<h2>REST API Quota Notes</h2>")
        parts.append("<ul>")
        for note in notes:
            parts.append(f"<li>{html.escape(note)}</li>")
        parts.append("</ul>")

    parts.append(_HTML_DOCUMENT_TAIL)
    return "".join(parts)
