#!/usr/bin/env python3
"""Compatibility shim for the original legacy report module."""

from __future__ import annotations

from .api import GitHubAPI
from .auth import check_user_scope, resolve_token
from .billing import (
    get_actions_from_runs,
    get_actions_per_repo,
    get_billing_summary,
    get_full_billing,
    get_premium_request_usage,
    get_user_actions_billing,
)
from .legacy_report import main
from .report_account import show_account_info, show_rate_limits, show_what_else
from .report_actions import (
    show_actions_os_breakdown,
    show_actions_per_repo,
    show_actions_summary,
    show_actions_top_consumers,
    show_limits_summary,
)
from .report_helpers import fmt_price, gb_hours_to_avg_mb, hours_in_month
from .report_products import (
    show_base_costs,
    show_copilot_summary,
    show_full_billing_history,
    show_gitlfs_summary,
    show_monthly_costs,
)
from .report_summary import show_final_summary
from .storage import get_storage_analysis
from .terminal import print_header, print_section, print_sep

__all__ = [
    "GitHubAPI",
    "check_user_scope",
    "fmt_price",
    "gb_hours_to_avg_mb",
    "get_actions_from_runs",
    "get_actions_per_repo",
    "get_billing_summary",
    "get_full_billing",
    "get_premium_request_usage",
    "get_storage_analysis",
    "get_user_actions_billing",
    "hours_in_current_month",
    "main",
    "print_header",
    "print_section",
    "print_sep",
    "resolve_token",
    "show_account_info",
    "show_actions_os_breakdown",
    "show_actions_per_repo",
    "show_actions_summary",
    "show_actions_top_consumers",
    "show_base_costs",
    "show_copilot_summary",
    "show_full_billing_history",
    "show_gitlfs_summary",
    "show_limits_summary",
    "show_monthly_costs",
    "show_rate_limits",
    "show_final_summary",
    "show_what_else",
]


def hours_in_current_month():
    """Return the total number of hours in the current calendar month."""
    return hours_in_month()
