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
