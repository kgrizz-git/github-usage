"""Terminal rendering for the legacy report from a pre-fetched data dict."""

from __future__ import annotations

from .report_account import render_account_info, render_rate_limits, render_what_else
from .report_actions import (
    render_actions_os_breakdown,
    render_actions_summary,
    render_actions_top_consumers,
    render_limits_summary,
    render_repo_actions_table,
)
from .report_forecast import render_forecast
from .report_products import (
    render_base_costs,
    render_copilot_summary,
    render_full_billing_history,
    render_gitlfs_summary,
    render_monthly_costs,
)
from .report_sources import print_report_sources_footer
from .report_storage import render_artifact_storage_section
from .report_summary import render_final_summary_from_data


def _print_section_error(label: str, errors: dict, key: str) -> None:
    message = errors.get(key)
    if message:
        print(f"  ({label} unavailable: {message})")


def render_legacy_report(
    data: dict,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> None:
    """Print the full legacy v3 report from a :func:`build_legacy_report_data` dict."""
    errors = data.get("errors") or {}

    render_account_info(data.get("account") or {})
    render_rate_limits(data.get("rate_limits") or {})

    if data.get("actions") is None and errors.get("actions"):
        _print_section_error("Actions", errors, "actions")
    else:
        render_actions_summary(data.get("actions"))

    render_artifact_storage_section(
        data.get("storage_analysis"),
        data.get("actions"),
        data.get("repo_actions") or [],
        reference_date=reference_date,
    )

    render_repo_actions_table(data.get("repo_actions") or [])
    render_actions_top_consumers(data.get("repo_actions") or [])
    render_actions_os_breakdown(data.get("actions_os_breakdown"))

    if data.get("copilot") is None and errors.get("copilot"):
        _print_section_error("Copilot", errors, "copilot")
    else:
        render_copilot_summary(data.get("copilot"), data.get("copilot_premium"))

    if data.get("git_lfs") is None and errors.get("git_lfs"):
        _print_section_error("Git LFS", errors, "git_lfs")
    else:
        render_gitlfs_summary(data.get("git_lfs"))

    render_monthly_costs(data.get("monthly_costs"))
    render_full_billing_history(data.get("billing_history"))
    render_limits_summary(data.get("actions"))

    if data.get("repo_actions"):
        render_base_costs(data.get("actions"), data.get("copilot_billing"), data.get("lfs_billing"))

    render_final_summary_from_data(data)
    if include_forecast:
        render_forecast(
            data,
            premium_requests_limit=premium_requests_limit,
            reference_date=reference_date,
        )
    render_what_else(str(data.get("username", "?")))

    if data.get("sources"):
        print_report_sources_footer()

    print("=" * 70)
    print("  End of Report v3")
    print("=" * 70)
