"""Single-fetch legacy report dict for terminal display and file export.

Builds a superset of :func:`report_data.build_report_data` with legacy-only keys
(``account``, ``rate_limits``, ``repo_actions``, ``actions_os_breakdown``,
``billing_history``, ``storage_analysis``). Derived keys ``repo_consumers``,
``artifact_storage``, and ``release_assets`` are computed from primary fetches
without additional API calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .billing import get_billing_summary, get_premium_request_usage
from .repo_consumers import build_consumer_rankings
from .report_account import fetch_account_info, fetch_rate_limits
from .report_actions import fetch_actions_os_breakdown, fetch_repo_actions_table
from .report_data import (
    GitHubAPIClient,
    _empty_cost,
    _limited_repos,
    _rate_limit,
    get_actions_usage,
    get_copilot_usage,
    get_gitlfs_usage,
    get_key_insights,
    get_monthly_costs,
    get_warning_state,
)
from .report_products import fetch_billing_history
from .report_storage import build_storage_summary
from .report_workflow_minutes import workflow_breakdown_for_top_private
from .storage import get_storage_analysis
from .usage_split import REPORT_SOURCES, attach_actions_visibility_split
from .visibility import filter_repos_by_visibility, repo_visibility

LEGACY_DEFAULT_MAX_REPOS = 100
OS_BREAKDOWN_LIMIT = 10
CONSUMER_TOP_LIMIT = 5


def derive_repo_consumers(
    repo_actions: list[dict],
    errors: dict[str, str],
    *,
    limit: int = CONSUMER_TOP_LIMIT,
    max_repos: int,
    truncated: bool,
    scanned_repo_count: int,
) -> dict:
    """Build ``repo_consumers`` from a full ``repo_actions`` table (no API)."""
    rows = [
        {
            "repo": row["repo"],
            "minutes": float(row["minutes"]),
            "gross": float(row["gross"]),
            "storage_avg_mb": float(row["avg_mb"]),
            "visibility": repo_visibility(row),
        }
        for row in repo_actions
    ]
    rankings = build_consumer_rankings(rows, limit=limit)
    return {
        "scanned_repo_count": scanned_repo_count,
        "max_repos": max_repos,
        "truncated": truncated,
        **rankings,
        "errors": dict(errors),
    }


def _bytes_from_storage_items(items: list[dict], item_type: str) -> int:
    """Sum item storage (GB floats from storage analysis) into integer bytes."""
    return int(
        sum(
            float(item.get("storage", 0.0)) * (1024**3)
            for item in items
            if item.get("type") == item_type
        )
    )


def derive_artifact_storage(
    storage_analysis: dict,
    *,
    max_repos: int,
    truncated: bool,
    scanned_repo_count: int,
) -> dict:
    """Build ``artifact_storage`` export shape from ``storage_analysis`` (no API)."""
    rows = []
    for repo in storage_analysis.get("repos", []):
        artifact_bytes = _bytes_from_storage_items(repo.get("items", []), "Artifact")
        if artifact_bytes:
            rows.append(
                {
                    "repo": repo["name"],
                    "artifact_bytes": artifact_bytes,
                    "visibility": repo_visibility(repo),
                }
            )
    return {
        "scanned_repo_count": scanned_repo_count,
        "max_repos": max_repos,
        "truncated": truncated,
        "top_repos": sorted(rows, key=lambda row: row["artifact_bytes"], reverse=True)[:5],
    }


def derive_release_assets(
    storage_analysis: dict,
    *,
    max_repos: int,
    truncated: bool,
    scanned_repo_count: int,
) -> dict:
    """Build ``release_assets`` export shape from ``storage_analysis`` (no API)."""
    rows = []
    for repo in storage_analysis.get("repos", []):
        release_bytes = _bytes_from_storage_items(repo.get("items", []), "Release Asset")
        if release_bytes:
            rows.append(
                {
                    "repo": repo["name"],
                    "release_asset_bytes": release_bytes,
                    "visibility": repo_visibility(repo),
                }
            )
    return {
        "scanned_repo_count": scanned_repo_count,
        "max_repos": max_repos,
        "truncated": truncated,
        "top_repos": sorted(rows, key=lambda row: row["release_asset_bytes"], reverse=True)[:5],
    }


def estimate_legacy_api_request_count(
    repo_count: int,
    *,
    max_repos: int,
    include_release_assets: bool,
    core_limit: int | None,
    core_remaining: int | None,
) -> dict:
    """Estimate REST calls for the legacy single-fetch path (no double-counting)."""
    repos_considered = min(repo_count, max_repos)
    # Account-level: /user, /rate_limit, billing summaries, premium, full history
    account_level = 10
    # Per repo: Actions billing + artifacts pages + releases pages (storage_analysis once)
    per_repo = 3
    os_breakdown = min(OS_BREAKDOWN_LIMIT, repos_considered)
    estimated = account_level + repos_considered * per_repo + os_breakdown + 10
    percent = None
    if core_remaining:
        percent = round(estimated / core_remaining * 100, 1)
    notes = []
    if repo_count > max_repos:
        notes.append(f"Repository list truncated to {max_repos} of {repo_count} repositories.")
    if estimated:
        notes.append(f"Local full report may use about {estimated} REST API requests.")
    if include_release_assets:
        notes.append("Release asset totals are derived from storage analysis (no extra fetch).")
    return {
        "core_limit": core_limit,
        "core_remaining": core_remaining,
        "estimated_incremental_requests": estimated,
        "estimated_percent_of_remaining": percent,
        "repos_considered": repos_considered,
        "notes": notes,
    }


def repo_actions_to_tuples(repo_actions: list[dict]) -> list[tuple]:
    """Convert ``repo_actions`` rows to the tuple shape used by final summary renderers."""
    return [
        (
            row["repo"],
            row["minutes"],
            row["storage_gb_hours"],
            row["avg_mb"],
            row["gross"],
            row.get("sku", {}),
        )
        for row in repo_actions
    ]


def premium_from_copilot(copilot: dict | None) -> dict | None:
    """Adapt ``copilot.by_model`` to the premium-by-model shape for final summary."""
    if not copilot:
        return None
    by_model = copilot.get("by_model") or {}
    if not by_model:
        return None
    return {
        model: {
            "total_requests": data.get("requests", 0),
            "total_gross": data.get("gross", 0),
            "total_discount": data.get("discount", 0),
            "total_net": data.get("net", 0),
            "items": [],
        }
        for model, data in by_model.items()
    }


def build_legacy_report_data(
    api: GitHubAPIClient,
    username: str,
    *,
    max_repos: int = LEGACY_DEFAULT_MAX_REPOS,
    warn_over: list[str] | str | None = None,
    include_release_assets: bool = False,
    only_public: bool = False,
    only_private: bool = False,
    account: dict | None = None,
    rate_limits: dict | None = None,
) -> dict[str, Any]:
    """Fetch and assemble the legacy report superset dict in a single pass."""
    errors: dict[str, str] = {}
    if account is None:
        account = fetch_account_info(api)
    if rate_limits is None:
        rate_limits = fetch_rate_limits(api)
    repos, truncated = _limited_repos(api, max_repos)
    repos = filter_repos_by_visibility(repos, only_public=only_public, only_private=only_private)
    scanned_repo_count = len(repos)
    repo_count = scanned_repo_count + (1 if truncated else 0)
    core_limit, core_remaining = _rate_limit(api)
    api_estimate = estimate_legacy_api_request_count(
        repo_count,
        max_repos=max_repos,
        include_release_assets=include_release_assets,
        core_limit=core_limit,
        core_remaining=core_remaining,
    )
    if (
        core_remaining is not None
        and core_remaining < api_estimate["estimated_incremental_requests"]
    ):
        raise RuntimeError("GitHub REST API quota is too low for selected repo-level sections.")

    repo_actions, repo_action_errors = fetch_repo_actions_table(api, repos)
    storage_analysis = get_storage_analysis(api, repos)
    actions_os_breakdown = fetch_actions_os_breakdown(api, repos, limit=OS_BREAKDOWN_LIMIT)
    billing_history = fetch_billing_history(api, username)

    runs_cache: dict = {}
    repo_consumers = derive_repo_consumers(
        repo_actions,
        repo_action_errors,
        max_repos=max_repos,
        truncated=truncated,
        scanned_repo_count=scanned_repo_count,
    )
    workflow_breakdown = workflow_breakdown_for_top_private(
        api, repo_consumers, runs_cache=runs_cache
    )
    artifact_storage = derive_artifact_storage(
        storage_analysis,
        max_repos=max_repos,
        truncated=truncated,
        scanned_repo_count=scanned_repo_count,
    )
    release_assets = (
        derive_release_assets(
            storage_analysis,
            max_repos=max_repos,
            truncated=truncated,
            scanned_repo_count=scanned_repo_count,
        )
        if include_release_assets
        else None
    )

    report: dict[str, Any] = {
        "username": username,
        "period": "current_month",
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "warnings": [],
        "errors": errors,
        "account": account,
        "rate_limits": rate_limits,
        "repo_actions": repo_actions,
        "actions_os_breakdown": actions_os_breakdown,
        "billing_history": billing_history,
        "storage_analysis": storage_analysis,
        "actions": None,
        "copilot": None,
        "git_lfs": None,
        "monthly_costs": None,
        "repo_consumers": repo_consumers,
        "workflow_breakdown": workflow_breakdown,
        "artifact_storage": artifact_storage,
        "release_assets": release_assets,
        "api_estimate": api_estimate,
        "insights": [],
        "copilot_premium": None,
        "copilot_billing": None,
        "lfs_billing": None,
    }

    for key, getter in [
        ("actions", lambda: get_actions_usage(api, username)),
        ("copilot", lambda: get_copilot_usage(api, username)),
        ("git_lfs", lambda: get_gitlfs_usage(api, username)),
    ]:
        try:
            report[key] = getter()
        except RuntimeError as exc:
            errors[key] = str(exc)

    attach_actions_visibility_split(
        report, repo_actions, only_public=only_public, only_private=only_private
    )
    storage_summary = build_storage_summary(report.get("actions"))
    if storage_summary is not None:
        report["storage_summary"] = storage_summary
    report["sources"] = dict(REPORT_SOURCES)

    try:
        report["monthly_costs"] = get_monthly_costs(api, username)
    except RuntimeError as exc:
        errors["monthly_costs"] = str(exc)
        report["monthly_costs"] = {
            "actions": _empty_cost(),
            "copilot": _empty_cost(),
            "git_lfs": _empty_cost(),
            "total": _empty_cost(),
        }

    try:
        report["copilot_premium"] = get_premium_request_usage(api, username)
    except RuntimeError as exc:
        errors["copilot_premium"] = str(exc)

    try:
        report["copilot_billing"] = get_billing_summary(api, username, "Copilot")
    except RuntimeError as exc:
        errors["copilot_billing"] = str(exc)

    try:
        report["lfs_billing"] = get_billing_summary(api, username, "git_lfs")
    except RuntimeError as exc:
        errors["lfs_billing"] = str(exc)

    report["insights"] = get_key_insights(report)
    report["warnings"] = get_warning_state(report, warn_over)
    return report
