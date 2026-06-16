#!/usr/bin/env python3
"""
github-usage — GitHub Monthly Usage Report v3
  - Actions minutes & storage (with per-repo breakdown)
  - Copilot requests (premium + cloud agent, by model)
  - Git LFS usage
  - Per-SKU cost breakdown (gross, discount, net)
  - Monthly totals and limits
  - Final summary: biggest resource consumers, base costs, key insights

Usage:
    ./github-usage [GITHUB_TOKEN]
    python3 -m github_usage [GITHUB_TOKEN]

Token resolution (first match wins):
    1. Command-line argument
    2. GITHUB_TOKEN environment variable
    3. `gh auth token` output
    4. ~/.config/github-cli/github.yaml (oauth_token field)
"""

# Token discovery intentionally shells out to the GitHub CLI.
import json
import os
import subprocess  # nosec B404
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .report_helpers import (
    fmt_price as shared_fmt_price,
)
from .report_helpers import (
    gb_hours_to_avg_mb as shared_gb_hours_to_avg_mb,
)
from .report_helpers import (
    hours_in_month,
)

UTC = UTC

# ── Token Resolution ────────────────────────────────────────────────────


def resolve_token():
    if len(sys.argv) > 1:
        return sys.argv[1]
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:
        # Fixed gh CLI invocation, no user-controlled executable.
        result = subprocess.run(  # nosec
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    config = Path.home() / ".config" / "github-cli" / "github.yaml"
    if config.exists():
        content = config.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("oauth_token:"):
                token = line.split(":", 1)[1].strip().strip("'\"")
                if token:
                    return token
    return None


# ── GitHub API Helper ───────────────────────────────────────────────────


def check_user_scope(api):
    """Check if the token has the 'user' scope required for billing endpoints.
    Returns True if scope is present, False otherwise."""
    import http.client

    conn = http.client.HTTPSConnection("api.github.com")
    conn.request("GET", "/user", headers=api.headers)
    resp = conn.getresponse()
    scopes_header = resp.getheader("X-OAuth-Scopes", "")
    resp.read()  # consume response
    scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
    return "user" in scopes


class GitHubAPI:
    def __init__(self, token):
        self.token = token
        self.base = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-usage-report-v3",
        }

    def request(self, method, path, params=None):
        import http.client

        url = path
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query}"
        conn = http.client.HTTPSConnection("api.github.com")
        req_headers = {**self.headers}
        conn.request(method, url, headers=req_headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        if resp.status in (200, 201, 202, 204):
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return {}
            return {}
        elif resp.status == 403:
            try:
                body = json.loads(data) if data else {}
            except json.JSONDecodeError:
                body = {}
            reset = int(body.get("retry-after", 0) or 0)
            if reset > 0:
                time.sleep(reset + 1)
                return self.request(method, path, params)
            raise RuntimeError(f"API error 403: {data[:200]}")
        elif resp.status == 404:
            # Check if this is a billing endpoint that needs 'user' scope
            if "billing" in path and "settings" in path:
                raise RuntimeError(
                    f"API error 404 on billing endpoint '{path}'. "
                    f"This usually means your token is missing the 'user' scope. "
                    f"Fix: run 'gh auth refresh -h github.com -s user'"
                )
            raise RuntimeError(f"API error 404: {data[:200]}")
        else:
            raise RuntimeError(f"API error {resp.status}: {data[:200]}")

    def get_all_pages(self, path, params=None):
        all_items = []
        page = 1
        per_page = 100
        while True:
            result = self.request(
                "GET", path, {**(params or {}), "page": page, "per_page": per_page}
            )
            if not result:
                break
            if isinstance(result, list):
                all_items.extend(result)
                if len(result) < per_page:
                    break
                page += 1
            else:
                break
        return all_items


# ── Helpers ─────────────────────────────────────────────────────────────


def hours_in_current_month():
    return hours_in_month()


def gb_hours_to_avg_mb(gb_hours):
    return shared_gb_hours_to_avg_mb(gb_hours)


def fmt_price(v):
    return shared_fmt_price(v)


# ── Billing Data Collectors ─────────────────────────────────────────────


def get_billing_summary(api, username, product):
    """Get usage summary for a product. Returns parsed items dict keyed by sku."""
    try:
        billing = api.request(
            "GET", f"/users/{username}/settings/billing/usage/summary", {"product": product}
        )
    except RuntimeError:
        return None
    if not billing:
        return None
    items = billing.get("usageItems", [])
    summary = {"raw": billing, "items": {}, "total_gross": 0, "total_discount": 0, "total_net": 0}
    for item in items:
        sku = item.get("sku", item.get("product", "unknown"))
        summary["items"][sku] = item
        summary["total_gross"] += item.get("grossAmount", 0)
        summary["total_discount"] += item.get("discountAmount", 0)
        summary["total_net"] += item.get("netAmount", 0)
    return summary


def get_premium_request_usage(api, username, product="copilot", model=None):
    """Get premium request usage breakdown by model."""
    params = {"product": product}
    if model:
        params["model"] = model
    try:
        data = api.request(
            "GET",
            f"/users/{username}/settings/billing/premium_request/usage",
            params if params else None,
        )
    except RuntimeError:
        return None
    if not data:
        return None
    items = data.get("usageItems", [])
    by_model = {}
    for item in items:
        m = item.get("model", "Unknown")
        if m not in by_model:
            by_model[m] = {
                "items": [],
                "total_requests": 0,
                "total_gross": 0,
                "total_discount": 0,
                "total_net": 0,
            }
        by_model[m]["items"].append(item)
        by_model[m]["total_requests"] += item.get("grossQuantity", 0)
        by_model[m]["total_gross"] += item.get("grossAmount", 0)
        by_model[m]["total_discount"] += item.get("discountAmount", 0)
        by_model[m]["total_net"] += item.get("netAmount", 0)
    return by_model


def get_full_billing(api, username):
    """Get full billing usage report (all products, all time this year)."""
    try:
        data = api.request("GET", f"/users/{username}/settings/billing/usage")
    except RuntimeError:
        return None
    if not data:
        return None
    return data.get("usageItems", [])


def get_user_actions_billing(api, username):
    """Get user-level Actions billing. Returns (total_minutes, storage_gb_hours, sku_breakdown)."""
    summary = get_billing_summary(api, username, "Actions")
    if not summary:
        return None, None, {}
    total_minutes = 0.0
    total_storage_gb_hours = 0.0
    sku_breakdown = {}
    for sku, item in summary["items"].items():
        unit = item.get("unitType", "")
        qty = item.get("grossQuantity", 0)
        if unit == "minutes":
            total_minutes += qty
        elif unit == "gigabyte-hours":
            total_storage_gb_hours += qty
        sku_breakdown[sku] = item
    return total_minutes, total_storage_gb_hours, sku_breakdown


def get_actions_per_repo(api, owner, repo):
    """Get per-repo Actions billing."""
    try:
        billing = api.request(
            "GET",
            f"/users/{owner}/settings/billing/usage/summary",
            {"product": "Actions", "repository": f"{owner}/{repo}"},
        )
    except RuntimeError:
        return 0.0, 0.0, {}
    if not billing:
        return 0.0, 0.0, {}
    total_minutes = 0.0
    total_storage_gb_hours = 0.0
    sku_breakdown = {}
    for item in billing.get("usageItems", []):
        sku = item.get("sku", "unknown")
        unit = item.get("unitType", "")
        qty = item.get("grossQuantity", 0)
        if unit == "minutes":
            total_minutes += qty
        elif unit == "gigabyte-hours":
            total_storage_gb_hours += qty
        sku_breakdown[sku] = item
    return total_minutes, total_storage_gb_hours, sku_breakdown


def get_actions_from_runs(api, owner, repo):
    """Fallback: calculate minutes from workflow runs."""
    first_day = date.today().replace(day=1)
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    created_range = f"{first_day.isoformat()}..{last_day.isoformat()}"
    runs = api.get_all_pages(
        f"/repos/{owner}/{repo}/actions/runs",
        {"created": created_range, "per_page": 100},
    )
    total_minutes = 0.0
    workflow_minutes = {}
    os_minutes = {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}
    for run in runs:
        billable = run.get("billable") or {}
        for os_name in ["UBUNTU", "WINDOWS", "MACOS"]:
            millis = billable.get(os_name, {}).get("millis", 0)
            os_minutes[os_name] += millis
            total_minutes += millis / 60000
        wf_name = run.get("workflow_name", "Unknown")
        workflow_minutes[wf_name] = workflow_minutes.get(wf_name, 0) + total_minutes
    return round(total_minutes, 1), os_minutes, workflow_minutes


# ── Report Sections ─────────────────────────────────────────────────────


def print_header():
    print("=" * 70)
    print("        GitHub Monthly Usage Report v3")
    print("=" * 70)
    print()


def print_sep(title):
    print(f"── {title} {'─' * (60 - len(title))}")


def print_section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def show_rate_limits(api):
    print_sep("API Rate Limit")
    data = api.request("GET", "/rate_limit")
    resources = data.get("resources", {})

    # Standard limits
    print()
    for name, key in [
        ("Core API", "core"),
        ("GraphQL API", "graphql"),
        ("Search API", "search"),
        ("Code Scanning", "code_scanning_upload"),
    ]:
        r = resources.get(key, {})
        rem = r.get("remaining", "?")
        lim = r.get("limit", "?")
        used = r.get("used", 0)
        reset_ts = r.get("reset", 0)
        reset_str = ""
        if reset_ts:
            reset_str = (
                f"  (resets {datetime.fromtimestamp(reset_ts, tz=UTC).strftime('%H:%M UTC')})"
            )
        print(f"  {name:<25} {rem:>6} / {lim:<6} remaining{reset_str}")

    # Premium / high-tier
    print()
    print("  Premium API tiers:")
    for name, res in resources.items():
        limit = res.get("limit", 0)
        used = res.get("used", 0)
        if limit > 5000:
            pct = (used / limit * 100) if limit else 0
            print(f"    {name:<35} {used:>6} / {limit:<6} ({pct:.1f}% used)")
    print()


def show_account_info(api):
    print_sep("Account Info")
    user = api.request("GET", "/user")
    username = user.get("login", "?")
    user_type = user.get("type", "?")
    plan = user.get("plan", {})

    print(f"  Username:   {username}")
    print(f"  Account:    {user_type}")
    if plan:
        plan_name = plan.get("name", "?")
        space = plan.get("space", "?")
        collaborators = plan.get("collaborators", "?")
        private_repos = plan.get("private_repos", "?")
        print(f"  Plan:       {plan_name}")
        if space and space != 0:
            space_gb = space / (1024 * 1024 * 1024) if isinstance(space, int | float) else space
            print(f"  Space:      {space_gb:.1f} GB available")
        if collaborators:
            print(f"  Collaborators: {collaborators}")
        if private_repos:
            print(f"  Private repos: {private_repos} allowed")
    print()
    return username, user_type


def show_actions_summary(api, username, user_minutes, user_storage_gb_hours, sku_breakdown):
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
    print_section("Per-Repository Actions Breakdown")
    print(f"  {'REPO':<45} {'MINUTES':>10} {'GB-HRS':>10} {'AVG MB':>10} {'GROSS':>10}")
    print(f"  {'-' * 45} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10}")

    repo_data = []
    for repo in repos:
        owner = repo["owner"]["login"]
        name = repo["name"]
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
        owner = repo["owner"]["login"]
        name = repo["name"]
        minutes, os_millis, _ = get_actions_from_runs(api, owner, name)
        if minutes > 0:
            found = True
            print(f"  {owner}/{name}:")
            for os_name in ["UBUNTU", "WINDOWS", "MACOS"]:
                mins = os_millis[os_name] / 60000
                total_os[os_name] += os_millis
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


def show_copilot_summary(api, username):
    print_section("GitHub Copilot Usage")

    # Summary
    summary = get_billing_summary(api, username, "Copilot")
    if not summary:
        print("  No Copilot usage data found.")
        print()
        return

    items = summary["items"]
    total_requests = 0
    total_gross = 0
    total_discount = 0
    total_net = 0

    print("  Summary:")
    for sku, item in items.items():
        qty = item.get("grossQuantity", 0)
        unit = item.get("unitType", "")
        gross = item.get("grossAmount", 0)
        discount = item.get("discountAmount", 0)
        net = item.get("netAmount", 0)
        price = item.get("pricePerUnit", 0)
        total_requests += qty
        total_gross += gross
        total_discount += discount
        total_net += net
        print(
            f"    {sku:<35} {qty:>10.2f} {unit:<10} @ {fmt_price(price)}/ea | gross: {fmt_price(gross)} | discount: {fmt_price(discount)} | net: {fmt_price(net)}"
        )
    print()
    print(
        f"    {'TOTAL':<35} {total_requests:>10.2f} requests | gross: {fmt_price(total_gross)} | discount: {fmt_price(total_discount)} | net: {fmt_price(total_net)}"
    )
    print()

    # By model breakdown
    print("  By Model:")
    premium_by_model = get_premium_request_usage(api, username)
    if not premium_by_model:
        print("    No model-level data available.")
        print()
        return

    for model, data in sorted(
        premium_by_model.items(), key=lambda x: x[1]["total_requests"], reverse=True
    ):
        print(f"    {model}:")
        print(f"      Total requests: {data['total_requests']:.2f}")
        print(
            f"      Gross: {fmt_price(data['total_gross'])} | Discount: {fmt_price(data['total_discount'])} | Net: {fmt_price(data['total_net'])}"
        )
        for item in data["items"]:
            sku = item.get("sku", "unknown")
            qty = item.get("grossQuantity", 0)
            price = item.get("pricePerUnit", 0)
            print(f"        {sku}: {qty:.2f} @ {fmt_price(price)}/ea")
        print()


def show_gitlfs_summary(api, username):
    print_section("Git LFS Usage")
    summary = get_billing_summary(api, username, "git_lfs")
    if not summary:
        print("  No Git LFS usage found.")
        print()
        return

    items = summary["items"]
    print(f"  {'SKU':<30} {'QTY':>10} {'UNIT':<18} {'GROSS':>10} {'DISCOUNT':>10} {'NET':>10}")
    print(f"  {'-' * 30} {'-' * 10} {'-' * 18} {'-' * 10} {'-' * 10} {'-' * 10}")
    for sku, item in items.items():
        qty = item.get("grossQuantity", 0)
        unit = item.get("unitType", "")
        gross = item.get("grossAmount", 0)
        discount = item.get("discountAmount", 0)
        net = item.get("netAmount", 0)
        print(
            f"    {sku:<30} {qty:>10.4f} {unit:<18} {fmt_price(gross):>10} {fmt_price(discount):>10} {fmt_price(net):>10}"
        )
    print()


def show_full_billing_history(api, username):
    """Show detailed billing history with all products."""
    print_section("Full Billing History (All Products)")
    full = get_full_billing(api, username)
    if not full:
        print("  No billing history available.")
        print()
        return

    # Aggregate by product+sku
    from collections import defaultdict

    agg = defaultdict(
        lambda: {
            "entries": 0,
            "total_qty": 0,
            "total_gross": 0,
            "total_discount": 0,
            "total_net": 0,
            "units": set(),
            "repos": set(),
            "months": set(),
        }
    )

    for item in full:
        prod = item.get("product", "unknown")
        sku = item.get("sku", "unknown")
        key = f"{prod}/{sku}"
        agg[key]["entries"] += 1
        agg[key]["total_qty"] += item.get("quantity", 0)
        agg[key]["total_gross"] += item.get("grossAmount", 0)
        agg[key]["total_discount"] += item.get("discountAmount", 0)
        agg[key]["total_net"] += item.get("netAmount", 0)
        agg[key]["units"].add(item.get("unitType", ""))
        repo = item.get("repositoryName", "")
        if repo:
            agg[key]["repos"].add(repo)
        dt = item.get("date", "")[:7]
        if dt:
            agg[key]["months"].add(dt)

    print(
        f"  {'PRODUCT/SKU':<40} {'ENRIES':>6} {'TOTAL QTY':>12} {'UNITS':<12} {'GROSS':>10} {'DISCOUNT':>10} {'NET':>10}"
    )
    print(f"  {'-' * 40} {'-' * 6} {'-' * 12} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 10}")

    for key in sorted(agg.keys()):
        d = agg[key]
        units = ", ".join(d["units"])
        repos = ", ".join(sorted(d["repos"]))[:30]
        months = ", ".join(sorted(d["months"]))
        qty_str = f"{d['total_qty']:.2f}"
        print(
            f"  {key:<40} {d['entries']:>6} {qty_str:>12} {units:<12} {fmt_price(d['total_gross']):>10} {fmt_price(d['total_discount']):>10} {fmt_price(d['total_net']):>10}"
        )
        if repos:
            print(f"    repos: {repos}")
        if months:
            print(f"    months: {months}")

    total_gross = sum(d["total_gross"] for d in agg.values())
    total_discount = sum(d["total_discount"] for d in agg.values())
    total_net = sum(d["total_net"] for d in agg.values())
    print(f"  {'-' * 40} {'-' * 6} {'-' * 12} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 10}")
    print(
        f"  {'TOTAL':<40} {'':>6} {'':>12} {'':>12} {fmt_price(total_gross):>10} {fmt_price(total_discount):>10} {fmt_price(total_net):>10}"
    )
    print()


def show_monthly_costs(repo_data, username, api):
    """Show estimated monthly costs for current month."""
    print_section("Current Month Cost Estimate")

    # Actions
    actions_summary = get_billing_summary(api, username, "Actions")
    actions_gross = actions_summary["total_gross"] if actions_summary else 0
    actions_discount = actions_summary["total_discount"] if actions_summary else 0
    actions_net = actions_summary["total_net"] if actions_summary else 0

    # Copilot
    copilot_summary = get_billing_summary(api, username, "Copilot")
    copilot_gross = copilot_summary["total_gross"] if copilot_summary else 0
    copilot_discount = copilot_summary["total_discount"] if copilot_summary else 0
    copilot_net = copilot_summary["total_net"] if copilot_summary else 0

    # Git LFS
    lfs_summary = get_billing_summary(api, username, "git_lfs")
    lfs_gross = lfs_summary["total_gross"] if lfs_summary else 0
    lfs_discount = lfs_summary["total_discount"] if lfs_summary else 0
    lfs_net = lfs_summary["total_net"] if lfs_summary else 0

    total_gross = actions_gross + copilot_gross + lfs_gross
    total_discount = actions_discount + copilot_discount + lfs_discount
    total_net = actions_net + copilot_net + lfs_net

    print(f"  {'Category':<25} {'GROSS':>12} {'DISCOUNT':>12} {'NET':>12}")
    print(f"  {'-' * 25} {'-' * 12} {'-' * 12} {'-' * 12}")
    print(
        f"  {'Actions':<25} {fmt_price(actions_gross):>12} {fmt_price(actions_discount):>12} {fmt_price(actions_net):>12}"
    )
    print(
        f"  {'Copilot':<25} {fmt_price(copilot_gross):>12} {fmt_price(copilot_discount):>12} {fmt_price(copilot_net):>12}"
    )
    print(
        f"  {'Git LFS':<25} {fmt_price(lfs_gross):>12} {fmt_price(lfs_discount):>12} {fmt_price(lfs_net):>12}"
    )
    print(f"  {'-' * 25} {'-' * 12} {'-' * 12} {'-' * 12}")
    print(
        f"  {'TOTAL':<25} {fmt_price(total_gross):>12} {fmt_price(total_discount):>12} {fmt_price(total_net):>12}"
    )
    print()

    if total_discount > 0:
        savings_pct = (total_discount / total_gross * 100) if total_gross > 0 else 0
        print(
            f"  You're saving {fmt_price(total_discount)} ({savings_pct:.1f}% discount) this month!"
        )
        print()


def show_limits_summary(username, user_minutes, user_storage_gb_hours):
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


def show_what_else(api, username):
    """Show info about other available data points."""
    print_section("Other Available Data Points")
    print("  Products available via billing API:")
    print("    - actions        : GitHub Actions compute & storage")
    print("    - copilot        : Copilot Chat, Agent, Code Review, etc.")
    print("    - git_lfs        : Git LFS storage")
    print("    - codespaces     : GitHub Codespaces compute & storage")
    print("    - packages       : GitHub Packages (npm, Docker, etc.)")
    print("    - models         : GitHub Models (LLM API usage)")
    print()
    print("  Other endpoints available:")
    print(f"    - /users/{username}/settings/billing/usage")
    print("      Full billing history (all products, daily granularity)")
    print(f"    - /users/{username}/settings/billing/premium_request/usage")
    print("      Premium request usage by model (Claude Sonnet 4.6, GPT-5.4, etc.)")
    print()
    print("  Rate limits tracked:")
    print("    - Core API:       5000/hour (authenticated)")
    print("    - GraphQL API:    5000/hour (authenticated)")
    print("    - Search API:     30/minute (full text search)")
    print("    - Code Scanning:  5000/hour")
    print("    - Actions Runner: 10000/hour (registration)")
    print("    - SCIM:           15000/hour (enterprise)")
    print("    - Audit Log:      1750/hour")
    print("    - Dependency:     100/hour (snapshots + SBOM)")
    print()


def get_storage_analysis(api, repos):
    """Analyze storage per repo: artifacts, releases, LFS."""
    repo_storage = []
    for repo in repos:
        owner = repo["owner"]["login"]
        name = repo["name"]
        full = f"{owner}/{name}"
        total_storage = 0.0
        items = []

        # Artifacts
        try:
            artifacts = api.get_all_pages(
                f"/repos/{owner}/{name}/actions/artifacts",
                {"per_page": 100},
            )
        except RuntimeError:
            artifacts = []
        for art in artifacts:
            size_bytes = art.get("size_in_bytes", 0)
            total_storage += size_bytes / (1024 * 1024 * 1024)
            items.append(
                {
                    "type": "Artifact",
                    "name": art.get("name", "Unknown"),
                    "count": 1,
                    "storage": size_bytes / (1024 * 1024 * 1024),
                    "size": f"{size_bytes / (1024 * 1024):.0f} MB",
                }
            )

        # Releases + assets
        try:
            releases = api.get_all_pages(
                f"/repos/{owner}/{name}/releases",
                {"per_page": 100},
            )
        except RuntimeError:
            releases = []
        for rel in releases:
            for asset in rel.get("assets", []):
                size_bytes = asset.get("size", 0)
                total_storage += size_bytes / (1024 * 1024 * 1024)
                items.append(
                    {
                        "type": "Release Asset",
                        "name": asset.get("name", "Unknown"),
                        "count": 1,
                        "storage": size_bytes / (1024 * 1024 * 1024),
                        "size": f"{size_bytes / (1024 * 1024):.0f} MB",
                    }
                )

        if total_storage > 0 or items:
            repo_storage.append(
                {
                    "name": full,
                    "total_storage": total_storage,
                    "items": items,
                }
            )

    return {"repos": repo_storage}


def show_base_costs(api, username, actions_sku, copilot_summary, lfs_summary):
    """Show per-unit base costs for all products."""
    print_section("Base Costs (Per-Unit Pricing)")

    # Actions base costs
    print("\n  Actions Compute:")
    actions_minutes_found = False
    for sku, item in (actions_sku or {}).items():
        if sku.startswith("_"):
            continue
        unit = item.get("unitType", "")
        price = item.get("pricePerUnit", 0)
        qty = item.get("grossQuantity", 0)
        net = item.get("netAmount", 0)
        if unit == "minutes":
            print(f"    {sku:<40} {fmt_price(price)}/min  × {qty:.1f} min  = {fmt_price(net)}")
            actions_minutes_found = True
    if not actions_minutes_found:
        print("    No compute minutes billed.")
    print("    Standard tier: ~$0.008/min (Linux), ~$0.016/min (Windows), ~$0.016/min (macOS)")
    print("    Free tier: 2,000 min/month for personal repos")
    print()

    print("  Actions Storage:")
    actions_storage_found = False
    for sku, item in (actions_sku or {}).items():
        if sku.startswith("_"):
            continue
        unit = item.get("unitType", "")
        price = item.get("pricePerUnit", 0)
        qty = item.get("grossQuantity", 0)
        net = item.get("netAmount", 0)
        if unit == "gigabyte-hours":
            avg_mb = gb_hours_to_avg_mb(qty)
            print(
                f"    {sku:<40} {fmt_price(price)}/GB-hr  × {qty:.2f} GB-hrs ({avg_mb:.0f} MB avg)  = {fmt_price(net)}"
            )
            actions_storage_found = True
    if not actions_storage_found:
        print("    No storage billed.")
    print("    Standard: ~$0.01/GB-month")
    print("    Free tier: 500 MB for personal repos")
    print()

    print("  Copilot Premium Requests:")
    copilot_found = False
    if copilot_summary and copilot_summary["items"]:
        all_prices = set()
        for sku, item in copilot_summary["items"].items():
            price = item.get("pricePerUnit", 0)
            qty = item.get("grossQuantity", 0)
            if price > 0:
                print(
                    f"    {sku:<40} {fmt_price(price)}/req  × {qty:.0f} reqs  = {fmt_price(item.get('netAmount', 0))}"
                )
                copilot_found = True
                all_prices.add(price)
        if all_prices:
            print(f"    Base rate: {max(all_prices):.4f}/req (highest observed)")
    if not copilot_found:
        print("    No premium requests billed.")
    print("    Copilot Pro: ~$0.04-0.08/request for premium features")
    print()

    print("  Git LFS:")
    lfs_found = False
    if lfs_summary and lfs_summary["items"]:
        for sku, item in lfs_summary["items"].items():
            price = item.get("pricePerUnit", 0)
            qty = item.get("grossQuantity", 0)
            if price > 0:
                print(
                    f"    {sku:<40} {fmt_price(price)}/GB  × {qty:.2f} GB  = {fmt_price(item.get('netAmount', 0))}"
                )
                lfs_found = True
    if not lfs_found:
        print("    No LFS storage billed.")
    print("    Standard: ~$1/GB-month after 1 GB free")
    print()


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

    # ── Aggregate totals ──
    copilot_gross = copilot_summary["total_gross"] if copilot_summary else 0
    copilot_discount = copilot_summary["total_discount"] if copilot_summary else 0
    copilot_net = copilot_summary["total_net"] if copilot_summary else 0
    lfs_gross = lfs_summary["total_gross"] if lfs_summary else 0
    lfs_discount = lfs_summary["total_discount"] if lfs_summary else 0
    lfs_net = lfs_summary["total_net"] if lfs_summary else 0

    total_gross = actions_gross + copilot_gross + lfs_gross
    total_discount = actions_discount + copilot_discount + lfs_discount
    total_net = actions_net + copilot_net + lfs_net

    # ── 1. Cost Overview ──
    print("\n  1. COST OVERVIEW")
    print(f"  {'─' * 55}")
    print(f"    Total Gross:     {fmt_price(total_gross):>12}")
    print(
        f"    Total Discount:  {fmt_price(total_discount):>12}  ({total_discount / total_gross * 100:.1f}% off)"
    )
    print(f"    Total Net:       {fmt_price(total_net):>12}")
    print()

    # ── 2. Biggest Consumers by Category ──
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
    premium_by_model = get_premium_request_usage(api, username)
    if premium_by_model:
        for model, data in sorted(
            premium_by_model.items(), key=lambda x: x[1]["total_requests"], reverse=True
        ):
            # Find price per unit from items
            price = 0
            for item in data["items"]:
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
    if lfs_summary and lfs_summary["items"]:
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

    # ── 3. Storage Breakdown by Repo (Artifacts, Releases, LFS) ──
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

        # Top repo detail
        if sorted_by_storage:
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
        print("    No storage data available from repositories.")
        print()

    # ── 4. Resource Utilization vs Limits ──
    print("  4. RESOURCE UTILIZATION vs LIMITS")
    print(f"  {'─' * 55}")

    # Actions minutes
    free_min_limit = 2000
    min_pct = (user_minutes / free_min_limit * 100) if user_minutes else 0
    min_bar_len = 40
    min_filled = int(min_pct / 100 * min_bar_len)
    print(
        f"\n    Actions Minutes:     {user_minutes:>8.1f} / {free_min_limit} min ({min_pct:.1f}% of free tier)"
    )
    print(f"    {'█' * min_filled}{'░' * (min_bar_len - min_filled)}")
    if min_pct > 80:
        print("    ⚠ HIGH USAGE — approaching free tier limit!")
    elif min_pct > 50:
        print("    → Moderate usage — on track to use half your free allowance")
    print()

    # Actions storage
    free_storage_mb = 500
    avg_storage_mb = gb_hours_to_avg_mb(user_storage_gb_hours) if user_storage_gb_hours else 0
    storage_pct = (avg_storage_mb / free_storage_mb * 100) if user_storage_gb_hours else 0
    storage_filled = int(storage_pct / 100 * min_bar_len)
    print(
        f"    Actions Storage:     {avg_storage_mb:>8.1f} / {free_storage_mb} MB ({storage_pct:.1f}% of free tier)"
    )
    print(f"    {'█' * storage_filled}{'░' * (min_bar_len - storage_filled)}")
    if storage_pct > 80:
        print("    ⚠ HIGH USAGE — approaching free tier limit!")
    elif storage_pct > 50:
        print("    → Moderate usage — on track to use half your free allowance")
    print()

    # ── 5. Top 3 Most Impactful Findings ──
    print("  5. TOP 3 MOST IMPACTFUL FINDINGS")
    print(f"  {'─' * 55}")

    findings = []

    # Finding 1: Biggest actions consumer
    if sorted_repos:
        top_repo = sorted_repos[0]
        pct_of_total = top_repo[1] / user_minutes * 100 if user_minutes else 0
        findings.append(
            f"Biggest Actions consumer: {top_repo[0]} at {top_repo[1]:.0f} min ({pct_of_total:.1f}% of total)"
        )

    # Finding 2: Highest cost repo
    if sorted_by_cost:
        top_cost = sorted_by_cost[0]
        pct_cost = top_cost[4] / actions_gross * 100 if actions_gross else 0
        findings.append(
            f"Highest Actions cost: {top_cost[0]} at {fmt_price(top_cost[4])} ({pct_cost:.1f}% of total)"
        )

    # Finding 3: Storage consumer
    if sorted_by_storage:
        top_st = sorted_by_storage[0]
        total_gb = top_st["total_storage"]
        size_str = f"{total_gb:.2f} GB" if total_gb >= 1 else f"{total_gb * 1024:.0f} MB"
        findings.append(
            f"Biggest storage consumer: {top_st['name']} at {fmt_price(top_st['total_storage'])} ({size_str})"
        )

    # Finding 4: Copilot model breakdown
    if premium_by_model:
        top_model = max(premium_by_model.items(), key=lambda x: x[1]["total_requests"])
        findings.append(
            f"Most-used Copilot model: {top_model[0]} with {top_model[1]['total_requests']:.0f} requests"
        )

    # Finding 5: Overall savings
    if total_discount > 0:
        findings.append(
            f"Monthly savings from discounts: {fmt_price(total_discount)} ({total_discount / total_gross * 100:.1f}% off gross)"
        )

    # Finding 6: Cost efficiency
    if total_net > 0 and user_minutes > 0:
        cost_per_min = total_net / user_minutes
        findings.append(
            f"Effective cost per Actions minute: {fmt_price(cost_per_min)} (all products averaged)"
        )

    for i, finding in enumerate(findings[:3], 1):
        print(f"\n    {i}. {finding}")
    print()

    # ── 6. Recommendations ──
    print("  6. QUICK RECOMMENDATIONS")
    print(f"  {'─' * 55}")
    recs = []
    if min_pct > 80:
        recs.append(
            "Upgrade from free tier or optimize Actions workflows — you're near your minute limit."
        )
    if sorted_repos and len(sorted_repos) > 1:
        top2_sum = sorted_repos[0][1] + sorted_repos[1][1]
        if top2_sum / user_minutes * 100 > 70 if user_minutes else False:
            recs.append(
                f"Top 2 repos consume {top2_sum / user_minutes * 100:.0f}% of Actions — consider self-hosted runners to save."
            )
    if premium_by_model:
        models = list(premium_by_model.keys())
        if len(models) > 2:
            recs.append(
                f"Using {len(models)} Copilot models — consolidate to reduce cost complexity."
            )
    if lfs_summary and lfs_summary["total_gross"] > 0:
        recs.append("Review Git LFS usage — large binaries add up quickly at ~$1/GB.")
    if sorted_by_storage:
        top_st = sorted_by_storage[0]
        artifacts = top_st.get("items", [])
        release_assets = [a for a in artifacts if a["type"] == "Release Asset"]
        if release_assets:
            total_release_size = sum(a["storage"] for a in release_assets)
            if total_release_size > 100:
                recs.append(
                    f"Release assets in {top_st['name']} use {fmt_price(total_release_size)} — consider using GitHub Pages or external storage for large binaries."
                )
    if not recs:
        recs.append("Usage is well within free tiers — no immediate action needed.")
        recs.append("Consider enabling cost alerts in GitHub billing settings.")
    for i, rec in enumerate(recs, 1):
        print(f"\n    {i}. {rec}")
    print()


# ── Main ────────────────────────────────────────────────────────────────


def main():
    token = resolve_token()
    if not token:
        print("Error: No GitHub token found.")
        print("  Usage: ./github-usage <token>")
        print("  Or set GITHUB_TOKEN env var.")
        print("  Or run: gh auth login")
        sys.exit(1)

    try:
        api = GitHubAPI(token)

        # Check for 'user' scope required for billing endpoints
        if not check_user_scope(api):
            print("Error: Your GitHub token is missing the 'user' scope.")
            print()
            print("  The billing endpoints require the 'user' scope.")
            print("  Fix: run 'gh auth refresh -h github.com -s user'")
            print()
            print("  Current token scopes:", end=" ")
            import http.client

            conn = http.client.HTTPSConnection("api.github.com")
            conn.request("GET", "/user", headers={**api.headers, "Authorization": f"token {token}"})
            resp = conn.getresponse()
            scopes = resp.getheader("X-OAuth-Scopes", "none")
            print(scopes if scopes else "none")
            resp.read()
            sys.exit(1)

        # Account & rate limits
        print_header()
        username, user_type = show_account_info(api)
        show_rate_limits(api)

        # Actions
        user_minutes, user_storage_gb, actions_sku = get_user_actions_billing(api, username)
        actions_gross_total = sum(i.get("grossAmount", 0) for i in (actions_sku or {}).values())
        actions_discount_total = sum(
            i.get("discountAmount", 0) for i in (actions_sku or {}).values()
        )
        actions_net_total = sum(i.get("netAmount", 0) for i in (actions_sku or {}).values())
        if user_minutes is not None:
            show_actions_summary(api, username, user_minutes, user_storage_gb, actions_sku)

        # Repos
        repos = api.get_all_pages("/user/repos", {"type": "all"})
        repo_data = show_actions_per_repo(api, repos)
        show_actions_top_consumers(repo_data)
        show_actions_os_breakdown(api, repos)

        # Copilot
        show_copilot_summary(api, username)

        # Git LFS
        show_gitlfs_summary(api, username)

        # Cost estimate
        show_monthly_costs(repo_data, username, api)

        # Full billing history
        show_full_billing_history(api, username)

        # Limits
        show_limits_summary(username, user_minutes or 0, user_storage_gb or 0)

        # Base costs (v3 addition — standalone section)
        copilot_summary = get_billing_summary(api, username, "Copilot")
        lfs_summary = get_billing_summary(api, username, "git_lfs")
        if repos:
            show_base_costs(api, username, actions_sku, copilot_summary, lfs_summary)

        # Final summary (v3 addition)
        storage_analysis = get_storage_analysis(api, repos) if repos else {"repos": []}
        show_final_summary(
            username,
            user_minutes,
            user_storage_gb,
            actions_gross_total,
            actions_discount_total,
            actions_net_total,
            repo_data,
            copilot_summary,
            lfs_summary,
            storage_analysis,
            api,
        )

        # What else is available
        show_what_else(api, username)

        print("=" * 70)
        print("  End of Report v3")
        print("=" * 70)

    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
