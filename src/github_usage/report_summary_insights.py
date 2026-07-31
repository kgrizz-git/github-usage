"""Utilization bars, findings, and recommendations for the final summary.

Split out of ``report_summary`` to stay under the module size budget.
"""

from __future__ import annotations

from .report_helpers import days_in_month, fmt_price, gb_hours_to_avg_mb
from .usage_split import flat_equivalent_gb_hours, storage_allowance_gb_hours
from .visibility import repo_visibility, visibility_label

_FREE_MIN_LIMIT = 2000
_FREE_STORAGE_MB = 500
_BAR_LEN = 40


def _repo_label(full: str, visibility_by_repo: dict[str, str] | None) -> str:
    if not visibility_by_repo:
        return full
    return f"{full}{visibility_label(visibility_by_repo.get(full, 'public'))}"


def _usage_bar(pct: float) -> str:
    filled = int(min(100, pct) / 100 * _BAR_LEN)
    return f"    {'█' * filled}{'░' * (_BAR_LEN - filled)}"


def _print_usage_band(pct: float, *, high: str, moderate: str) -> None:
    if pct > 80:
        print(f"    ⚠ HIGH USAGE — {high}")
    elif pct > 50:
        print(f"    → Moderate usage — {moderate}")


def _print_minutes_utilization(
    *,
    private_min: float,
    public_min: float,
    has_split: bool,
    skip_quota: bool,
    scan_note: str,
    tier_label: str,
) -> None:
    min_pct = min(100, (private_min / _FREE_MIN_LIMIT * 100) if private_min else 0)
    print(
        f"\n    Actions Minutes{scan_note}:     {private_min:>8.1f} / {_FREE_MIN_LIMIT} min "
        f"({min_pct:.1f}% {tier_label})"
    )
    print(_usage_bar(min_pct))
    if not skip_quota:
        _print_usage_band(
            min_pct,
            high="private repos past/near the free-tier minute limit!",
            moderate="on track to use half your private free allowance",
        )
    if has_split and public_min:
        print(f"    (+ {public_min:.1f} min public, free)")
    print()


def _print_storage_utilization(
    *,
    avg_storage_mb: float,
    private_gb: float,
    actions: dict,
    has_split: bool,
    skip_quota: bool,
    scan_note: str,
    tier_label: str,
) -> None:
    storage_pct = min(100, (avg_storage_mb / _FREE_STORAGE_MB * 100) if _FREE_STORAGE_MB > 0 else 0)
    print(
        f"    Actions Storage{scan_note}:     {avg_storage_mb:>8.1f} / {_FREE_STORAGE_MB} MB "
        f"({storage_pct:.1f}% {tier_label})"
    )
    print(_usage_bar(storage_pct))
    if not skip_quota:
        _print_usage_band(
            storage_pct,
            high="approaching free tier limit!",
            moderate="on track to use half your free allowance",
        )
    if not has_split:
        print()
        return
    dim = days_in_month()
    allowance = storage_allowance_gb_hours(dim)
    flat_mb = flat_equivalent_gb_hours(private_gb, dim) * 1024.0
    gb_pct = (private_gb / allowance * 100) if allowance else 0
    print(
        f"    Private accrued {private_gb:.2f} / {allowance:.0f} GB-hrs "
        f"({gb_pct:.1f}%) ≈ {flat_mb:.0f} MB flat all month"
    )
    public_avg = float(actions.get("public_storage_avg_mb", 0.0) or 0.0)
    if public_avg:
        print(f"    (+ {public_avg:.1f} MB public avg storage, free)")
    print()


def _print_utilization(user_minutes, user_storage_gb_hours, *, actions: dict | None = None):
    print("  4. RESOURCE UTILIZATION vs LIMITS")
    print(f"  {'─' * 55}")
    actions = actions or {}
    has_split = "private_minutes" in actions
    filtered = bool(actions.get("filtered"))
    private_min = float(
        actions.get("private_minutes", user_minutes) if has_split else (user_minutes or 0)
    )
    public_min = float(actions.get("public_minutes", 0.0) or 0.0)
    skip_quota = filtered and has_split and private_min <= 0
    scan_note = " (scanned repos)" if filtered else ""
    tier_label = "of private free tier" if has_split else "of free tier"
    _print_minutes_utilization(
        private_min=private_min,
        public_min=public_min,
        has_split=has_split,
        skip_quota=skip_quota,
        scan_note=scan_note,
        tier_label=tier_label,
    )
    if has_split:
        avg_storage_mb = float(actions.get("private_storage_avg_mb", 0.0) or 0.0)
        private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
    else:
        avg_storage_mb = gb_hours_to_avg_mb(user_storage_gb_hours) if user_storage_gb_hours else 0
        private_gb = float(user_storage_gb_hours or 0)
    _print_storage_utilization(
        avg_storage_mb=avg_storage_mb,
        private_gb=private_gb,
        actions=actions,
        has_split=has_split,
        skip_quota=skip_quota,
        scan_note=scan_note,
        tier_label=tier_label,
    )


def _artifact_expiry_findings(storage_analysis: dict | None) -> list[str]:
    expired_repos = expired_arts = soon_repos = soon_arts = 0
    for repo in (storage_analysis or {}).get("repos", []):
        exp = int(repo.get("expired_count", 0) or 0)
        soon = int(repo.get("expiring_soon_count", 0) or 0)
        if exp:
            expired_repos += 1
            expired_arts += exp
        if soon:
            soon_repos += 1
            soon_arts += soon
    if not expired_arts and not soon_arts:
        return []
    parts = []
    if expired_arts:
        parts.append(f"{expired_arts} already expired across {expired_repos} repo(s)")
    if soon_arts:
        parts.append(f"{soon_arts} expire within 7 days across {soon_repos} repo(s)")
    return ["Artifacts: " + "; ".join(parts) + "."]


def _consumer_findings(
    user_minutes,
    actions_gross,
    repo_data,
    storage_analysis,
    visibility_by_repo,
) -> list[str]:
    findings: list[str] = []
    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    sorted_by_cost = sorted(repo_data, key=lambda x: x[4], reverse=True) if repo_data else []
    sorted_by_storage = sorted(
        storage_analysis.get("repos", []), key=lambda x: x["total_storage"], reverse=True
    )
    if sorted_repos:
        top_repo = sorted_repos[0]
        pct_of_total = top_repo[1] / user_minutes * 100 if user_minutes else 0
        findings.append(
            f"Biggest Actions consumer: {_repo_label(top_repo[0], visibility_by_repo)} "
            f"at {top_repo[1]:.0f} min ({pct_of_total:.1f}% of total)"
        )
    if sorted_by_cost:
        top_cost = sorted_by_cost[0]
        pct_cost = top_cost[4] / actions_gross * 100 if actions_gross else 0
        findings.append(
            f"Highest Actions cost: {_repo_label(top_cost[0], visibility_by_repo)} "
            f"at {fmt_price(top_cost[4])} ({pct_cost:.1f}% of total)"
        )
    if sorted_by_storage:
        top_st = sorted_by_storage[0]
        total_gb = top_st["total_storage"]
        size_str = f"{total_gb:.2f} GB" if total_gb >= 1 else f"{total_gb * 1024:.0f} MB"
        st_label = f"{top_st['name']}{visibility_label(repo_visibility(top_st))}"
        findings.append(f"Biggest storage consumer: {st_label} ({size_str})")
    return findings


def _print_impactful_findings(
    user_minutes,
    actions_gross,
    total_gross,
    total_discount,
    total_net,
    repo_data,
    premium_by_model,
    storage_analysis,
    visibility_by_repo=None,
    *,
    actions: dict | None = None,
):
    print("  5. TOP 3 MOST IMPACTFUL FINDINGS")
    print(f"  {'─' * 55}")
    findings: list[str] = []
    actions = actions or {}
    larger = list(actions.get("larger_runner_skus") or [])
    if larger:
        findings.append(
            "Larger-runner SKU(s) detected: "
            + ", ".join(larger)
            + " — always billed regardless of repo visibility."
        )
    findings.extend(_artifact_expiry_findings(storage_analysis))
    findings.extend(
        _consumer_findings(
            user_minutes, actions_gross, repo_data, storage_analysis, visibility_by_repo
        )
    )
    if premium_by_model:
        top_model = max(premium_by_model.items(), key=lambda x: x[1]["total_requests"])
        findings.append(
            f"Most-used Copilot model: {top_model[0]} with "
            f"{top_model[1]['total_requests']:.0f} requests"
        )
    if (total_discount or 0) > 0 and (total_gross or 0) > 0:
        findings.append(
            f"Monthly savings from discounts: {fmt_price(total_discount or 0)} "
            f"({(total_discount or 0) / (total_gross or 0) * 100:.1f}% off gross)"
        )
    if (total_net or 0) > 0 and (user_minutes or 0) > 0:
        cost_per_min = (total_net or 0) / (user_minutes or 0)
        findings.append(
            f"Effective cost per Actions minute: {fmt_price(cost_per_min)} (all products averaged)"
        )
    for i, finding in enumerate(findings[:3], 1):
        print(f"\n    {i}. {finding}")
    print()


def _minute_recommendations(
    *,
    private_min: float,
    has_split: bool,
    skip_private_quota: bool,
) -> list[str]:
    if skip_private_quota:
        return []
    if has_split and private_min > _FREE_MIN_LIMIT:
        return [
            f"Private repos used all 2,000 free Actions minutes ({private_min:.0f} used) — "
            "review the private top-consumers below or move heavy workflows to "
            "public/self-hosted."
        ]
    min_pct = (private_min / _FREE_MIN_LIMIT * 100) if private_min else 0
    if min_pct <= 80:
        return []
    if has_split:
        return [
            "Optimize private-repo Actions workflows — you're near the 2,000 free-minute limit."
        ]
    return ["Upgrade from free tier or optimize Actions workflows — you're near your minute limit."]


def _concentration_recommendation(repo_data, basis_minutes, visibility_by_repo) -> list[str]:
    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    if len(sorted_repos) <= 1 or basis_minutes <= 0:
        return []
    top2_sum = sorted_repos[0][1] + sorted_repos[1][1]
    if top2_sum / basis_minutes * 100 <= 70:
        return []
    top_labels = ", ".join(_repo_label(str(row[0]), visibility_by_repo) for row in sorted_repos[:2])
    return [
        f"Top 2 repos ({top_labels}) consume "
        f"{top2_sum / basis_minutes * 100:.0f}% of Actions — "
        "consider self-hosted runners to save."
    ]


def _release_asset_recommendation(storage_analysis: dict) -> list[str]:
    sorted_by_storage = sorted(
        storage_analysis.get("repos", []), key=lambda x: x["total_storage"], reverse=True
    )
    if not sorted_by_storage:
        return []
    top_st = sorted_by_storage[0]
    release_assets = [a for a in top_st.get("items", []) if a["type"] == "Release Asset"]
    if not release_assets:
        return []
    total_release_size = sum(a["storage"] for a in release_assets)
    if total_release_size <= 0.1:
        return []
    st_label = f"{top_st['name']}{visibility_label(repo_visibility(top_st))}"
    return [
        f"Release assets in {st_label} use {total_release_size:.2f} GB — "
        "consider GitHub Pages or external storage for large binaries "
        "(release assets are not Actions artifact quota)."
    ]


def _print_recommendations(
    user_minutes,
    repo_data,
    premium_by_model,
    lfs_summary,
    storage_analysis,
    visibility_by_repo=None,
    *,
    actions: dict | None = None,
):
    print("  6. QUICK RECOMMENDATIONS")
    print(f"  {'─' * 55}")
    actions = actions or {}
    has_split = "private_minutes" in actions
    filtered = bool(actions.get("filtered"))
    private_min = (
        float(actions.get("private_minutes") or 0.0) if has_split else float(user_minutes or 0)
    )
    skip_private_quota = filtered and has_split and private_min <= 0
    recs = _minute_recommendations(
        private_min=private_min, has_split=has_split, skip_private_quota=skip_private_quota
    )
    basis_minutes = private_min if has_split and not skip_private_quota else (user_minutes or 0)
    recs.extend(_concentration_recommendation(repo_data, basis_minutes, visibility_by_repo))
    if has_split and not skip_private_quota:
        private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
        allowance = storage_allowance_gb_hours(days_in_month())
        if allowance and private_gb > 0.8 * allowance:
            recs.append(
                "Private artifact accrual is over 80% of the monthly GB-hrs allowance — "
                "clean up artifacts or reduce retention (Settings → Actions → General)."
            )
    if premium_by_model and len(premium_by_model) > 2:
        recs.append(
            f"Using {len(premium_by_model)} Copilot models — consolidate to reduce cost complexity."
        )
    if lfs_summary and (lfs_summary.get("total_gross", 0) or 0) > 0:
        recs.append("Review Git LFS usage — large binaries add up quickly at ~$1/GB.")
    recs.extend(_release_asset_recommendation(storage_analysis))
    if not recs:
        recs.append("Usage is well within free tiers — no immediate action needed.")
        recs.append("Consider enabling cost alerts in GitHub billing settings.")
    for i, rec in enumerate(recs, 1):
        print(f"\n    {i}. {rec}")
    print()
