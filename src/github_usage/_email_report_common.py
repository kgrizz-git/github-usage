"""Shared formatters used by both text and HTML email report renderers."""

from __future__ import annotations

from datetime import UTC, datetime

from .report_helpers import fmt_price

_PRIVATE_MINUTES_LIMIT = 2000
_PRIVATE_STORAGE_LIMIT_MB = 500


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


def email_actions_minutes_lines(actions: dict) -> list[str]:
    """Bullet lines for Actions compute minutes (quota is private-only)."""
    limit = int(actions.get("minutes_limit") or _PRIVATE_MINUTES_LIMIT)
    if "private_minutes" in actions:
        private = float(actions.get("private_minutes") or 0.0)
        public = float(actions.get("public_minutes") or 0.0)
        pct = float(actions.get("private_minutes_percent") or 0.0)
        lines = [f"- Quota (private repos): {private:,.1f} / {limit:,} min ({pct:.1f}%)"]
        if public > 0:
            lines.append(f"- Public repos (free): {public:,.1f} min")
        unattributed = float(actions.get("unattributed_minutes") or 0.0)
        if unattributed > 0:
            lines.append(f"- Not attributed to scanned repos: {unattributed:,.1f} min")
        account = float(actions.get("minutes") or 0.0)
        if account > 0 and abs(account - (private + public + unattributed)) > 0.05:
            lines.append(f"- Account total (billing API): {account:,.1f} min")
        return lines
    minutes = float(actions.get("minutes") or 0.0)
    pct = float(actions.get("minutes_percent") or 0.0)
    return [
        f"- Account total: {minutes:,.1f} min",
        (
            f"- Note: {limit:,} min free tier applies to private repos only; "
            "this total may include public usage until a visibility split is available."
        ),
        f"- Shown vs limit (approximate): {minutes:,.1f} / {limit:,} ({pct:.1f}%)",
    ]


def email_actions_storage_lines(actions: dict) -> list[str]:
    """Bullet lines for billed Actions artifact storage."""
    limit_mb = int(actions.get("storage_limit_mb") or _PRIVATE_STORAGE_LIMIT_MB)
    if "private_storage_avg_mb" in actions:
        priv_mb = float(actions.get("private_storage_avg_mb") or 0.0)
        pub_mb = float(actions.get("public_storage_avg_mb") or 0.0)
        priv_gb = float(actions.get("private_storage_gb_hours") or 0.0)
        pub_gb = float(actions.get("public_storage_gb_hours") or 0.0)
        priv_pct = (priv_mb / limit_mb * 100.0) if limit_mb else 0.0
        lines = [
            (
                f"- Quota storage (private): {priv_mb:,.1f} / {limit_mb:,} MB "
                f"({priv_pct:.1f}%)"
            ),
            f"- Accrued (private): {priv_gb:,.4f} GB-hrs",
        ]
        if pub_mb > 0 or pub_gb > 0:
            lines.append(f"- Public repos (free): {pub_mb:,.1f} MB · {pub_gb:,.4f} GB-hrs")
        return lines
    avg_mb = float(actions.get("storage_avg_mb") or 0.0)
    gb_hours = float(actions.get("storage_gb_hours") or 0.0)
    pct = float(actions.get("storage_percent") or 0.0)
    return [
        f"- Account storage (avg): {avg_mb:,.1f} / {limit_mb:,} MB ({pct:.1f}%)",
        f"- Accrued: {gb_hours:,.4f} GB-hrs",
        (
            "- Note: 500 MB free tier applies to private artifact storage; "
            "account totals may include public repos."
        ),
    ]


def copilot_section_title(copilot: dict) -> str:
    """Heading for the Copilot usage block in email reports."""
    if copilot.get("metering") == "ai_credits":
        return "Copilot AI Credits"
    return "Copilot Premium Requests"


def copilot_usage_summary_lines(copilot: dict) -> list[str]:
    """Primary Copilot usage bullets for email (metering-aware)."""
    lines: list[str] = []
    if copilot.get("metering") == "ai_credits":
        usage_net = float(copilot.get("total_usage_net") or 0.0)
        lines.append(f"- Net AI credit usage: {usage_net:,.4f} (billing units)")
    else:
        lines.append(f"- Total requests: {copilot.get('total_requests', 0.0):,.1f}")
    lines.append(
        f"- Net cost (Copilot product summary): {fmt_price(float(copilot.get('total_net', 0.0)))}"
    )
    note = copilot.get("usage_note")
    if note:
        lines.append(f"- Note: {note}")
    return lines


def copilot_model_detail_line(model: str, values: dict, *, metering: str) -> str:
    """One model line under the Copilot section."""
    if metering == "ai_credits":
        net = float(values.get("net", 0.0))
        return f"  - {model}: {net:,.4f} net usage"
    requests = values.get("requests", values.get("total_requests", 0.0))
    return f"  - {model}: {float(requests):,.1f} requests"


def copilot_forecast_metric(copilot: dict) -> tuple[float, str]:
    """Return (current usage value, row label) for the usage forecast table."""
    if copilot.get("metering") == "ai_credits":
        value = float(copilot.get("total_usage_net") or 0.0)
        return value, "AI Credits (net)"
    return float(copilot.get("total_requests") or 0.0), "Premium Requests"
