"""Local disk cache for fetched GitHub billing report data.

Caches JSON snapshots under ``.github-usage/cache/`` so repeated legacy and
email reports can reuse recent API results. Cache entries are keyed by report
kind, a token fingerprint (not the token itself), and the fetch parameters
that affect the assembled dict shape.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .export_json import _DatetimeEncoder
from .setup_config import SetupPaths

DEFAULT_CACHE_MAX_AGE_SECONDS = 3600
CACHE_VERSION = 1


def cache_disabled() -> bool:
    """Return True when report caching is turned off via environment."""
    raw = os.environ.get("GITHUB_USAGE_DISABLE_CACHE", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    # Under unittest, avoid reading a developer's real .github-usage/cache unless opted in.
    return "unittest" in sys.modules


@dataclass(frozen=True)
class CacheSettings:
    """Resolved cache TTL for report fetches."""

    max_age_seconds: int = DEFAULT_CACHE_MAX_AGE_SECONDS


@dataclass(frozen=True)
class CacheHit:
    """Metadata when a cached report snapshot is reused."""

    from_cache: bool = False
    age_seconds: float | None = None
    max_age_seconds: int | None = None
    cached_at: str | None = None


def cache_dir(paths: SetupPaths) -> Path:
    """Directory for cached report JSON files."""
    return paths.config_dir / "cache"


def token_fingerprint(token: str) -> str:
    """Return a stable non-reversible fingerprint for cache keying."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-stable copy of cache-key parameters."""
    normalized: dict[str, Any] = {}
    for key in sorted(params):
        value = params[key]
        if isinstance(value, list):
            normalized[key] = sorted(value)
        else:
            normalized[key] = value
    return normalized


def cache_entry_path(paths: SetupPaths, *, kind: str, token: str, params: dict[str, Any]) -> Path:
    """Return the on-disk path for a cache key."""
    payload = json.dumps(
        {
            "kind": kind,
            "token": token_fingerprint(token),
            "params": _normalize_params(params),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return cache_dir(paths) / f"{kind}-{digest}.json"


def load_cache_settings(paths: SetupPaths) -> CacheSettings:
    """Load ``[cache].max_age_seconds`` from ``config.toml`` when present."""
    if not paths.config_file.is_file():
        return CacheSettings()
    data = tomllib.loads(paths.config_file.read_text(encoding="utf-8"))
    cache = data.get("cache")
    if not isinstance(cache, dict):
        return CacheSettings()
    raw = cache.get("max_age_seconds", DEFAULT_CACHE_MAX_AGE_SECONDS)
    try:
        max_age = int(raw)
    except (TypeError, ValueError):
        max_age = DEFAULT_CACHE_MAX_AGE_SECONDS
    return CacheSettings(max_age_seconds=max(0, max_age))


def resolve_cache_max_age(
    paths: SetupPaths,
    *,
    override_seconds: int | None = None,
    gui_override_seconds: int | None = None,
) -> int:
    """Resolve TTL with explicit override, then GUI override, then config.toml."""
    if override_seconds is not None:
        return max(0, int(override_seconds))
    if gui_override_seconds is not None:
        return max(0, int(gui_override_seconds))
    return load_cache_settings(paths).max_age_seconds


def _parse_cached_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def cache_age_seconds(cached_at: str, *, now: datetime | None = None) -> float | None:
    """Return age in seconds for an ISO ``cached_at`` timestamp."""
    parsed = _parse_cached_at(cached_at)
    if parsed is None:
        return None
    reference = now or datetime.now(tz=UTC)
    return max(0.0, (reference - parsed).total_seconds())


def is_cache_fresh(cached_at: str, max_age_seconds: int, *, now: datetime | None = None) -> bool:
    """Return True when ``cached_at`` is younger than ``max_age_seconds``."""
    if max_age_seconds <= 0:
        return False
    age = cache_age_seconds(cached_at, now=now)
    if age is None:
        return False
    return age < float(max_age_seconds)


def format_cache_hit_message(age_seconds: float, max_age_seconds: int) -> str:
    """Human-readable note for CLI/TUI when reusing cached data."""
    age_min = max(0, int(age_seconds // 60))
    if max_age_seconds >= 3600 and max_age_seconds % 3600 == 0:
        ttl = f"{max_age_seconds // 3600}h"
    else:
        ttl = f"{max_age_seconds // 60}m"
    return (
        f"Using cached report data ({age_min} min old, TTL {ttl}). "
        "Pass --refresh to fetch fresh data."
    )


def load_cached_report(
    paths: SetupPaths,
    *,
    kind: str,
    token: str,
    params: dict[str, Any],
    max_age_seconds: int,
    refresh: bool = False,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, str | None, CacheHit]:
    """Load a fresh cached report dict when allowed.

    Returns ``(data, username, cache_hit)``. ``data`` is ``None`` on miss.
    """
    miss = CacheHit(from_cache=False, max_age_seconds=max_age_seconds)
    if refresh or max_age_seconds <= 0 or cache_disabled():
        return None, None, miss

    path = cache_entry_path(paths, kind=kind, token=token, params=params)
    if not path.is_file():
        return None, None, miss

    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None, miss

    cached_at = str(wrapper.get("cached_at", ""))
    if not is_cache_fresh(cached_at, max_age_seconds, now=now):
        return None, None, miss

    data = wrapper.get("data")
    if not isinstance(data, dict):
        return None, None, miss

    username = wrapper.get("username")
    age = cache_age_seconds(cached_at, now=now)
    return (
        data,
        str(username) if username else None,
        CacheHit(
            from_cache=True,
            age_seconds=age,
            max_age_seconds=max_age_seconds,
            cached_at=cached_at,
        ),
    )


def store_cached_report(
    paths: SetupPaths,
    *,
    kind: str,
    token: str,
    params: dict[str, Any],
    username: str,
    data: dict[str, Any],
    cached_at: datetime | None = None,
) -> Path:
    """Persist a report dict snapshot atomically."""
    if cache_disabled():
        return cache_entry_path(paths, kind=kind, token=token, params=params)
    when = cached_at or datetime.now(tz=UTC)
    cached_at_text = when.astimezone(UTC).isoformat().replace("+00:00", "Z")
    wrapper = {
        "version": CACHE_VERSION,
        "kind": kind,
        "username": username,
        "params": _normalize_params(params),
        "cached_at": cached_at_text,
        "data": data,
    }
    path = cache_entry_path(paths, kind=kind, token=token, params=params)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(wrapper, handle, indent=2, ensure_ascii=False, cls=_DatetimeEncoder)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise
    return path


def legacy_cache_params(
    *,
    max_repos: int,
    warn_over: list[str] | str | None = None,
    include_release_assets: bool = False,
) -> dict[str, Any]:
    """Build cache-key parameters for the legacy report superset."""
    warn_values: list[str] | None
    if warn_over is None:
        warn_values = None
    elif isinstance(warn_over, str):
        warn_values = [warn_over]
    else:
        warn_values = list(warn_over)
    return {
        "max_repos": int(max_repos),
        "warn_over": warn_values,
        "include_release_assets": bool(include_release_assets),
    }


def email_cache_params(
    *,
    include_actions: bool,
    include_copilot: bool,
    include_lfs: bool,
    include_consumers: bool,
    include_artifact_storage: bool,
    include_release_assets: bool,
    max_repos: int,
    warn_over: list[str] | str | None,
) -> dict[str, Any]:
    """Build cache-key parameters for :func:`report_data.build_report_data`."""
    warn_values: list[str] | None
    if warn_over is None:
        warn_values = None
    elif isinstance(warn_over, str):
        warn_values = [warn_over]
    else:
        warn_values = list(warn_over)
    return {
        "include_actions": bool(include_actions),
        "include_copilot": bool(include_copilot),
        "include_lfs": bool(include_lfs),
        "include_consumers": bool(include_consumers),
        "include_artifact_storage": bool(include_artifact_storage),
        "include_release_assets": bool(include_release_assets),
        "max_repos": int(max_repos),
        "warn_over": warn_values,
    }
