"""Shared formatters for measured-vs-estimated GitHub REST API usage.

Both the email renderers and the file exports derive their API-usage rows
from :func:`api_usage_lines`, matching the existing ``email_actions_table_rows``
convention (``- Label: value`` bullets feed a shared rows adapter).
"""

from __future__ import annotations

RATE_LIMITS_URL = "https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api"

# Documented primary rate limit for authenticated REST requests, used when the
# report has no live ``core_limit`` from ``/rate_limit``.
_DOCUMENTED_CORE_LIMIT = 5000

# Estimate scopes recorded in ``api_estimate["estimate_scope"]``. Builders
# import these instead of re-typing the strings so a typo cannot silently
# degrade to the neutral label.
SCOPE_REPO_SECTIONS = "repo-sections-only"
SCOPE_FULL_REPORT = "full-report-including-account-level"

_SCOPE_LABELS = {
    SCOPE_FULL_REPORT: "All requests in estimate scope",
    SCOPE_REPO_SECTIONS: "Repo requests in estimate scope",
}


def _scope_label(estimate: dict) -> str:
    """Return the scope-qualified label for the measured-requests line."""
    return _SCOPE_LABELS.get(
        str(estimate.get("estimate_scope") or ""),
        "Requests in estimate scope",
    )


def _fmt_count(value) -> str:
    """Format a request count, tolerating None/missing values."""
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def _measured(estimate: dict) -> bool:
    """True when the estimate carries a measurement (vs estimate-only)."""
    return "actual_requests" in estimate or "total_requests" in estimate


def api_usage_lines(estimate: dict | None) -> list[str]:
    """Bullet lines comparing measured vs estimated REST API usage.

    Each line is shaped ``- Label: value`` so :func:`api_usage_rows` can
    derive label/value pairs from it. ``actual_requests`` always covers the
    estimate's matching window (see ``estimate_scope``); ``total_requests``
    is the raw client total and is never compared against the estimate.
    Returns no lines when the estimate carries no measurement, so
    pre-measurement reports render nothing rather than zeros.
    """
    if not estimate or not _measured(estimate):
        return []
    actual = estimate.get("actual_requests") or 0
    estimated = estimate.get("estimated_incremental_requests") or 0
    total = estimate.get("total_requests") or 0
    if estimate.get("from_cache"):
        total_label = "Total requests (original fetch)"
    else:
        total_label = "Total requests this fetch"
    lines = [
        f"- {_scope_label(estimate)}: {_fmt_count(actual)} (estimated {_fmt_count(estimated)})",
        f"- {total_label}: {_fmt_count(total)}",
    ]
    core_limit = estimate.get("core_limit")
    core_remaining = estimate.get("core_remaining")
    if core_limit and core_remaining is not None:
        lines.append(
            f"- Core quota remaining before: {_fmt_count(core_remaining)} / "
            f"{_fmt_count(core_limit)}"
        )
    limit = core_limit or _DOCUMENTED_CORE_LIMIT
    lines.append(
        f"- Core rate limit: {_fmt_count(limit)} requests/hour (authenticated) - {RATE_LIMITS_URL}"
    )
    by_resource = estimate.get("actual_requests_by_resource") or {}
    nonzero = {name: qty for name, qty in sorted(by_resource.items()) if (qty or 0) != 0}
    if nonzero:
        breakdown = ", ".join(f"{name} {_fmt_count(qty)}" for name, qty in nonzero.items())
        lines.append(f"- By resource (estimate scope): {breakdown}")
    if estimate.get("from_cache"):
        lines.append(
            "- Source: cached report (0 new API requests; "
            f"{_fmt_count(total)} total during the original fetch)"
        )
    else:
        lines.append("- Source: live fetch")
    return lines


def api_usage_rows(estimate: dict | None) -> list[tuple[str, str]]:
    """Derive ``(label, value)`` pairs from :func:`api_usage_lines`."""
    rows: list[tuple[str, str]] = []
    for line in api_usage_lines(estimate):
        label, _, value = line.partition(": ")
        rows.append((label.removeprefix("- "), value))
    return rows
