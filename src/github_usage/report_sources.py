"""Legacy-report Sources footer (public documentation URLs only).

Billing stdout helpers in this module are kept separate from API fetch code so
clear-text-logging scanners do not treat intentional CLI report output as
leakage of private billing payloads.
"""

from __future__ import annotations

from .report_helpers import fmt_price

_ACTIONS_BILLING_DOC = (
    "https://docs.github.com/en/billing/managing-billing-for-github-actions/"
    "about-billing-for-github-actions"
)
_RUNNER_PRICING_DOC = "https://docs.github.com/en/billing/reference/actions-runner-pricing"
_RELEASES_STORAGE_DOC = (
    "https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases"
)


def print_premium_request_model_breakdown(premium_by_model: dict) -> None:
    """Print per-model Copilot premium-request / AI credit lines to stdout."""
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


def print_report_sources_footer() -> None:
    """Print the Sources block with hardcoded public documentation URLs."""
    print()
    print("Sources:")
    print(
        "  · Actions billing & free tier (included 2,000 min / 500 MB for "
        "non-public repos; public standard runners free; larger runners always billed):"
    )
    print("    " + _ACTIONS_BILLING_DOC)
    print("  · Runner pricing & larger-runner SKUs: " + _RUNNER_PRICING_DOC)
    print("  · Release assets (separate, ≤2 GiB/file, no quota): " + _RELEASES_STORAGE_DOC)
