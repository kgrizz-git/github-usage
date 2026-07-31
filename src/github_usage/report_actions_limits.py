"""Actions summary and limits rendering with private-usage emphasis.

Split out of ``report_actions`` to keep that module under the size budget.
Re-exported from ``report_actions`` for existing imports.
"""

from __future__ import annotations

from .report_helpers import days_in_month, fmt_price, gb_hours_to_avg_mb
from .terminal import print_section
from .usage_split import (
    classify_actions_sku,
    flat_equivalent_gb_hours,
    storage_allowance_gb_hours,
)

_PRIVATE_MINUTES_LIMIT = 2000
_PRIVATE_STORAGE_LIMIT_MB = 500


def _print_usage_by_visibility(actions: dict) -> None:
    """Print the Private/Public/Unattributed Actions block when split keys exist."""
    if "private_minutes" not in actions:
        return
    private_min = float(actions.get("private_minutes", 0.0) or 0.0)
    public_min = float(actions.get("public_minutes", 0.0) or 0.0)
    unattr_min = float(actions.get("unattributed_minutes", 0.0) or 0.0)
    private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
    public_gb = float(actions.get("public_storage_gb_hours", 0.0) or 0.0)
    unattr_gb = float(actions.get("unattributed_storage_gb_hours", 0.0) or 0.0)
    pct = float(actions.get("private_minutes_percent", 0.0) or 0.0)
    internal_n = int(actions.get("internal_repo_count", 0) or 0)
    filtered = bool(actions.get("filtered"))

    print("  Usage by Visibility:")
    priv_note = f" (includes {internal_n} internal repos)" if internal_n else ""
    scan_note = " (scanned repos)" if filtered else ""
    print(
        f"    Private (billable){priv_note}{scan_note}: "
        f"{private_min:>8.1f} min  of {_PRIVATE_MINUTES_LIMIT} free "
        f"({pct:.1f}% of private quota) | {private_gb:.1f} GB-hrs"
    )
    print(f"    Public (free):              {public_min:>8.1f} min  | {public_gb:.1f} GB-hrs")
    if unattr_min or unattr_gb:
        print(
            f"    Unattributed:               {unattr_min:>8.1f} min  | {unattr_gb:.1f} GB-hrs"
            f"   (repos beyond scan / measurement skew)"
        )
    print()


def _sku_display_name(sku: str, item: dict) -> str:
    """Append `` *`` for larger-runner compute SKUs."""
    if classify_actions_sku(sku, item) == "larger":
        return f"{sku} *"
    return sku


def render_actions_summary(actions: dict | None) -> None:
    """Print Actions summary from a pre-fetched ``actions`` section dict."""
    if not actions:
        print_section("GitHub Actions Usage")
        print("  (Actions data unavailable.)")
        print()
        return
    user_minutes = actions.get("minutes", 0)
    storage_gb_hours = actions.get("storage_gb_hours", 0)
    sku_breakdown = actions.get("sku_breakdown") or {}
    print_section("GitHub Actions Usage")
    print("  Summary:")
    print(f"    Compute Minutes:    {user_minutes:>10.1f} min")
    print(f"    Storage (GB-hrs):   {storage_gb_hours:>10.4f} GB-hrs")
    print(f"    Avg Storage (MB):   {gb_hours_to_avg_mb(storage_gb_hours):>10.1f} MB")
    print()
    _print_usage_by_visibility(actions)
    print("  Per-SKU Breakdown:")
    print(f"    {'SKU':<30} {'QTY':>10} {'UNIT':<18} {'GROSS':>10} {'DISCOUNT':>10} {'NET':>10}")
    print(f"    {'-' * 30} {'-' * 10} {'-' * 18} {'-' * 10} {'-' * 10} {'-' * 10}")
    saw_larger = False
    for sku, item in sku_breakdown.items():
        qty = item.get("grossQuantity", 0)
        unit = item.get("unitType", "")
        gross = item.get("grossAmount", 0)
        discount = item.get("discountAmount", 0)
        net = item.get("netAmount", 0)
        label = _sku_display_name(str(sku), item if isinstance(item, dict) else {})
        if label.endswith(" *"):
            saw_larger = True
        print(
            f"    {label:<30} {qty:>10.4f} {unit:<18} {fmt_price(gross):>10} "
            f"{fmt_price(discount):>10} {fmt_price(net):>10}"
        )
    if saw_larger:
        print("    * = GitHub-hosted larger runner — always billed, not covered by free tier")
    print()


def render_limits_summary(actions: dict | None, *, reference_date=None) -> None:
    """Print free-tier limits from a pre-fetched ``actions`` section dict.

    When visibility-split keys are present, minutes/storage checks use the
    **private** bucket only; public usage is labeled free.
    """
    actions = actions or {}
    filtered = bool(actions.get("filtered"))
    has_split = "private_minutes" in actions
    private_min = float(actions.get("private_minutes", actions.get("minutes", 0.0)) or 0.0)
    public_min = float(actions.get("public_minutes", 0.0) or 0.0)
    unattr_min = float(actions.get("unattributed_minutes", 0.0) or 0.0)

    title = "Limits Summary (scanned repos)" if filtered else "Limits Summary"
    print_section(title)

    # Suppress quota math for --only-public (filtered + no private minutes).
    skip_quota = filtered and has_split and private_min == 0.0

    if skip_quota:
        print("  Actions Minutes (private repos only):")
        print("    (No private repos in this scan — quota math suppressed.)")
        if public_min:
            print(f"    Public repos:  {public_min:>8.1f} min (free — no quota impact)")
        print()
    else:
        min_limit = _PRIVATE_MINUTES_LIMIT
        min_remaining = max(0, min_limit - private_min)
        min_pct = (private_min / min_limit * 100) if min_limit else 0
        label = "Actions Minutes (private repos only):" if has_split else "Actions Minutes:"
        print(f"  {label}")
        print(f"    Used:         {private_min:>8.1f} / {min_limit} min ({min_pct:.1f}% used)")
        print(f"    Remaining:    {min_remaining:>8.1f} min")
        if has_split and public_min:
            print(f"    Public repos:  {public_min:>8.1f} min (free — no quota impact)")
        if has_split and unattr_min:
            print(f"    Unattributed:  {unattr_min:>8.1f} min (best-effort attribution)")
        print()

    if has_split:
        private_avg = float(actions.get("private_storage_avg_mb", 0.0) or 0.0)
        public_avg = float(actions.get("public_storage_avg_mb", 0.0) or 0.0)
        private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
        public_gb = float(actions.get("public_storage_gb_hours", 0.0) or 0.0)
        dim = days_in_month(reference_date)
        allowance = storage_allowance_gb_hours(dim)
        flat_mb = flat_equivalent_gb_hours(private_gb, dim) * 1024.0
        storage_pct = (private_avg / _PRIVATE_STORAGE_LIMIT_MB * 100) if private_avg else 0
        gb_pct = (private_gb / allowance * 100) if allowance else 0
        print("  Actions Storage (avg, private repos only):")
        if skip_quota:
            print("    (No private repos in this scan — quota math suppressed.)")
        else:
            print(
                f"    Used:         {private_avg:>8.1f} / {_PRIVATE_STORAGE_LIMIT_MB} MB "
                f"({storage_pct:.1f}% used)"
            )
            print(
                f"    Accrued:      {private_gb:>8.1f} / {allowance:.0f} GB-hrs "
                f"({gb_pct:.1f}%)  ≈ {flat_mb:.0f} MB flat all month"
            )
        if public_avg or public_gb:
            print(f"    Public repos: {public_avg:>8.1f} MB / {public_gb:.1f} GB-hrs (free)")
        print()
    else:
        storage_gb_hours = float(actions.get("storage_gb_hours", 0) or 0)
        avg_storage_mb = gb_hours_to_avg_mb(storage_gb_hours) if storage_gb_hours else 0
        storage_remaining = max(0, _PRIVATE_STORAGE_LIMIT_MB - avg_storage_mb)
        storage_pct = (
            (avg_storage_mb / _PRIVATE_STORAGE_LIMIT_MB * 100) if _PRIVATE_STORAGE_LIMIT_MB else 0
        )
        print("  Actions Storage (avg):")
        print(f"    Used:         {avg_storage_mb:>8.1f} / {_PRIVATE_STORAGE_LIMIT_MB} MB")
        print(f"    Remaining:    {storage_remaining:>8.1f} MB ({storage_pct:.1f}% used)")
        print()

    print("  Copilot Pro:")
    print("    Includes: Copilot Chat, Copilot Agent, Code Review, etc.")
    print("    Premium requests are billed at $0.04/request after included allowance.")
    print("    (Check your plan details for exact premium request limits)")
    print()
