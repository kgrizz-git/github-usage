"""Collection and shaping for scheduled email report data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from .report_helpers import fmt_price, gb_hours_to_avg_mb
from .report_optional import (
    estimate_api_request_count,
    get_artifact_storage_details,
    get_release_asset_details,
    get_repo_consumers,
)


class GitHubAPIClient(Protocol):
    def request(
        self, method: str, path: str, params: dict[str, object] | None = None
    ) -> object: ...

    def get_all_pages(
        self, path: str, params: dict[str, object] | None = None
    ) -> list[dict[str, object]]: ...


def _empty_cost() -> dict[str, float]:
    return {"gross": 0.0, "discount": 0.0, "net": 0.0}


def _summary_cost(summary: dict | None) -> dict[str, float]:
    if not summary:
        return _empty_cost()
    return {
        "gross": float(summary.get("total_gross", 0.0)),
        "discount": float(summary.get("total_discount", 0.0)),
        "net": float(summary.get("total_net", 0.0)),
    }


def _billing_summary(api: GitHubAPIClient, username: str, product: str) -> dict | None:
    data = api.request(
        "GET", f"/users/{username}/settings/billing/usage/summary", {"product": product}
    )
    if not data:
        return None
    items = data.get("usageItems", []) if isinstance(data, dict) else []
    summary = {
        "raw": data,
        "items": {},
        "total_gross": 0.0,
        "total_discount": 0.0,
        "total_net": 0.0,
    }
    for item in items:
        sku = item.get("sku", item.get("product", "unknown"))
        summary["items"][sku] = item
        summary["total_gross"] += float(item.get("grossAmount", 0.0))
        summary["total_discount"] += float(item.get("discountAmount", 0.0))
        summary["total_net"] += float(item.get("netAmount", 0.0))
    return summary


def get_actions_usage(api: GitHubAPIClient, username: str) -> dict:
    """Return Actions compute minutes, storage, and per-SKU cost breakdown."""
    summary = _billing_summary(api, username, "Actions")
    total_minutes = 0.0
    storage_gb_hours = 0.0
    sku_breakdown = {}
    for sku, item in (summary or {}).get("items", {}).items():
        qty = float(item.get("grossQuantity", 0.0))
        if item.get("unitType") == "minutes":
            total_minutes += qty
        elif item.get("unitType") == "gigabyte-hours":
            storage_gb_hours += qty
        sku_breakdown[sku] = item
    storage_avg_mb = gb_hours_to_avg_mb(storage_gb_hours)
    return {
        "minutes": total_minutes,
        "minutes_limit": 2000,
        "minutes_percent": (total_minutes / 2000 * 100) if total_minutes else 0.0,
        "storage_gb_hours": storage_gb_hours,
        "storage_avg_mb": storage_avg_mb,
        "storage_limit_mb": 500,
        "storage_percent": (storage_avg_mb / 500 * 100) if storage_avg_mb else 0.0,
        "sku_breakdown": sku_breakdown,
    }


def get_copilot_usage(api: GitHubAPIClient, username: str) -> dict:
    """Return Copilot billing totals and per-model premium request breakdown."""
    summary = _billing_summary(api, username, "Copilot")
    premium = api.request(
        "GET",
        f"/users/{username}/settings/billing/premium_request/usage",
        {"product": "copilot"},
    )
    by_model = {}
    for item in (premium or {}).get("usageItems", []):
        model = item.get("model", "Unknown")
        entry = by_model.setdefault(
            model, {"requests": 0.0, "gross": 0.0, "discount": 0.0, "net": 0.0}
        )
        entry["requests"] += float(item.get("grossQuantity", 0.0))
        entry["gross"] += float(item.get("grossAmount", 0.0))
        entry["discount"] += float(item.get("discountAmount", 0.0))
        entry["net"] += float(item.get("netAmount", 0.0))
    cost = _summary_cost(summary)
    return {
        "total_requests": sum(model["requests"] for model in by_model.values()),
        "total_gross": cost["gross"],
        "total_discount": cost["discount"],
        "total_net": cost["net"],
        "by_model": by_model,
    }


def get_gitlfs_usage(api: GitHubAPIClient, username: str) -> dict:
    """Return Git LFS billing totals and raw line items."""
    summary = _billing_summary(api, username, "git_lfs")
    cost = _summary_cost(summary)
    return {
        **{f"total_{key}": value for key, value in cost.items()},
        "items": (summary or {}).get("items", {}),
    }


def get_monthly_costs(api: GitHubAPIClient, username: str) -> dict:
    """Return gross/discount/net costs for Actions, Copilot, Git LFS, and their total."""
    actions = _summary_cost(_billing_summary(api, username, "Actions"))
    copilot = _summary_cost(_billing_summary(api, username, "Copilot"))
    git_lfs = _summary_cost(_billing_summary(api, username, "git_lfs"))
    total = {
        "gross": actions["gross"] + copilot["gross"] + git_lfs["gross"],
        "discount": actions["discount"] + copilot["discount"] + git_lfs["discount"],
        "net": actions["net"] + copilot["net"] + git_lfs["net"],
    }
    return {"actions": actions, "copilot": copilot, "git_lfs": git_lfs, "total": total}


def _limited_repos(api: GitHubAPIClient, max_repos: int) -> tuple[list[dict], bool]:
    repos = api.get_all_pages("/user/repos", {"type": "all"})
    return repos[:max_repos], len(repos) > max_repos


def _single_warning_state(report_data: dict, warn_over: str) -> list[str]:
    raw = warn_over.strip().removeprefix("$")
    if raw.endswith("%"):
        actions = report_data.get("actions")
        if not actions:
            return ["Percentage warning threshold skipped: Actions data not included in report."]
        threshold = float(raw[:-1])
        usage = float(actions.get("minutes_percent", 0.0))
        if usage > threshold:
            return [f"Actions minutes usage is {usage:.1f}%, above the {threshold:.1f}% threshold."]
        return []
    threshold = float(raw)
    monthly_costs = report_data.get("monthly_costs")
    if not monthly_costs:
        return []
    total_net = float(monthly_costs["total"]["net"])
    if total_net > threshold:
        return [
            f"Current monthly net cost is {fmt_price(total_net)}, "
            f"above the {fmt_price(threshold)} threshold."
        ]
    return []


def get_warning_state(report_data: dict, warn_over: list[str] | str | None) -> list[str]:
    """Return warning messages if cost or usage exceeds any warn_over threshold."""
    if not warn_over:
        return []
    thresholds = [warn_over] if isinstance(warn_over, str) else warn_over
    warnings = []
    for threshold in thresholds:
        warnings.extend(_single_warning_state(report_data, threshold))
    return warnings


def get_key_insights(report_data: dict) -> list[str]:
    """Return up to three plain-English insight strings derived from report_data."""
    insights = []
    actions = report_data.get("actions")
    consumers = report_data.get("repo_consumers")
    if actions and consumers and consumers.get("by_minutes"):
        top = consumers["by_minutes"][0]
        minutes = float(actions.get("minutes", 0.0))
        if minutes:
            insights.append(
                f"{top['repo']} accounts for {top['minutes'] / minutes * 100:.0f}% of Actions minutes."
            )
    if actions and float(actions.get("storage_percent", 0.0)) < 100:
        insights.append("Actions storage is below the free-tier limit.")
    return insights[:3]


def _rate_limit(api: GitHubAPIClient) -> tuple[int | None, int | None]:
    try:
        data = api.request("GET", "/rate_limit")
    except RuntimeError:
        return None, None
    core = (data or {}).get("resources", {}).get("core", {})
    return core.get("limit"), core.get("remaining")


def build_report_data(
    api: GitHubAPIClient,
    username: str,
    *,
    include_actions: bool,
    include_copilot: bool,
    include_lfs: bool,
    include_consumers: bool,
    include_artifact_storage: bool,
    include_release_assets: bool,
    max_repos: int,
    warn_over: list[str] | str | None,
) -> dict:
    """Fetch and assemble all enabled billing sections into a single report dict."""
    errors = {}
    repos = []
    truncated = False
    needs_repos = include_consumers or include_artifact_storage or include_release_assets
    if needs_repos:
        repos, truncated = _limited_repos(api, max_repos)
    core_limit, core_remaining = _rate_limit(api)
    api_estimate = estimate_api_request_count(
        repo_count=len(repos) + (1 if truncated else 0),
        include_consumers=include_consumers,
        include_artifact_storage=include_artifact_storage,
        include_release_assets=include_release_assets,
        max_repos=max_repos,
        core_limit=core_limit,
        core_remaining=core_remaining,
    )
    if (
        core_remaining is not None
        and core_remaining < api_estimate["estimated_incremental_requests"]
    ):
        raise RuntimeError("GitHub REST API quota is too low for selected repo-level sections.")

    report = {
        "username": username,
        "period": "current_month",
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "warnings": [],
        "errors": errors,
        "actions": None,
        "copilot": None,
        "git_lfs": None,
        "monthly_costs": None,
        "repo_consumers": None,
        "artifact_storage": None,
        "release_assets": None,
        "api_estimate": api_estimate,
        "insights": [],
    }

    for key, enabled, getter in [
        ("actions", include_actions, lambda: get_actions_usage(api, username)),
        ("copilot", include_copilot, lambda: get_copilot_usage(api, username)),
        ("git_lfs", include_lfs, lambda: get_gitlfs_usage(api, username)),
    ]:
        if enabled:
            try:
                report[key] = getter()
            except RuntimeError as exc:
                errors[key] = str(exc)

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

    if include_consumers:
        try:
            report["repo_consumers"] = get_repo_consumers(api, repos, max_repos=max_repos)
        except RuntimeError as exc:
            errors["repo_consumers"] = str(exc)
    if include_artifact_storage:
        try:
            report["artifact_storage"] = get_artifact_storage_details(api, repos, max_repos)
        except RuntimeError as exc:
            errors["artifact_storage"] = str(exc)
    if include_release_assets:
        try:
            report["release_assets"] = get_release_asset_details(api, repos, max_repos)
        except RuntimeError as exc:
            errors["release_assets"] = str(exc)

    report["insights"] = get_key_insights(report)
    report["warnings"] = get_warning_state(report, warn_over)
    return report
