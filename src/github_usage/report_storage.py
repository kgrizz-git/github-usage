"""Artifact storage & retention section for the legacy terminal report.

Separates private-quota artifact accrual (from Actions billing) from the
current artifact/release scan, and surfaces expiry/retention rollups from
:func:`storage.get_storage_analysis`.
"""

from __future__ import annotations

from datetime import date

from .report_helpers import days_in_month, gb_hours_to_avg_mb
from .terminal import print_section
from .usage_split import flat_equivalent_gb_hours, storage_allowance_gb_hours
from .visibility import visibility_label


def _accrued_by_repo(repo_actions: list[dict]) -> dict[str, dict]:
    """Map full repo name → Actions billing row (minutes/storage/visibility)."""
    return {row.get("repo", ""): row for row in repo_actions or [] if row.get("repo")}


def _expiry_note(repo: dict) -> str:
    """Short expiry annotation for a per-repo storage row."""
    expired = int(repo.get("expired_count", 0) or 0)
    soon = int(repo.get("expiring_soon_count", 0) or 0)
    if expired and soon:
        return f"expired: {expired}; ≤7d: {soon}"
    if expired:
        return f"expired: {expired}"
    if soon:
        return f"≤7d: {soon}"
    days = None
    for item in repo.get("items") or []:
        if item.get("type") != "Artifact" or item.get("expired"):
            continue
        d = item.get("days_to_expiry")
        if d is None:
            continue
        days = d if days is None else min(days, int(d))
    if days is None:
        return "—"
    if days < 0:
        return "expired"
    return f"in {days}d"


def render_artifact_storage_section(
    storage_analysis: dict | None,
    actions: dict | None,
    repo_actions: list[dict] | None = None,
    *,
    reference_date: date | None = None,
) -> None:
    """Print the Artifact Storage & Retention section (private-first framing)."""
    print_section("Artifact Storage & Retention")
    ref = reference_date or date.today()
    dim = days_in_month(ref)
    allowance = storage_allowance_gb_hours(dim)
    month_label = ref.strftime("%b %Y")

    actions = actions or {}
    private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
    public_gb = float(actions.get("public_storage_gb_hours", 0.0) or 0.0)
    unattr_gb = float(actions.get("unattributed_storage_gb_hours", 0.0) or 0.0)
    has_split = "private_storage_gb_hours" in actions

    print(
        f"  Private allowance: 500 MB of artifacts = {allowance:.0f} GB-hrs "
        f"flat all month ({month_label})"
    )
    if has_split:
        pct = (private_gb / allowance * 100.0) if allowance else 0.0
        flat_gb = flat_equivalent_gb_hours(private_gb, dim)
        flat_mb = flat_gb * 1024.0
        print(
            f"    Private accrued:  {private_gb:>8.2f} GB-hrs "
            f"({pct:.1f}% of {allowance:.0f})  ≈ {flat_mb:.0f} MB flat all month"
        )
        print(f"    Public accrued:   {public_gb:>8.2f} GB-hrs (free — no quota impact)")
        if unattr_gb:
            print(f"    Unattributed:     {unattr_gb:>8.2f} GB-hrs")
    else:
        combined = float(actions.get("storage_gb_hours", 0.0) or 0.0)
        print(f"    Accrued (combined): {combined:>8.2f} GB-hrs  (visibility split unavailable)")
    print()

    repos = list((storage_analysis or {}).get("repos") or [])
    if not repos:
        print("  (No artifact/release storage found in scanned repos.)")
        print()
        return

    by_repo = _accrued_by_repo(repo_actions or [])
    ranked = sorted(
        repos,
        key=lambda r: float(
            (by_repo.get(r.get("name"), {}) or {}).get("storage_gb_hours", 0.0) or 0.0
        ),
        reverse=True,
    )[:10]

    print(f"  {'Per-repo (current scan)':<42} {'CURRENT':>10} {'ACCRUED':>12} {'ARTIF':>6}  EXPIRY")
    for repo in ranked:
        name = str(repo.get("name", "?"))
        vis = repo.get("visibility", "public")
        label = f"{name}{visibility_label(vis)}"
        art_gb = float(repo.get("artifact_storage_gb", 0.0) or 0.0)
        # Prefer artifact-only current MB; fall back to total for old shapes.
        if "artifact_storage_gb" not in repo:
            art_gb = float(repo.get("total_storage", 0.0) or 0.0)
        current_mb = art_gb * 1024.0
        accrued = float((by_repo.get(name) or {}).get("storage_gb_hours", 0.0) or 0.0)
        count = int(repo.get("artifact_count", 0) or 0)
        free_note = " (free)" if vis == "public" else ""
        print(
            f"    {label:<40} {current_mb:>8.1f} MB {accrued:>8.2f} GB-hrs "
            f"{count:>5}  {_expiry_note(repo)}{free_note}"
        )
        rel_gb = float(repo.get("release_storage_gb", 0.0) or 0.0)
        if rel_gb > 0:
            print(
                f"      release assets: {rel_gb * 1024.0:.1f} MB "
                f"(free/unlimited — not quota-billed)"
            )
    print()
    print("  Retention: 90 days default; adjust per repo (Settings → Actions → General).")
    print("  Release assets are separate from Actions artifact storage (≤2 GiB/file, no quota).")
    print()


def build_storage_summary(
    actions: dict | None,
    *,
    reference_date: date | None = None,
) -> dict | None:
    """Build the ``storage_summary`` block from an actions dict with split keys."""
    if not actions or "private_storage_gb_hours" not in actions:
        return None
    ref = reference_date or date.today()
    dim = days_in_month(ref)
    private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
    public_gb = float(actions.get("public_storage_gb_hours", 0.0) or 0.0)
    return {
        "private_gb_hours": private_gb,
        "public_gb_hours": public_gb,
        "unattributed_gb_hours": float(actions.get("unattributed_storage_gb_hours", 0.0) or 0.0),
        "allowance_gb_hours": storage_allowance_gb_hours(dim),
        "private_avg_mb": float(actions.get("private_storage_avg_mb") or 0.0)
        if actions.get("private_storage_avg_mb") is not None
        else gb_hours_to_avg_mb(private_gb, ref),
        "public_avg_mb": float(actions.get("public_storage_avg_mb") or 0.0)
        if actions.get("public_storage_avg_mb") is not None
        else gb_hours_to_avg_mb(public_gb, ref),
        "retention_default_days": 90,
    }
