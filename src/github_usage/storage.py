"""Repository storage analysis helpers.

Distinguishes Actions **artifacts** (quota-relevant for private repos) from
**release assets** (separate, not quota-billed). Artifact items carry expiry
fields from the Actions artifacts API so reports can flag soon-to-expire and
expired storage without extra API calls.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from .visibility import repo_visibility

_EXPIRING_SOON_DAYS = 7


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp; return ``None`` on missing/invalid input."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _days_until(expires_at: str | None, *, today: date) -> int | None:
    """Whole days from ``today`` until ``expires_at`` (negative if past)."""
    parsed = _parse_iso_datetime(expires_at)
    if parsed is None:
        return None
    return (parsed.date() - today).days


def _retention_days(created_at: str | None, expires_at: str | None) -> int | None:
    """Retention window in days from created→expires; ``None`` if undated."""
    created = _parse_iso_datetime(created_at)
    expires = _parse_iso_datetime(expires_at)
    if created is None or expires is None:
        return None
    return max(0, (expires.date() - created.date()).days)


def _artifact_item(art: dict, *, today: date) -> dict:
    """Build one artifact item dict with size and expiry metadata."""
    size_bytes = float(art.get("size_in_bytes", 0) or 0)
    storage_gb = size_bytes / (1024 * 1024 * 1024)
    expires_at = art.get("expires_at")
    expired = bool(art.get("expired", False))
    days = _days_until(expires_at if isinstance(expires_at, str) else None, today=today)
    return {
        "type": "Artifact",
        "name": art.get("name", "Unknown"),
        "count": 1,
        "storage": storage_gb,
        "size": f"{size_bytes / (1024 * 1024):.0f} MB",
        "created_at": art.get("created_at"),
        "expires_at": expires_at,
        "expired": expired,
        "days_to_expiry": days,
    }


def _release_item(asset: dict) -> dict:
    """Build one release-asset item dict (not quota-billed)."""
    size_bytes = float(asset.get("size", 0) or 0)
    storage_gb = size_bytes / (1024 * 1024 * 1024)
    return {
        "type": "Release Asset",
        "name": asset.get("name", "Unknown"),
        "count": 1,
        "storage": storage_gb,
        "size": f"{size_bytes / (1024 * 1024):.0f} MB",
    }


def _repo_retention_days(artifact_items: list[dict]) -> int | None:
    """Retention from the newest non-expired artifact; ``None`` if unavailable."""
    candidates = [
        item
        for item in artifact_items
        if not item.get("expired") and item.get("created_at") and item.get("expires_at")
    ]
    if not candidates:
        return None
    newest = max(
        candidates,
        key=lambda item: _parse_iso_datetime(item.get("created_at"))
        or datetime.min.replace(tzinfo=UTC),
    )
    return _retention_days(newest.get("created_at"), newest.get("expires_at"))


def _rollup_artifacts(artifact_items: list[dict]) -> dict:
    """Per-repo artifact count / expiry rollup fields."""
    expired_count = sum(1 for item in artifact_items if item.get("expired"))
    expiring_soon = sum(
        1
        for item in artifact_items
        if not item.get("expired")
        and item.get("days_to_expiry") is not None
        and 0 <= int(item["days_to_expiry"]) <= _EXPIRING_SOON_DAYS
    )
    earliest = None
    for item in artifact_items:
        if item.get("expired"):
            continue
        exp = item.get("expires_at")
        if isinstance(exp, str) and (earliest is None or exp < earliest):
            earliest = exp
    return {
        "artifact_count": len(artifact_items),
        "expired_count": expired_count,
        "expiring_soon_count": expiring_soon,
        "earliest_expiry": earliest,
        "retention_days": _repo_retention_days(artifact_items),
    }


def get_storage_analysis(api, repos, *, reference_date: date | None = None):
    """Analyze storage per repo: artifacts, releases, LFS.

    Keeps ``total_storage`` for backward compatibility and adds
    ``artifact_storage_gb`` / ``release_storage_gb`` so renderers can separate
    quota-relevant artifacts from free/unlimited release assets.
    """
    today = reference_date or date.today()
    repo_storage = []
    for repo in repos:
        try:
            owner = (repo.get("owner") or {}).get("login")
            name = repo.get("name")
            if not owner or not name:
                continue
            full = repo.get("full_name") or f"{owner}/{name}"
            items: list[dict] = []
            artifact_storage_gb = 0.0
            release_storage_gb = 0.0

            try:
                artifacts = api.get_all_pages(
                    f"/repos/{owner}/{name}/actions/artifacts",
                    {"per_page": 100},
                )
            except RuntimeError:
                artifacts = []
            artifact_items = []
            for art in artifacts or []:
                item = _artifact_item(art, today=today)
                artifact_items.append(item)
                items.append(item)
                artifact_storage_gb += float(item["storage"])

            try:
                releases = api.get_all_pages(
                    f"/repos/{owner}/{name}/releases",
                    {"per_page": 100},
                )
            except RuntimeError:
                releases = []
            for rel in releases or []:
                for asset in rel.get("assets", []) or []:
                    item = _release_item(asset)
                    items.append(item)
                    release_storage_gb += float(item["storage"])

            total_storage = artifact_storage_gb + release_storage_gb
            if total_storage > 0 or items:
                entry = {
                    "name": full,
                    "total_storage": total_storage,
                    "artifact_storage_gb": artifact_storage_gb,
                    "release_storage_gb": release_storage_gb,
                    "items": items,
                    "visibility": repo_visibility(repo),
                }
                entry.update(_rollup_artifacts(artifact_items))
                repo_storage.append(entry)
        except (KeyError, RuntimeError):
            continue

    return {"repos": repo_storage}
