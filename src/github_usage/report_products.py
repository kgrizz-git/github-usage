"""Product billing sections for the legacy report."""

from __future__ import annotations

from collections import defaultdict

from .billing import get_billing_summary, get_full_billing, get_premium_request_usage
from .report_helpers import fmt_price, gb_hours_to_avg_mb
from .terminal import print_section


def show_copilot_summary(api, username):
    """Print Copilot billing summary and per-model premium request breakdown."""
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
    """Print Git LFS billing summary and per-SKU line items."""
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


def _print_actions_compute_costs(actions_sku) -> None:
    """Per-unit Actions compute (minutes) pricing rows."""
    print("\n  Actions Compute:")
    found = False
    for sku, item in (actions_sku or {}).items():
        if str(sku).startswith("_"):
            continue
        if item.get("unitType", "") == "minutes":
            price = item.get("pricePerUnit", 0)
            qty = item.get("grossQuantity", 0)
            net = item.get("netAmount", 0)
            print(f"    {sku:<40} {fmt_price(price)}/min  × {qty:.1f} min  = {fmt_price(net)}")
            found = True
    if not found:
        print("    No compute minutes billed.")
    print("    Standard tier: ~$0.008/min (Linux), ~$0.016/min (Windows), ~$0.016/min (macOS)")
    print("    Free tier: 2,000 min/month for personal repos")
    print()


def _print_actions_storage_costs(actions_sku) -> None:
    """Per-unit Actions storage (GB-hours) pricing rows."""
    print("  Actions Storage:")
    found = False
    for sku, item in (actions_sku or {}).items():
        if str(sku).startswith("_"):
            continue
        if item.get("unitType", "") == "gigabyte-hours":
            price = item.get("pricePerUnit", 0)
            qty = item.get("grossQuantity", 0)
            net = item.get("netAmount", 0)
            avg_mb = gb_hours_to_avg_mb(qty)
            print(
                f"    {sku:<40} {fmt_price(price)}/GB-hr  × {qty:.2f} GB-hrs "
                f"({avg_mb:.0f} MB avg)  = {fmt_price(net)}"
            )
            found = True
    if not found:
        print("    No storage billed.")
    print("    Standard: ~$0.01/GB-month")
    print("    Free tier: 500 MB for personal repos")
    print()


def _print_copilot_base_costs(items) -> None:
    """Per-unit Copilot premium-request pricing rows from a billing items map."""
    print("  Copilot Premium Requests:")
    found = False
    if items:
        all_prices = set()
        for sku, item in items.items():
            price = item.get("pricePerUnit", 0)
            qty = item.get("grossQuantity", 0)
            if price > 0:
                # codeql[py/clear-text-logging-sensitive-data]
                print(
                    f"    {sku:<40} {fmt_price(price)}/req  × {qty:.0f} reqs  "
                    f"= {fmt_price(item.get('netAmount', 0))}"
                )
                found = True
                all_prices.add(price)
        if all_prices:
            print(f"    Base rate: {max(all_prices):.4f}/req (highest observed)")
    if not found:
        print("    No premium requests billed.")
    print("    Copilot Pro: ~$0.04-0.08/request for premium features")
    print()


def _print_lfs_base_costs(items) -> None:
    """Per-unit Git LFS storage pricing rows from a billing items map."""
    print("  Git LFS:")
    found = False
    if items:
        for sku, item in items.items():
            price = item.get("pricePerUnit", 0)
            qty = item.get("grossQuantity", 0)
            if price > 0:
                # codeql[py/clear-text-logging-sensitive-data]
                print(
                    f"    {sku:<40} {fmt_price(price)}/GB  × {qty:.2f} GB  "
                    f"= {fmt_price(item.get('netAmount', 0))}"
                )
                found = True
    if not found:
        print("    No LFS storage billed.")
    print("    Standard: ~$1/GB-month after 1 GB free")
    print()


def show_base_costs(api, username, actions_sku, copilot_summary, lfs_summary):
    """Show per-unit base costs for all products."""
    print_section("Base Costs (Per-Unit Pricing)")
    _print_actions_compute_costs(actions_sku)
    _print_actions_storage_costs(actions_sku)
    _print_copilot_base_costs(copilot_summary.get("items") if copilot_summary else None)
    _print_lfs_base_costs(lfs_summary.get("items") if lfs_summary else None)


def fetch_billing_history(api, username: str) -> list:
    """Return raw billing history items (no printing)."""
    full = get_full_billing(api, username)
    return full if full else []


def render_copilot_summary(copilot: dict | None, premium_by_model: dict | None) -> None:
    """Print Copilot usage from pre-fetched dicts."""
    print_section("GitHub Copilot Usage")
    if not copilot:
        print("  No Copilot usage data found.")
        print()
        return
    print("  Summary:")
    total_requests = copilot.get("total_requests", 0)
    print(
        f"    {'TOTAL':<35} {total_requests:>10.2f} requests | "
        f"gross: {fmt_price(copilot.get('total_gross', 0))} | "
        f"discount: {fmt_price(copilot.get('total_discount', 0))} | "
        f"net: {fmt_price(copilot.get('total_net', 0))}"
    )
    print()
    print("  By Model:")
    if not premium_by_model:
        by_model = copilot.get("by_model") or {}
        if not by_model:
            print("    No model-level data available.")
            print()
            return
        for model, data in sorted(
            by_model.items(), key=lambda x: x[1].get("requests", 0), reverse=True
        ):
            print(f"    {model}:")
            print(f"      Total requests: {data.get('requests', 0):.2f}")
            print(
                f"      Gross: {fmt_price(data.get('gross', 0))} | "
                f"Discount: {fmt_price(data.get('discount', 0))} | "
                f"Net: {fmt_price(data.get('net', 0))}"
            )
            print()
        return
    for model, data in sorted(
        premium_by_model.items(), key=lambda x: x[1]["total_requests"], reverse=True
    ):
        print(f"    {model}:")
        print(f"      Total requests: {data['total_requests']:.2f}")
        print(
            f"      Gross: {fmt_price(data['total_gross'])} | "
            f"Discount: {fmt_price(data['total_discount'])} | "
            f"Net: {fmt_price(data['total_net'])}"
        )
        for item in data.get("items", []):
            sku = item.get("sku", "unknown")
            qty = item.get("grossQuantity", 0)
            price = item.get("pricePerUnit", 0)
            print(f"        {sku}: {qty:.2f} @ {fmt_price(price)}/ea")
        print()


def render_gitlfs_summary(git_lfs: dict | None) -> None:
    """Print Git LFS usage from a pre-fetched ``git_lfs`` section dict."""
    print_section("Git LFS Usage")
    if not git_lfs or not git_lfs.get("items"):
        print("  No Git LFS usage found.")
        print()
        return
    items = git_lfs["items"]
    print(f"  {'SKU':<30} {'QTY':>10} {'UNIT':<18} {'GROSS':>10} {'DISCOUNT':>10} {'NET':>10}")
    print(f"  {'-' * 30} {'-' * 10} {'-' * 18} {'-' * 10} {'-' * 10} {'-' * 10}")
    for sku, item in items.items():
        qty = item.get("grossQuantity", 0)
        unit = item.get("unitType", "")
        gross = item.get("grossAmount", 0)
        discount = item.get("discountAmount", 0)
        net = item.get("netAmount", 0)
        print(
            f"    {sku:<30} {qty:>10.4f} {unit:<18} {fmt_price(gross):>10} "
            f"{fmt_price(discount):>10} {fmt_price(net):>10}"
        )
    print()


def render_full_billing_history(history: list | None) -> None:
    """Print aggregated billing history from pre-fetched items."""
    print_section("Full Billing History (All Products)")
    if not history:
        print("  No billing history available.")
        print()
        return
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
    for item in history:
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
        f"  {'PRODUCT/SKU':<40} {'ENRIES':>6} {'TOTAL QTY':>12} {'UNITS':<12} "
        f"{'GROSS':>10} {'DISCOUNT':>10} {'NET':>10}"
    )
    print(f"  {'-' * 40} {'-' * 6} {'-' * 12} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 10}")
    for key in sorted(agg.keys()):
        entry = agg[key]
        units = ", ".join(entry["units"])
        repos = ", ".join(sorted(entry["repos"]))[:30]
        months = ", ".join(sorted(entry["months"]))
        qty_str = f"{entry['total_qty']:.2f}"
        print(
            f"  {key:<40} {entry['entries']:>6} {qty_str:>12} {units:<12} "
            f"{fmt_price(entry['total_gross']):>10} {fmt_price(entry['total_discount']):>10} "
            f"{fmt_price(entry['total_net']):>10}"
        )
        if repos:
            print(f"    repos: {repos}")
        if months:
            print(f"    months: {months}")
    total_gross = sum(entry["total_gross"] for entry in agg.values())
    total_discount = sum(entry["total_discount"] for entry in agg.values())
    total_net = sum(entry["total_net"] for entry in agg.values())
    print(f"  {'-' * 40} {'-' * 6} {'-' * 12} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 10}")
    print(
        f"  {'TOTAL':<40} {'':>6} {'':>12} {'':>12} {fmt_price(total_gross):>10} "
        f"{fmt_price(total_discount):>10} {fmt_price(total_net):>10}"
    )
    print()


def render_monthly_costs(monthly_costs: dict | None) -> None:
    """Print monthly cost estimate from a pre-fetched ``monthly_costs`` dict."""
    print_section("Current Month Cost Estimate")
    if not monthly_costs:
        print("  (Monthly cost data unavailable.)")
        print()
        return
    actions = monthly_costs.get("actions") or {}
    copilot = monthly_costs.get("copilot") or {}
    git_lfs = monthly_costs.get("git_lfs") or {}
    total = monthly_costs.get("total") or {}
    print(f"  {'Category':<25} {'GROSS':>12} {'DISCOUNT':>12} {'NET':>12}")
    print(f"  {'-' * 25} {'-' * 12} {'-' * 12} {'-' * 12}")
    for label, row in [
        ("Actions", actions),
        ("Copilot", copilot),
        ("Git LFS", git_lfs),
    ]:
        print(
            f"  {label:<25} {fmt_price(row.get('gross', 0)):>12} "
            f"{fmt_price(row.get('discount', 0)):>12} {fmt_price(row.get('net', 0)):>12}"
        )
    print(f"  {'-' * 25} {'-' * 12} {'-' * 12} {'-' * 12}")
    print(
        f"  {'TOTAL':<25} {fmt_price(total.get('gross', 0)):>12} "
        f"{fmt_price(total.get('discount', 0)):>12} {fmt_price(total.get('net', 0)):>12}"
    )
    print()
    total_discount = total.get("discount", 0) or 0
    total_gross = total.get("gross", 0) or 0
    if total_discount > 0:
        savings_pct = (total_discount / total_gross * 100) if total_gross > 0 else 0
        print(
            f"  You're saving {fmt_price(total_discount)} ({savings_pct:.1f}% discount) this month!"
        )
        print()


def render_base_costs(
    actions: dict | None,
    copilot_billing: dict | None,
    lfs_billing: dict | None,
) -> None:
    """Print per-unit base costs from pre-fetched billing summaries."""
    actions_sku = (actions or {}).get("sku_breakdown") or {}
    print_section("Base Costs (Per-Unit Pricing)")
    _print_actions_compute_costs(actions_sku)
    _print_actions_storage_costs(actions_sku)
    _print_copilot_base_costs(copilot_billing.get("items") if copilot_billing else None)
    _print_lfs_base_costs(lfs_billing.get("items") if lfs_billing else None)
