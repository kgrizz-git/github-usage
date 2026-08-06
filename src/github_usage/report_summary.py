"""Final summary section for the legacy report."""

from __future__ import annotations

from .billing import get_premium_request_usage
from .repo_consumers import private_list_is_redundant
from .report_actions_limits import _print_usage_by_visibility
from .report_helpers import fmt_price, repo_label
from .report_summary_insights import (
    _print_impactful_findings,
    _print_recommendations,
    _print_utilization,
)
from .terminal import print_section
from .visibility import repo_visibility, visibility_label


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

    total_gross = (actions_gross or 0) + copilot_gross + lfs_gross
    total_discount = (actions_discount or 0) + copilot_discount + lfs_discount
    total_net = (
        (actions_net or 0) + (copilot_summary["total_net"] if copilot_summary else 0) + lfs_net
    )

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


def render_final_summary_from_data(data: dict) -> None:
    """Print final summary from a legacy report superset dict (no API)."""
    actions = data.get("actions") or {}
    monthly = data.get("monthly_costs") or {}
    actions_costs = monthly.get("actions") or {}
    user_minutes = actions.get("minutes", 0)
    user_storage_gb_hours = actions.get("storage_gb_hours", 0)
    actions_gross = actions_costs.get("gross", 0)
    actions_discount = actions_costs.get("discount", 0)
    actions_net = actions_costs.get("net", 0)
    repo_data = [
        (
            row["repo"],
            row["minutes"],
            row["storage_gb_hours"],
            row["avg_mb"],
            row["gross"],
            row.get("sku", {}),
        )
        for row in data.get("repo_actions") or []
    ]
    copilot_summary = data.get("copilot_billing")
    lfs_summary = data.get("lfs_billing")
    storage_analysis = data.get("storage_analysis") or {"repos": []}
    premium_by_model = data.get("copilot_premium")
    if premium_by_model is None:
        copilot = data.get("copilot")
        by_model = (copilot or {}).get("by_model") or {}
        if by_model:
            premium_by_model = {
                model: {
                    "total_requests": values.get("requests", 0),
                    "total_gross": values.get("gross", 0),
                    "total_discount": values.get("discount", 0),
                    "total_net": values.get("net", 0),
                    "items": [],
                }
                for model, values in by_model.items()
            }

    visibility_by_repo = {
        row["repo"]: repo_visibility(row) for row in (data.get("repo_actions") or [])
    }

    print_section("FINAL SUMMARY — Key Insights & Biggest Consumers")
    copilot_gross = copilot_summary["total_gross"] if copilot_summary else 0
    copilot_discount = copilot_summary["total_discount"] if copilot_summary else 0
    lfs_gross = lfs_summary["total_gross"] if lfs_summary else 0
    lfs_discount = lfs_summary["total_discount"] if lfs_summary else 0
    lfs_net = lfs_summary["total_net"] if lfs_summary else 0
    total_gross = (actions_gross or 0) + copilot_gross + lfs_gross
    total_discount = (actions_discount or 0) + copilot_discount + lfs_discount
    total_net = (
        (actions_net or 0) + (copilot_summary["total_net"] if copilot_summary else 0) + lfs_net
    )
    _print_cost_overview(total_gross, total_discount, total_net)
    if "private_minutes" in actions:
        print("  1.5 PRIVATE vs PUBLIC ACTIONS")
        print(f"  {'─' * 55}")
        _print_usage_by_visibility(actions)
    _print_top_consumers(
        user_minutes,
        actions_gross,
        repo_data,
        premium_by_model,
        lfs_summary,
        visibility_by_repo,
        repo_consumers=data.get("repo_consumers"),
        private_minutes=actions.get("private_minutes"),
    )
    _print_storage_breakdown(storage_analysis)
    _print_utilization(user_minutes, user_storage_gb_hours, actions=actions)
    _print_impactful_findings(
        user_minutes,
        actions_gross,
        total_gross,
        total_discount,
        total_net,
        repo_data,
        premium_by_model,
        storage_analysis,
        visibility_by_repo,
        actions=actions,
        repo_consumers=data.get("repo_consumers"),
    )
    _print_recommendations(
        user_minutes,
        repo_data,
        premium_by_model,
        lfs_summary,
        storage_analysis,
        visibility_by_repo,
        actions=actions,
        repo_consumers=data.get("repo_consumers"),
    )


def _print_cost_overview(total_gross, total_discount, total_net):
    print("\n  1. COST OVERVIEW")
    print(f"  {'─' * 55}")
    print(f"    Total Gross:     {fmt_price(total_gross or 0):>12}")

    discount_pct = 0.0
    if (total_gross or 0) > 0:
        discount_pct = (total_discount or 0) / total_gross * 100

    print(f"    Total Discount:  {fmt_price(total_discount or 0):>12}  ({discount_pct:.1f}% off)")
    print(f"    Total Net:       {fmt_price(total_net or 0):>12}")
    print()


def _print_top_consumers(
    user_minutes,
    actions_gross,
    repo_data,
    premium_by_model,
    lfs_summary,
    visibility_by_repo=None,
    *,
    repo_consumers=None,
    private_minutes=None,
):
    print("  2. BIGGEST CONSUMERS BY CATEGORY")
    print(f"  {'─' * 55}")

    # Actions — top repos by minutes
    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True) if repo_data else []
    print("\n    Actions Minutes (top 5 repos):")
    for full, mins, _gb, _avg_mb, gross, _ in sorted_repos[:5]:
        pct = mins / user_minutes * 100 if user_minutes and user_minutes > 0 else 0
        label = repo_label(full, visibility_by_repo)
        print(f"      {label:<45} {mins:>8.1f} min  ({pct:5.1f}%)  {fmt_price(gross)}")
    if not sorted_repos:
        print("      No Actions usage found.")
    print()

    # Actions — top repos by cost
    sorted_by_cost = sorted(repo_data, key=lambda x: x[4], reverse=True) if repo_data else []
    print("    Actions Cost (top 5 repos):")
    for full, _mins, _gb, _avg_mb, gross, _ in sorted_by_cost[:5]:
        pct = gross / actions_gross * 100 if (actions_gross or 0) > 0 else 0
        label = repo_label(full, visibility_by_repo)
        print(f"      {label:<45} {fmt_price(gross):>10}  ({pct:5.1f}%)")
    print()

    if repo_consumers:
        by_minutes = repo_consumers.get("by_minutes") or []
        by_minutes_private = repo_consumers.get("by_minutes_private") or []
        if by_minutes_private and not private_list_is_redundant(
            by_minutes[:5], by_minutes_private[:5]
        ):
            print("    Private Actions Minutes (top 5 repos):")
            for row in by_minutes_private[:5]:
                mins = row["minutes"]
                pct = (
                    mins / private_minutes * 100.0
                    if private_minutes and private_minutes > 0
                    else 0.0
                )
                label = repo_label(row["repo"], visibility_by_repo)
                print(f"      {label:<45} {mins:>8.1f} min  ({pct:5.1f}% of private minutes)")
            print()

        by_storage = repo_consumers.get("by_storage") or []
        if by_storage:
            print("    Actions Storage (top 5 repos, billed):")
            for row in by_storage[:5]:
                label = repo_label(row["repo"], visibility_by_repo)
                print(f"      {label:<45} {row['storage_avg_mb']:>8.1f} MB")
            print()

        by_storage_private = repo_consumers.get("by_storage_private") or []
        if by_storage_private and not private_list_is_redundant(
            by_storage[:5], by_storage_private[:5]
        ):
            print("    Private Actions Storage (top 5 repos, billed):")
            for row in by_storage_private[:5]:
                label = repo_label(row["repo"], visibility_by_repo)
                print(f"      {label:<45} {row['storage_avg_mb']:>8.1f} MB")
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
            label = f"{r['name']}{visibility_label(repo_visibility(r))}"
            print(f"      {label:<45} {r['total_storage']:>10.2f} GB")
        print()

        private_top = sorted(
            (
                r
                for r in storage_analysis.get("repos", [])
                if repo_visibility(r) in ("private", "internal")
            ),
            key=lambda x: (-x["total_storage"], x["name"]),
        )[:10]
        if private_top and not private_list_is_redundant(sorted_by_storage[:10], private_top):
            print("    Top 10 Private Repos by Storage (scan)")
            print(f"    {'REPO':<45} {'TOTAL':>10}")
            print(f"    {'-' * 45} {'-' * 10}")
            for r in private_top:
                label = f"{r['name']}{visibility_label(repo_visibility(r))}"
                print(f"      {label:<45} {r['total_storage']:>10.2f} GB")
            print()

        top_storage = sorted_by_storage[0]
        top_label = f"{top_storage['name']}{visibility_label(repo_visibility(top_storage))}"
        print(f"    Top storage consumer: {top_label} ({top_storage['total_storage']:.2f} GB)")
        print("    Breakdown:")
        for item in top_storage.get("items", []):
            print(
                f"      {item['type']:<20} {item['count']:>5} items  {item['storage']:>10.2f} GB  ({item['size']})"
            )
        print()
    else:
        print("    No storage data available from repositories.\n")
