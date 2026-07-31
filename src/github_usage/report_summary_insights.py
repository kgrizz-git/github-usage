"""Utilization bars, findings, and recommendations for the final summary.

Split out of ``report_summary`` to stay under the module size budget.
"""

from __future__ import annotations

from .report_helpers import days_in_month, fmt_price, gb_hours_to_avg_mb
from .usage_split import flat_equivalent_gb_hours, storage_allowance_gb_hours
from .visibility import repo_visibility, visibility_label


def _repo_label(full: str, visibility_by_repo: dict[str, str] | None) -> str:
    if not visibility_by_repo:
        return full
    return f"{full}{visibility_label(visibility_by_repo.get(full, 'public'))}"


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

    free_min_limit = 2000
    bar_len = 40
    min_pct = min(100, (private_min / free_min_limit * 100) if private_min else 0)
    min_filled = int(min_pct / 100 * bar_len)
    scan_note = " (scanned repos)" if filtered else ""
    tier_label = "of private free tier" if has_split else "of free tier"
    print(
        f"\n    Actions Minutes{scan_note}:     {private_min:>8.1f} / {free_min_limit} min "
        f"({min_pct:.1f}% {tier_label})"
    )
    print(f"    {'█' * min_filled}{'░' * (bar_len - min_filled)}")
    if not skip_quota:
        if min_pct > 80:
            print("    ⚠ HIGH USAGE — private repos past/near the free-tier minute limit!")
        elif min_pct > 50:
            print("    → Moderate usage — on track to use half your private free allowance")
    if has_split and public_min:
        print(f"    (+ {public_min:.1f} min public, free)")
    print()

    free_storage_mb = 500
    if has_split:
        avg_storage_mb = float(actions.get("private_storage_avg_mb", 0.0) or 0.0)
        private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
    else:
        avg_storage_mb = gb_hours_to_avg_mb(user_storage_gb_hours) if user_storage_gb_hours else 0
        private_gb = float(user_storage_gb_hours or 0)
    storage_pct = min(100, (avg_storage_mb / free_storage_mb * 100) if free_storage_mb > 0 else 0)
    storage_filled = int(storage_pct / 100 * bar_len)
    print(
        f"    Actions Storage{scan_note}:     {avg_storage_mb:>8.1f} / {free_storage_mb} MB "
        f"({storage_pct:.1f}% {tier_label})"
    )
    print(f"    {'█' * storage_filled}{'░' * (bar_len - storage_filled)}")
    if not skip_quota:
        if storage_pct > 80:
            print("    ⚠ HIGH USAGE — approaching free tier limit!")
        elif storage_pct > 50:
            print("    → Moderate usage — on track to use half your free allowance")
    if has_split:
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

    findings = []
    actions = actions or {}
    larger = list(actions.get("larger_runner_skus") or [])
    if larger:
        findings.append(
            "Larger-runner SKU(s) detected: "
            + ", ".join(larger)
            + " — always billed regardless of repo visibility."
        )

    expired_repos = 0
    expired_arts = 0
    soon_repos = 0
    soon_arts = 0
    for repo in (storage_analysis or {}).get("repos", []):
        exp = int(repo.get("expired_count", 0) or 0)
        soon = int(repo.get("expiring_soon_count", 0) or 0)
        if exp:
            expired_repos += 1
            expired_arts += exp
        if soon:
            soon_repos += 1
            soon_arts += soon
    if expired_arts or soon_arts:
        parts = []
        if expired_arts:
            parts.append(f"{expired_arts} already expired across {expired_repos} repo(s)")
        if soon_arts:
            parts.append(f"{soon_arts} expire within 7 days across {soon_repos} repo(s)")
        findings.append("Artifacts: " + "; ".join(parts) + ".")

    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    sorted_by_cost = sorted(repo_data, key=lambda x: x[4], reverse=True) if repo_data else []
    sorted_by_storage = sorted(
        storage_analysis.get("repos", []), key=lambda x: x["total_storage"], reverse=True
    )

    if sorted_repos:
        top_repo = sorted_repos[0]
        pct_of_total = top_repo[1] / user_minutes * 100 if user_minutes else 0
        findings.append(
            f"Biggest Actions consumer: {_repo_label(top_repo[0], visibility_by_repo)} at {top_repo[1]:.0f} min ({pct_of_total:.1f}% of total)"
        )

    if sorted_by_cost:
        top_cost = sorted_by_cost[0]
        pct_cost = top_cost[4] / actions_gross * 100 if actions_gross else 0
        findings.append(
            f"Highest Actions cost: {_repo_label(top_cost[0], visibility_by_repo)} at {fmt_price(top_cost[4])} ({pct_cost:.1f}% of total)"
        )

    if sorted_by_storage:
        top_st = sorted_by_storage[0]
        total_gb = top_st["total_storage"]
        size_str = f"{total_gb:.2f} GB" if total_gb >= 1 else f"{total_gb * 1024:.0f} MB"
        st_label = f"{top_st['name']}{visibility_label(repo_visibility(top_st))}"
        findings.append(f"Biggest storage consumer: {st_label} ({size_str})")

    if premium_by_model:
        top_model = max(premium_by_model.items(), key=lambda x: x[1]["total_requests"])
        findings.append(
            f"Most-used Copilot model: {top_model[0]} with {top_model[1]['total_requests']:.0f} requests"
        )

    if (total_discount or 0) > 0 and (total_gross or 0) > 0:
        findings.append(
            f"Monthly savings from discounts: {fmt_price(total_discount or 0)} ({(total_discount or 0) / (total_gross or 0) * 100:.1f}% off gross)"
        )

    if (total_net or 0) > 0 and (user_minutes or 0) > 0:
        cost_per_min = (total_net or 0) / (user_minutes or 0)
        findings.append(
            f"Effective cost per Actions minute: {fmt_price(cost_per_min)} (all products averaged)"
        )

    for i, finding in enumerate(findings[:3], 1):
        print(f"\n    {i}. {finding}")
    print()


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
    recs = []
    actions = actions or {}
    has_split = "private_minutes" in actions
    filtered = bool(actions.get("filtered"))
    private_min = (
        float(actions.get("private_minutes") or 0.0) if has_split else float(user_minutes or 0)
    )
    skip_private_quota = filtered and has_split and private_min <= 0

    free_min_limit = 2000
    if not skip_private_quota and has_split and private_min > free_min_limit:
        recs.append(
            f"Private repos used all 2,000 free Actions minutes ({private_min:.0f} used) — "
            "review the private top-consumers below or move heavy workflows to public/self-hosted."
        )
    elif not skip_private_quota:
        min_pct = (private_min / free_min_limit * 100) if private_min else 0
        if min_pct > 80:
            if has_split:
                recs.append(
                    "Optimize private-repo Actions workflows — you're near the 2,000 free-minute limit."
                )
            else:
                recs.append(
                    "Upgrade from free tier or optimize Actions workflows — you're near your minute limit."
                )

    basis_minutes = private_min if has_split and not skip_private_quota else (user_minutes or 0)
    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    if sorted_repos and len(sorted_repos) > 1 and basis_minutes > 0:
        top2_sum = sorted_repos[0][1] + sorted_repos[1][1]
        if top2_sum / basis_minutes * 100 > 70:
            top_labels = ", ".join(
                _repo_label(str(row[0]), visibility_by_repo) for row in sorted_repos[:2]
            )
            recs.append(
                f"Top 2 repos ({top_labels}) consume "
                f"{top2_sum / basis_minutes * 100:.0f}% of Actions — "
                "consider self-hosted runners to save."
            )

    if has_split and not skip_private_quota:
        private_gb = float(actions.get("private_storage_gb_hours", 0.0) or 0.0)
        allowance = storage_allowance_gb_hours(days_in_month())
        if allowance and private_gb > 0.8 * allowance:
            recs.append(
                "Private artifact accrual is over 80% of the monthly GB-hrs allowance — "
                "clean up artifacts or reduce retention (Settings → Actions → General)."
            )

    if premium_by_model:
        models = list(premium_by_model.keys())
        if len(models) > 2:
            recs.append(
                f"Using {len(models)} Copilot models — consolidate to reduce cost complexity."
            )

    if lfs_summary and (lfs_summary.get("total_gross", 0) or 0) > 0:
        recs.append("Review Git LFS usage — large binaries add up quickly at ~$1/GB.")

    sorted_by_storage = sorted(
        storage_analysis.get("repos", []), key=lambda x: x["total_storage"], reverse=True
    )
    if sorted_by_storage:
        top_st = sorted_by_storage[0]
        items = top_st.get("items", [])
        release_assets = [a for a in items if a["type"] == "Release Asset"]
        if release_assets:
            total_release_size = sum(a["storage"] for a in release_assets)
            if total_release_size > 0.1:  # 100MB in GB
                st_label = f"{top_st['name']}{visibility_label(repo_visibility(top_st))}"
                recs.append(
                    f"Release assets in {st_label} use {total_release_size:.2f} GB — "
                    "consider GitHub Pages or external storage for large binaries "
                    "(release assets are not Actions artifact quota)."
                )

    if not recs:
        recs.append("Usage is well within free tiers — no immediate action needed.")
        recs.append("Consider enabling cost alerts in GitHub billing settings.")
    for i, rec in enumerate(recs, 1):
        print(f"\n    {i}. {rec}")
    print()
