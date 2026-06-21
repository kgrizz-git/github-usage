"""Optional repo-level report collectors and quota estimates."""

from __future__ import annotations

from .billing import BillingFetchError, get_actions_per_repo
from .report_helpers import gb_hours_to_avg_mb


def _safe_int_size(value) -> int | None:
    """Return ``int(value)`` for numeric inputs, ``None`` for missing,
    ``None``, booleans, or unparseable values. Used to skip artifacts /
    release assets whose size is not a clean integer."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def get_repo_consumers(api, repos: list[dict], limit: int = 5, max_repos: int = 100) -> dict:
    """Return top repos ranked by Actions minutes and gross cost."""
    rows = []
    errors: dict = {}
    considered = repos[:max_repos]
    for repo in considered:
        owner = repo.get("owner", {}).get("login", "")
        name = repo.get("name", "")
        full_name = repo.get("full_name") or f"{owner}/{name}"
        try:
            minutes, storage_gb_hours, sku = get_actions_per_repo(api, owner, name)
        except BillingFetchError as e:
            errors[full_name] = str(e)
            continue
        rows.append(
            {
                "repo": full_name,
                "minutes": float(minutes),
                "gross": sum(float(item.get("grossAmount", 0.0)) for item in sku.values()),
                "storage_avg_mb": gb_hours_to_avg_mb(float(storage_gb_hours)),
            }
        )
    return {
        "scanned_repo_count": len(considered),
        "max_repos": max_repos,
        "truncated": len(repos) > max_repos,
        "by_minutes": sorted(rows, key=lambda row: row["minutes"], reverse=True)[:limit],
        "by_cost": sorted(rows, key=lambda row: row["gross"], reverse=True)[:limit],
        "errors": errors,
    }


def get_artifact_storage_details(api, repos: list[dict], max_repos: int = 100) -> dict:
    """Return per-repo artifact storage totals for the top storage consumers."""
    rows = []
    considered = repos[:max_repos]
    for repo in considered:
        owner = repo.get("owner", {}).get("login", "")
        name = repo.get("name", "")
        artifacts = api.get_all_pages(f"/repos/{owner}/{name}/actions/artifacts", {"per_page": 100})
        size = sum(
            s
            for s in (_safe_int_size(item.get("size_in_bytes")) for item in artifacts)
            if s is not None
        )
        if size:
            rows.append(
                {"repo": repo.get("full_name") or f"{owner}/{name}", "artifact_bytes": size}
            )
    return {
        "scanned_repo_count": len(considered),
        "max_repos": max_repos,
        "truncated": len(repos) > max_repos,
        "top_repos": sorted(rows, key=lambda row: row["artifact_bytes"], reverse=True)[:5],
    }


def get_release_asset_details(api, repos: list[dict], max_repos: int = 100) -> dict:
    """Return per-repo release asset storage totals for the top storage consumers."""
    rows = []
    considered = repos[:max_repos]
    for repo in considered:
        owner = repo.get("owner", {}).get("login", "")
        name = repo.get("name", "")
        releases = api.get_all_pages(f"/repos/{owner}/{name}/releases", {"per_page": 100})
        size = sum(
            s
            for s in (
                _safe_int_size(asset.get("size"))
                for release in releases
                for asset in release.get("assets", [])
            )
            if s is not None
        )
        if size:
            rows.append(
                {"repo": repo.get("full_name") or f"{owner}/{name}", "release_asset_bytes": size}
            )
    return {
        "scanned_repo_count": len(considered),
        "max_repos": max_repos,
        "truncated": len(repos) > max_repos,
        "top_repos": sorted(rows, key=lambda row: row["release_asset_bytes"], reverse=True)[:5],
    }


def estimate_api_request_count(
    repo_count: int,
    include_consumers: bool,
    include_artifact_storage: bool,
    include_release_assets: bool,
    max_repos: int,
    core_limit: int | None = None,
    core_remaining: int | None = None,
) -> dict:
    """Estimate the number of additional API requests optional sections will make."""
    repos_considered = min(repo_count, max_repos)
    per_repo_options = sum([include_consumers, include_artifact_storage, include_release_assets])
    estimated = repos_considered * per_repo_options
    percent = None
    if core_remaining:
        percent = round(estimated / core_remaining * 100, 1)
    notes = []
    if repo_count > max_repos:
        notes.append(f"Repository list truncated to {max_repos} of {repo_count} repositories.")
    if estimated:
        notes.append(f"Optional repo-level sections may use about {estimated} REST API requests.")
    return {
        "core_limit": core_limit,
        "core_remaining": core_remaining,
        "estimated_incremental_requests": estimated,
        "estimated_percent_of_remaining": percent,
        "repos_considered": repos_considered,
        "notes": notes,
    }
