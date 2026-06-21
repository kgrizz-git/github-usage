"""Final summary section for the legacy report."""

from __future__ import annotations

from .billing import get_premium_request_usage
from .report_helpers import fmt_price, gb_hours_to_avg_mb
from .terminal import print_section


def show_final_summary(
    username,
    user_minutes,
    user_storage_gb_hours,
    actions_gross,
    actions_discount,
    actions_net,
    repo_data,
    copilot_summary,
    lfs_summary,
    storage_analysis,
    api,
):
    """Final summary: biggest resource consumers, key insights."""
    print_section("FINAL SUMMARY — Key Insights & Biggest Consumers")

    copilot_gross = copilot_summary["total_gross"] if copilot_summary else 0
    copilot_discount = copilot_summary["total_discount"] if copilot_summary else 0
    lfs_gross = lfs_summary["total_gross"] if lfs_summary else 0
    lfs_discount = lfs_summary["total_discount"] if lfs_summary else 0
    lfs_net = lfs_summary["total_net"] if lfs_summary else 0

    total_gross = actions_gross + copilot_gross + lfs_gross
    total_discount = actions_discount + copilot_discount + lfs_discount
    total_net = actions_net + (copilot_summary["total_net"] if copilot_summary else 0) + lfs_net

    _print_cost_overview(total_gross, total_discount, total_net)

    premium_by_model = get_premium_request_usage(api, username)
    _print_top_consumers(user_minutes, actions_gross, repo_data, premium_by_model, lfs_summary)

    _print_storage_breakdown(storage_analysis)

    _print_utilization(user_minutes, user_storage_gb_hours)

    _print_impactful_findings(
        user_minutes,
        actions_gross,
        total_gross,
        total_discount,
        total_net,
        repo_data,
        premium_by_model,
        storage_analysis,
    )

    _print_recommendations(user_minutes, repo_data, premium_by_model, lfs_summary, storage_analysis)


def _print_cost_overview(total_gross, total_discount, total_net):
    print("\n  1. COST OVERVIEW")
    print(f"  {'─' * 55}")
    print(f"    Total Gross:     {fmt_price(total_gross):>12}")

    discount_pct = 0.0
    if total_gross > 0:
        discount_pct = total_discount / total_gross * 100

    print(f"    Total Discount:  {fmt_price(total_discount):>12}  ({discount_pct:.1f}% off)")
    print(f"    Total Net:       {fmt_price(total_net):>12}")
    print()


def _print_top_consumers(user_minutes, actions_gross, repo_data, premium_by_model, lfs_summary):
    print("  2. BIGGEST CONSUMERS BY CATEGORY")
    print(f"  {'─' * 55}")

    # Actions — top repos by minutes
    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    print("\n    Actions Minutes (top 5 repos):")
    for full, mins, _gb, _avg_mb, gross, _ in sorted_repos[:5]:
        pct = mins / user_minutes * 100 if user_minutes and user_minutes > 0 else 0
        print(f"      {full:<45} {mins:>8.1f} min  ({pct:5.1f}%)  {fmt_price(gross)}")
    if not sorted_repos:
        print("      No Actions usage found.")
    print()

    # Actions — top repos by cost
    sorted_by_cost = sorted(repo_data, key=lambda x: x[4], reverse=True) if repo_data else []
    print("    Actions Cost (top 5 repos):")
    for full, _mins, _gb, _avg_mb, gross, _ in sorted_by_cost[:5]:
        pct = gross / actions_gross * 100 if actions_gross > 0 else 0
        print(f"      {full:<45} {fmt_price(gross):>10}  ({pct:5.1f}%)")
    print()

    # Copilot — by model
    print("    Copilot Premium Requests (by model):")
    if premium_by_model:
        for model, data in sorted(
            premium_by_model.items(), key=lambda x: x[1]["total_requests"], reverse=True
        ):
            price = 0
            for item in data.get("items", []):
                pp = item.get("pricePerUnit", 0)
                if pp > 0:
                    price = pp
                    break
            print(
                f"      {model:<30} {data['total_requests']:>10.0f} reqs  @ {fmt_price(price)}/req  = {fmt_price(data['total_net'])}"
            )
    else:
        print("      No model-level data available.")
    print()

    # Git LFS
    if lfs_summary and lfs_summary.get("items"):
        print("    Git LFS Storage:")
        for sku, item in lfs_summary["items"].items():
            qty = item.get("grossQuantity", 0)
            unit = item.get("unitType", "")
            price = item.get("pricePerUnit", 0)
            net = item.get("netAmount", 0)
            print(
                f"      {sku:<30} {qty:>12.4f} {unit:<10} @ {fmt_price(price)}/ea  = {fmt_price(net)}"
            )
    else:
        print("    Git LFS: No usage found.")
    print()


def _print_storage_breakdown(storage_analysis):
    print("  3. STORAGE BREAKDOWN BY REPOSITORY")
    print(f"  {'─' * 55}")

    sorted_by_storage = sorted(
        storage_analysis.get("repos", []), key=lambda x: x["total_storage"], reverse=True
    )
    if sorted_by_storage:
        print(f"\n    {'REPO':<45} {'TOTAL':>10}")
        print(f"    {'-' * 45} {'-' * 10}")
        for r in sorted_by_storage[:10]:
            print(f"      {r['name']:<45} {fmt_price(r['total_storage']):>10}")
        print()

        top_storage = sorted_by_storage[0]
        print(
            f"    Top storage consumer: {top_storage['name']} ({fmt_price(top_storage['total_storage'])})"
        )
        print("    Breakdown:")
        for item in top_storage.get("items", []):
            print(
                f"      {item['type']:<20} {item['count']:>5} items  {fmt_price(item['storage'])}  ({item['size']})"
            )
        print()
    else:
        print("    No storage data available from repositories.\n")


def _print_utilization(user_minutes, user_storage_gb_hours):
    print("  4. RESOURCE UTILIZATION vs LIMITS")
    print(f"  {'─' * 55}")

    # Actions minutes
    free_min_limit = 2000
    min_pct = min(100, (user_minutes / free_min_limit * 100) if user_minutes else 0)
    bar_len = 40
    min_filled = int(min_pct / 100 * bar_len)
    print(
        f"\n    Actions Minutes:     {user_minutes:>8.1f} / {free_min_limit} min ({min_pct:.1f}% of free tier)"
    )
    print(f"    {'█' * min_filled}{'░' * (bar_len - min_filled)}")
    if min_pct > 80:
        print("    ⚠ HIGH USAGE — approaching free tier limit!")
    elif min_pct > 50:
        print("    → Moderate usage — on track to use half your free allowance")
    print()

    # Actions storage
    free_storage_mb = 500
    avg_storage_mb = gb_hours_to_avg_mb(user_storage_gb_hours) if user_storage_gb_hours else 0
    storage_pct = min(100, (avg_storage_mb / free_storage_mb * 100) if free_storage_mb > 0 else 0)
    storage_filled = int(storage_pct / 100 * bar_len)
    print(
        f"    Actions Storage:     {avg_storage_mb:>8.1f} / {free_storage_mb} MB ({storage_pct:.1f}% of free tier)"
    )
    print(f"    {'█' * storage_filled}{'░' * (bar_len - storage_filled)}")
    if storage_pct > 80:
        print("    ⚠ HIGH USAGE — approaching free tier limit!")
    elif storage_pct > 50:
        print("    → Moderate usage — on track to use half your free allowance")
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
):
    print("  5. TOP 3 MOST IMPACTFUL FINDINGS")
    print(f"  {'─' * 55}")

    findings = []
    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    sorted_by_cost = sorted(repo_data, key=lambda x: x[4], reverse=True) if repo_data else []
    sorted_by_storage = sorted(
        storage_analysis.get("repos", []), key=lambda x: x["total_storage"], reverse=True
    )

    if sorted_repos:
        top_repo = sorted_repos[0]
        pct_of_total = top_repo[1] / user_minutes * 100 if user_minutes else 0
        findings.append(
            f"Biggest Actions consumer: {top_repo[0]} at {top_repo[1]:.0f} min ({pct_of_total:.1f}% of total)"
        )

    if sorted_by_cost:
        top_cost = sorted_by_cost[0]
        pct_cost = top_cost[4] / actions_gross * 100 if actions_gross else 0
        findings.append(
            f"Highest Actions cost: {top_cost[0]} at {fmt_price(top_cost[4])} ({pct_cost:.1f}% of total)"
        )

    if sorted_by_storage:
        top_st = sorted_by_storage[0]
        total_gb = top_st["total_storage"]
        size_str = f"{total_gb:.2f} GB" if total_gb >= 1 else f"{total_gb * 1024:.0f} MB"
        findings.append(
            f"Biggest storage consumer: {top_st['name']} at {fmt_price(top_st['total_storage'])} ({size_str})"
        )

    if premium_by_model:
        top_model = max(premium_by_model.items(), key=lambda x: x[1]["total_requests"])
        findings.append(
            f"Most-used Copilot model: {top_model[0]} with {top_model[1]['total_requests']:.0f} requests"
        )

    if total_discount > 0 and total_gross > 0:
        findings.append(
            f"Monthly savings from discounts: {fmt_price(total_discount)} ({total_discount / total_gross * 100:.1f}% off gross)"
        )

    if total_net > 0 and user_minutes > 0:
        cost_per_min = total_net / user_minutes
        findings.append(
            f"Effective cost per Actions minute: {fmt_price(cost_per_min)} (all products averaged)"
        )

    for i, finding in enumerate(findings[:3], 1):
        print(f"\n    {i}. {finding}")
    print()


def _print_recommendations(
    user_minutes, repo_data, premium_by_model, lfs_summary, storage_analysis
):
    print("  6. QUICK RECOMMENDATIONS")
    print(f"  {'─' * 55}")
    recs = []

    free_min_limit = 2000
    min_pct = (user_minutes / free_min_limit * 100) if user_minutes else 0
    if min_pct > 80:
        recs.append(
            "Upgrade from free tier or optimize Actions workflows — you're near your minute limit."
        )

    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    if sorted_repos and len(sorted_repos) > 1 and user_minutes > 0:
        top2_sum = sorted_repos[0][1] + sorted_repos[1][1]
        if top2_sum / user_minutes * 100 > 70:
            recs.append(
                f"Top 2 repos consume {top2_sum / user_minutes * 100:.0f}% of Actions — consider self-hosted runners to save."
            )

    if premium_by_model:
        models = list(premium_by_model.keys())
        if len(models) > 2:
            recs.append(
                f"Using {len(models)} Copilot models — consolidate to reduce cost complexity."
            )

    if lfs_summary and lfs_summary.get("total_gross", 0) > 0:
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
                recs.append(
                    f"Release assets in {top_st['name']} use {fmt_price(total_release_size)} — consider using GitHub Pages or external storage for large binaries."
                )

    if not recs:
        recs.append("Usage is well within free tiers — no immediate action needed.")
        recs.append("Consider enabling cost alerts in GitHub billing settings.")
    for i, rec in enumerate(recs, 1):
        print(f"\n    {i}. {rec}")
    print()
