"""Legacy-report Sources footer (public documentation URLs only).

Kept separate from report data so clear-text-logging scanners do not treat
these prints as leakage of private billing payloads.
"""

from __future__ import annotations

_ACTIONS_BILLING_DOC = (
    "https://docs.github.com/en/billing/managing-billing-for-github-actions/"
    "about-billing-for-github-actions"
)
_RUNNER_PRICING_DOC = "https://docs.github.com/en/billing/reference/actions-runner-pricing"
_RELEASES_STORAGE_DOC = (
    "https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases"
)


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
