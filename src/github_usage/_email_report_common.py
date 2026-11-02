"""Shared formatters used by both text and HTML email report renderers."""

from __future__ import annotations

from datetime import UTC, datetime

from .report_helpers import fmt_price
from .usage_split import _PRIVATE_MINUTES_LIMIT

# Matches ``get_actions_usage`` default ``storage_limit_mb`` (500), not 0.5 GiB.
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


def email_actions_table_rows(actions: dict) -> list[tuple[str, str]]:
    """Structured label/value pairs for the Actions section (text bullets or HTML rows)."""
    rows: list[tuple[str, str]] = []
    for line in email_actions_minutes_lines(actions):
        label, _, value = line.partition(": ")
        rows.append((label.removeprefix("- "), value))
    for line in email_actions_storage_lines(actions):
        label, _, value = line.partition(": ")
        rows.append((label.removeprefix("- "), value))
    return rows


def email_actions_minutes_lines(actions: dict) -> list[str]:
    """Bullet lines for Actions compute minutes (quota is private-only)."""
    limit = int(actions.get("minutes_limit") or _PRIVATE_MINUTES_LIMIT)
    if "private_minutes" in actions:
        private = float(actions.get("private_minutes") or 0.0)
        public = float(actions.get("public_minutes") or 0.0)
        pct = (private / limit * 100.0) if limit else 0.0
        lines = [f"- Quota (private repos): {private:,.1f} / {limit:,} min ({pct:.1f}%)"]
        if public > 0:
            lines.append(f"- Public repos (free): {public:,.1f} min")
        unattributed = float(actions.get("unattributed_minutes") or 0.0)
        if unattributed >= 0.05:
            lines.append(f"- Not attributed to scanned repos: {unattributed:,.1f} min")
        account = float(actions.get("minutes") or 0.0)
        reconciled = actions.get("reconciled", True)
        if account > 0 and not reconciled:
            lines.append(f"- Account total (billing API): {account:,.1f} min")
        elif account > 0 and abs(account - (private + public + unattributed)) > 0.05:
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
        unattributed_gb = float(actions.get("unattributed_storage_gb_hours") or 0.0)
        priv_pct = (priv_mb / limit_mb * 100.0) if limit_mb else 0.0
        lines = [
            (
                f"- Quota storage (private): {priv_mb:,.1f} / {limit_mb:,} MB "
                f"({priv_pct:.1f}%)"
            ),
            f"- Accrued (private): {priv_gb:,.4f} GB-hrs",
        ]
        if unattributed_gb >= 0.0001:
            lines.append(
                f"- Storage not attributed to scanned repos: {unattributed_gb:,.4f} GB-hrs"
            )
        if pub_mb > 0 or pub_gb > 0:
            lines.append(f"- Public repos (free): {pub_mb:,.1f} MB · {pub_gb:,.4f} GB-hrs")
        account_gb = float(actions.get("storage_gb_hours") or 0.0)
        if account_gb > 0 and (
            unattributed_gb >= 0.0001 or not actions.get("reconciled_storage", True)
        ):
            lines.append(
                f"- Account total (billing API): {account_gb:,.4f} GB-hrs "
                "(may include unscanned repos)"
            )
        return lines
    avg_mb = float(actions.get("storage_avg_mb") or 0.0)
    gb_hours = float(actions.get("storage_gb_hours") or 0.0)
    pct = float(actions.get("storage_percent") or 0.0)
    return [
        f"- Account storage (avg): {avg_mb:,.1f} / {limit_mb:,} MB ({pct:.1f}%)",
        f"- Accrued: {gb_hours:,.4f} GB-hrs",
        (
            f"- Note: {limit_mb:,} MB free tier applies to private artifact storage; "
            "account totals may include public repos."
        ),
    ]


def email_actions_net_cost_line(net: float) -> str:
    return f"- Net cost: {fmt_price(net)}"
