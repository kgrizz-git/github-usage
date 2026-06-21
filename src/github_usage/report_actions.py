"""GitHub Actions sections for the legacy report."""

from __future__ import annotations

from .billing import get_actions_from_runs, get_actions_per_repo
from .report_helpers import fmt_price, gb_hours_to_avg_mb
from .terminal import print_section, print_sep


def show_actions_summary(api, username, user_minutes, user_storage_gb_hours, sku_breakdown):
    """Print the Actions compute and storage summary with per-SKU cost breakdown."""
    print_section("GitHub Actions Usage")
    print("  Summary:")
    print(f"    Compute Minutes:    {user_minutes:>10.1f} min")
    print(f"    Storage (GB-hrs):   {user_storage_gb_hours:>10.4f} GB-hrs")
    print(f"    Avg Storage (MB):   {gb_hours_to_avg_mb(user_storage_gb_hours):>10.1f} MB")
    print()

    # Per-SKU breakdown
    print("  Per-SKU Breakdown:")
    print(f"    {'SKU':<30} {'QTY':>10} {'UNIT':<18} {'GROSS':>10} {'DISCOUNT':>10} {'NET':>10}")
    print(f"    {'-' * 30} {'-' * 10} {'-' * 18} {'-' * 10} {'-' * 10} {'-' * 10}")
    for sku, item in sku_breakdown.items():
        qty = item.get("grossQuantity", 0)
        unit = item.get("unitType", "")
        gross = item.get("grossAmount", 0)
        discount = item.get("discountAmount", 0)
        net = item.get("netAmount", 0)
        print(
            f"    {sku:<30} {qty:>10.4f} {unit:<18} {fmt_price(gross):>10} {fmt_price(discount):>10} {fmt_price(net):>10}"
        )
    print()


def show_actions_per_repo(api, repos):
    """Print per-repository Actions minutes, storage, and gross cost; return row data."""
    print_section("Per-Repository Actions Breakdown")
    print(f"  {'REPO':<45} {'MINUTES':>10} {'GB-HRS':>10} {'AVG MB':>10} {'GROSS':>10}")
    print(f"  {'-' * 45} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10}")

    repo_data = []
    for repo in repos:
        owner = (repo.get("owner") or {}).get("login", "")
        name = repo.get("name", "")
        if not owner or not name:
            continue
        full = f"{owner}/{name}"
        minutes, storage_gb_hours, sku = get_actions_per_repo(api, owner, name)
        avg_mb = gb_hours_to_avg_mb(storage_gb_hours)
        gross = sum(i.get("grossAmount", 0) for i in sku.values())
        repo_data.append((full, minutes, storage_gb_hours, avg_mb, gross, sku))
        print(
            f"  {full:<45} {minutes:>10.1f} {storage_gb_hours:>10.4f} {avg_mb:>10.1f} {fmt_price(gross):>10}"
        )

    total_mins = sum(r[1] for r in repo_data)
    total_gb = sum(r[2] for r in repo_data)
    total_mb = gb_hours_to_avg_mb(total_gb)
    total_gross = sum(r[4] for r in repo_data)
    print(f"  {'-' * 45} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10}")
    print(
        f"  {'TOTAL':<45} {total_mins:>10.1f} {total_gb:>10.4f} {total_mb:>10.1f} {fmt_price(total_gross):>10}"
    )
    print()
    return repo_data


def show_actions_top_consumers(repo_data):
    """Print the top 10 repositories ranked by Actions minutes consumed."""
    print_sep("Top 10 Repos by Actions Minutes")
    print()
    sorted_repos = sorted(repo_data, key=lambda x: x[1], reverse=True)
    for full, minutes, _, avg_mb, _gross, _ in sorted_repos[:10]:
        print(f"    {minutes:>8.1f} min | {avg_mb:>8.1f} MB | {full}")
    print()


def show_actions_os_breakdown(api, repos):
    """Show Ubuntu/Windows/macOS breakdown for top repos."""
    print_sep("Actions Compute by OS (from workflow runs)")
    print()
    total_os = {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}
    found = False
    for repo in repos[:10]:
        owner = (repo.get("owner") or {}).get("login", "")
        name = repo.get("name", "")
        if not owner or not name:
            continue
        minutes, os_millis, _ = get_actions_from_runs(api, owner, name)
        if minutes > 0:
            found = True
            print(f"  {owner}/{name}:")
            for os_name in ["UBUNTU", "WINDOWS", "MACOS"]:
                mins = os_millis[os_name] / 60000
                total_os[os_name] += os_millis[os_name]
                if mins > 0:
                    print(f"    {os_name:<10} {mins:>8.1f} min")
            print()
    if found:
        print("  TOTAL:")
        for os_name in ["UBUNTU", "WINDOWS", "MACOS"]:
            mins = total_os[os_name] / 60000
            if mins > 0:
                print(f"    {os_name:<10} {mins:>8.1f} min")
    else:
        print("  No detailed OS breakdown available from workflow runs API.")
        print("  (Use the Actions Summary above for total minutes by OS type)")
    print()


def show_limits_summary(username, user_minutes, user_storage_gb_hours):
    """Print free-tier usage vs. limit for Actions minutes and storage."""
    print_section("Limits Summary")

    # Actions limits (free tier)
    min_limit = 2000
    min_remaining = max(0, min_limit - user_minutes) if user_minutes else min_limit
    min_pct = (user_minutes / min_limit * 100) if user_minutes and min_limit else 0

    # Storage: free tier is 500MB, but we track GB-hrs
    # Convert GB-hrs to average MB for comparison
    avg_storage_mb = gb_hours_to_avg_mb(user_storage_gb_hours) if user_storage_gb_hours else 0
    storage_limit = 500  # MB
    storage_remaining = max(0, storage_limit - avg_storage_mb)
    storage_pct = (avg_storage_mb / storage_limit * 100) if storage_limit else 0

    # Copilot: Copilot Pro includes premium requests
    # copilot_summary = get_billing_summary(GitHubAPI(""), username, "Copilot")

    print("  Actions Minutes:")
    print(f"    Used:         {user_minutes:>8.1f} / {min_limit} min")
    print(f"    Remaining:    {min_remaining:>8.1f} min ({min_pct:.1f}% used)")
    print()
    print("  Actions Storage (avg):")
    print(f"    Used:         {avg_storage_mb:>8.1f} / {storage_limit} MB")
    print(f"    Remaining:    {storage_remaining:>8.1f} MB ({storage_pct:.1f}% used)")
    print()

    # Copilot limits note
    print("  Copilot Pro:")
    print("    Includes: Copilot Chat, Copilot Agent, Code Review, etc.")
    print("    Premium requests are billed at $0.04/request after included allowance.")
    print("    (Check your plan details for exact premium request limits)")
    print()
