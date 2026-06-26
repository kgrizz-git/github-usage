"""Email report formatting (plain-text and HTML) and Resend delivery."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime

from .report_helpers import fmt_price


def default_subject(username: str, generated_at: str | None = None) -> str:
    """Return the default email subject."""
    day = generated_at[:10] if generated_at else datetime.now(tz=UTC).date().isoformat()
    return f"GitHub Usage Report for {username} - {day}"


def _generated_line(generated_at: str | None) -> str:
    if not generated_at:
        return f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}"
    if generated_at.endswith("Z"):
        generated_at = generated_at[:-1] + "+00:00"
    try:
        generated = datetime.fromisoformat(generated_at).astimezone(UTC)
    except ValueError:
        return f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}"
    return f"Generated: {generated.strftime('%Y-%m-%d %H:%M UTC')}"


def _bytes_to_mb(value: int | float) -> float:
    return float(value) / (1024 * 1024)


def _cost_line(label: str, cost: dict[str, float]) -> str:
    return (
        f"- {label}: gross {fmt_price(cost.get('gross', 0.0))}, "
        f"discount {fmt_price(cost.get('discount', 0.0))}, "
        f"net {fmt_price(cost.get('net', 0.0))}"
    )


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


def _format_consumers_section(data: dict) -> list[str]:
    consumers = data.get("repo_consumers")
    if not consumers:
        return []
    lines = ["Top Repositories by Actions Minutes"]
    for row in consumers.get("by_minutes", []):
        lines.append(
            f"- {row['repo']}: {row['minutes']:,.1f} min, "
            f"{fmt_price(row['gross'])}, {row['storage_avg_mb']:,.1f} MB avg storage"
        )
    lines.extend(["", "Top Repositories by Actions Cost"])
    for row in consumers.get("by_cost", []):
        lines.append(
            f"- {row['repo']}: {fmt_price(row['gross'])}, "
            f"{row['minutes']:,.1f} min, {row['storage_avg_mb']:,.1f} MB avg storage"
        )
    if consumers.get("truncated"):
        lines.append(f"- Repo list truncated at {consumers.get('max_repos')} repositories.")
    lines.append("")
    return lines


def _format_artifact_storage_section(data: dict) -> list[str]:
    artifact_storage = data.get("artifact_storage")
    if not artifact_storage:
        return []
    lines = ["Actions Artifact Storage"]
    for row in artifact_storage.get("top_repos", []):
        lines.append(f"- {row['repo']}: {_bytes_to_mb(row['artifact_bytes']):,.1f} MB artifacts")
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
    lines = ["Release Asset Inventory"]
    for row in release_assets.get("top_repos", []):
        lines.append(
            f"- {row['repo']}: {_bytes_to_mb(row['release_asset_bytes']):,.1f} MB release assets"
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


_SECTION_FORMATTERS = (
    _format_actions_section,
    _format_copilot_section,
    _format_git_lfs_section,
    _format_monthly_costs_section,
    _format_consumers_section,
    _format_artifact_storage_section,
    _format_release_assets_section,
    _format_insights_section,
    _format_errors_section,
)


def format_report_email(data: dict) -> str:
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
        lines.extend(formatter(data))

    estimate = data.get("api_estimate") or {}
    notes = estimate.get("notes") or []
    if notes:
        lines.extend(["REST API Quota Notes", *[f"- {note}" for note in notes], ""])

    return "\n".join(lines).rstrip() + "\n"


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


def send_email(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    html: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> None:
    """Send a report through Resend with optional HTML body."""
    from . import http_retry

    payload_dict: dict[str, object] = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }
    if html:
        payload_dict["html"] = html
    payload = json.dumps(payload_dict)
    response = http_retry.request_with_retries(
        "POST",
        "/emails",
        host="api.resend.com",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body=payload,
        timeout=timeout if timeout is not None else http_retry.DEFAULT_TIMEOUT_SECONDS,
        max_retries=max_retries if max_retries is not None else http_retry.DEFAULT_MAX_RETRIES,
    )
    if response.status not in (200, 201):
        response_body = response.body.decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API error {response.status}: {response_body[:300]}")
