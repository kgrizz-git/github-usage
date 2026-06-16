"""Plain-text email report formatting and Resend delivery."""

from __future__ import annotations

import http.client
import json
from datetime import UTC, datetime

from .report_helpers import fmt_price


def default_subject(username: str, generated_at: str | None = None) -> str:
    """Return the default email subject."""
    day = generated_at[:10] if generated_at else datetime.now(tz=UTC).date().isoformat()
    return f"GitHub Usage Report for {username} - {day}"


def _generated_line(generated_at: str) -> str:
    if generated_at.endswith("Z"):
        generated_at = generated_at[:-1] + "+00:00"
    try:
        generated = datetime.fromisoformat(generated_at).astimezone(UTC)
    except ValueError:
        return f"Generated: {generated_at}"
    return f"Generated: {generated.strftime('%Y-%m-%d %H:%M UTC')}"


def _bytes_to_mb(value: int | float) -> float:
    return float(value) / (1024 * 1024)


def _cost_line(label: str, cost: dict[str, float]) -> str:
    return (
        f"- {label}: gross {fmt_price(cost.get('gross', 0.0))}, "
        f"discount {fmt_price(cost.get('discount', 0.0))}, "
        f"net {fmt_price(cost.get('net', 0.0))}"
    )


def format_report_email(data: dict) -> str:
    """Format report data as a plain-text email body."""
    lines = [
        f"GitHub Usage Report for {data.get('username', '?')}",
        _generated_line(str(data.get("generated_at", ""))),
        "Period: current month",
        "",
    ]

    warnings = data.get("warnings") or []
    if warnings:
        lines.extend(["WARNING", *[f"- {warning}" for warning in warnings], ""])

    actions = data.get("actions")
    if actions:
        net = (data.get("monthly_costs") or {}).get("actions", {}).get("net", 0.0)
        lines.extend(
            [
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
        )

    copilot = data.get("copilot")
    if copilot:
        lines.extend(
            [
                "Copilot Premium Requests",
                f"- Total requests: {copilot.get('total_requests', 0.0):,.1f}",
                f"- Net cost: {fmt_price(copilot.get('total_net', 0.0))}",
            ]
        )
        by_model = copilot.get("by_model") or {}
        if by_model:
            lines.append("- By model:")
            for model, values in sorted(by_model.items()):
                requests = values.get("requests", values.get("total_requests", 0.0))
                lines.append(f"  - {model}: {requests:,.1f} requests")
        lines.append("")

    git_lfs = data.get("git_lfs")
    if git_lfs:
        lines.extend(["Git LFS", f"- Net cost: {fmt_price(git_lfs.get('total_net', 0.0))}", ""])

    monthly = data.get("monthly_costs") or {}
    if monthly:
        lines.append("Monthly Cost Estimate")
        for key, label in [
            ("actions", "Actions"),
            ("copilot", "Copilot"),
            ("git_lfs", "Git LFS"),
            ("total", "Total"),
        ]:
            lines.append(_cost_line(label, monthly.get(key, {})))
        lines.append("")

    consumers = data.get("repo_consumers")
    if consumers:
        lines.append("Top Repositories by Actions Minutes")
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

    artifact_storage = data.get("artifact_storage")
    if artifact_storage:
        lines.append("Actions Artifact Storage")
        for row in artifact_storage.get("top_repos", []):
            lines.append(
                f"- {row['repo']}: {_bytes_to_mb(row['artifact_bytes']):,.1f} MB artifacts"
            )
        if artifact_storage.get("truncated"):
            lines.append(
                f"- Artifact scan truncated at {artifact_storage.get('max_repos')} repositories."
            )
        lines.append("")

    release_assets = data.get("release_assets")
    if release_assets:
        lines.append("Release Asset Inventory")
        for row in release_assets.get("top_repos", []):
            lines.append(
                f"- {row['repo']}: {_bytes_to_mb(row['release_asset_bytes']):,.1f} MB release assets"
            )
        if release_assets.get("truncated"):
            lines.append(
                f"- Release asset scan truncated at {release_assets.get('max_repos')} repositories."
            )
        lines.append("")

    insights = data.get("insights") or []
    if insights:
        lines.extend(["Key Insights", *[f"- {insight}" for insight in insights], ""])

    errors = data.get("errors") or {}
    if errors:
        lines.append("Unavailable Data")
        for section, message in sorted(errors.items()):
            lines.append(f"- {section.replace('_', ' ').title()} data unavailable - {message}")
        lines.append("")

    estimate = data.get("api_estimate") or {}
    notes = estimate.get("notes") or []
    if notes:
        lines.extend(["REST API Quota Notes", *[f"- {note}" for note in notes], ""])

    return "\n".join(lines).rstrip() + "\n"


def send_email(api_key: str, from_addr: str, to_addr: str, subject: str, body: str) -> None:
    """Send a plain-text report through Resend."""
    payload = json.dumps(
        {
            "from": from_addr,
            "to": [to_addr],
            "subject": subject,
            "text": body,
        }
    )
    conn = http.client.HTTPSConnection("api.resend.com")
    try:
        conn.request(
            "POST",
            "/emails",
            body=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        response_body = resp.read().decode("utf-8", errors="replace")
    finally:
        conn.close()
    if resp.status not in (200, 201):
        raise RuntimeError(f"Resend API error {resp.status}: {response_body[:300]}")
