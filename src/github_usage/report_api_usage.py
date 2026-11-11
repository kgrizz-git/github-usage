"""Shared tracking helpers and formatters for measured-vs-estimated GitHub REST API usage.

Both the email renderers and the file exports derive their API-usage rows
from :func:`api_usage_lines`, matching the existing ``email_actions_table_rows``
convention (``- Label: value`` bullets feed a shared rows adapter). The merge
helpers below combine per-getter and window snapshots into report-ready
``actual`` / ``by_resource`` deltas.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

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


def _stats_total(stats: dict) -> int:
    """Return the total request count of a stats snapshot (0 when missing)."""
    return int(stats.get("actual_requests", 0) or 0)


def _subtract_stats(current: dict, baseline: dict) -> tuple[int, dict[str, int]]:
    """Return ``(actual, by_resource)`` for ``current`` minus ``baseline``.

    Missing keys default to 0 so empty getattr-fallback snapshots work.
    Counters only increase, so per-bucket deltas are non-negative in practice.
    """
    cur_by = current.get("actual_requests_by_resource") or {}
    base_by = baseline.get("actual_requests_by_resource") or {}
    by_resource = {
        res: int(cur_by.get(res, 0) or 0) - int(base_by.get(res, 0) or 0)
        for res in sorted(set(cur_by) | set(base_by))
    }
    return _stats_total(current) - _stats_total(baseline), by_resource


def _sum_repo_deltas(deltas: list[tuple[dict, dict]]) -> tuple[int, dict[str, int]]:
    """Sum ``(before, after)`` stats snapshots into ``(actual, by_resource)``."""
    actual = 0
    by_resource: dict[str, int] = {}
    for before, after in deltas:
        delta_actual, delta_by = _subtract_stats(after, before)
        actual += delta_actual
        for res, qty in delta_by.items():
            by_resource[res] = by_resource.get(res, 0) + qty
    return actual, dict(sorted(by_resource.items()))


def _finalize_api_estimate(
    estimate: dict,
    *,
    actual: int,
    by_resource: dict,
    total: int,
    scope: str | None,
) -> dict:
    """Return ``estimate`` augmented with measured usage fields.

    ``scope`` may be None for best-effort windows; renderers then use the
    neutral scope label.
    """
    merged = dict(estimate)
    merged["actual_requests"] = actual
    merged["total_requests"] = total
    merged["actual_requests_by_resource"] = dict(by_resource)
    merged["estimate_variance"] = actual - int(
        estimate.get("estimated_incremental_requests", 0) or 0
    )
    if scope is not None:
        merged["estimate_scope"] = scope
    merged["from_cache"] = False
    return merged


def _merge_legacy_api_estimate(
    estimate: dict,
    *,
    current: dict,
    baseline: dict,
    listing_before: dict,
    listing_after: dict,
    include_scope: bool,
) -> dict:
    """Merge measured legacy usage into ``estimate`` and return the result.

    Subtracts the repository-listing page fetches from the window delta so
    listing pagination changes the total without moving the variance.
    Omits ``estimate_scope`` when ``include_scope`` is false, so renderers
    use the neutral label for best-effort windows.
    """
    window_actual, window_by = _subtract_stats(current, baseline)
    listing_actual, listing_by = _subtract_stats(listing_after, listing_before)
    by_resource = {
        res: window_by.get(res, 0) - listing_by.get(res, 0)
        for res in sorted(set(window_by) | set(listing_by))
    }
    return _finalize_api_estimate(
        estimate,
        actual=window_actual - listing_actual,
        by_resource=by_resource,
        total=_stats_total(current),
        scope=SCOPE_FULL_REPORT if include_scope else None,
    )


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
        total_label = "Total requests (original fetch, retries excluded)"
    else:
        total_label = "Total requests this fetch (retries excluded)"
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


def _api_request_stats(api) -> dict[str, object]:
    """Return the client's request stats, tolerating fakes without counting.

    Clients without ``get_request_stats`` fall back to their
    ``request_count`` (if any) bucketed under ``"other"`` so the totals
    still reconcile.
    """
    stats = getattr(api, "get_request_stats", None)
    if callable(stats):
        result = stats()
        if isinstance(result, dict):
            return result
    count = int(getattr(api, "request_count", 0) or 0)
    return {
        "actual_requests": count,
        "actual_requests_by_resource": {"other": count} if count else {},
    }


_T = TypeVar("_T")


def _track_repo_calls(api, func: Callable[[], _T], deltas: list[tuple[dict, dict]]) -> _T:
    """Run ``func()``, appending its (before, after) stats to ``deltas``.

    The call's return value is passed through. Exceptions propagate after
    the ``after`` snapshot is recorded, so partial failures still count the
    calls they made.
    """
    before = _api_request_stats(api)
    try:
        return func()
    finally:
        deltas.append((before, _api_request_stats(api)))
