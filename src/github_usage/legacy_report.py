"""Orchestration for the legacy interactive report."""

from __future__ import annotations

import sys

from .api import GitHubAPI
from .auth import check_user_scope, resolve_token
from .legacy_report_data import LEGACY_DEFAULT_MAX_REPOS, build_legacy_report_data
from .legacy_terminal import render_legacy_report
from .report_account import fetch_account_info, fetch_rate_limits
from .report_cache import (
    CacheHit,
    format_cache_hit_message,
    legacy_cache_params,
    load_cached_report,
    resolve_cache_max_age,
    store_cached_report,
)
from .setup_config import (
    DEFAULT_EMAIL_REPORT,
    SetupPaths,
    find_profile,
    load_config,
    repo_root,
)
from .terminal import print_header


def _legacy_forecast_options(paths: SetupPaths) -> tuple[bool, float | None]:
    """Return ``(include_forecast, premium_requests_limit)`` from the default profile."""
    config = load_config(paths.config_file)
    try:
        profile = find_profile(config, "default")
    except KeyError:
        return bool(DEFAULT_EMAIL_REPORT["include_forecast"]), DEFAULT_EMAIL_REPORT[
            "premium_requests_limit"
        ]
    email = {**DEFAULT_EMAIL_REPORT, **profile.get("email_report", {})}
    return bool(email.get("include_forecast", True)), email.get("premium_requests_limit")


def run_legacy_report_session(
    *,
    timeout: float | None = None,
    max_retries: int | None = None,
    warn_over: list[str] | str | None = None,
    max_repos: int = LEGACY_DEFAULT_MAX_REPOS,
    refresh: bool = False,
    only_public: bool = False,
    only_private: bool = False,
    paths: SetupPaths | None = None,
    cache_max_age_seconds: int | None = None,
) -> tuple[int, dict | None, str | None, CacheHit]:
    """Fetch once, render terminal report; return ``(exit_code, data, username, cache)``."""
    token = resolve_token()
    if not token:
        from .auth import print_missing_token_error

        print_missing_token_error()
        return 1, None, None, CacheHit()

    resolved_paths = paths or SetupPaths.from_root(repo_root())
    include_forecast, premium_requests_limit = _legacy_forecast_options(resolved_paths)
    max_age = resolve_cache_max_age(resolved_paths, override_seconds=cache_max_age_seconds)
    params = legacy_cache_params(
        max_repos=max_repos,
        warn_over=warn_over,
        include_release_assets=False,
        only_public=only_public,
        only_private=only_private,
    )
    cached_data, cached_username, cache_hit = load_cached_report(
        resolved_paths,
        kind="legacy",
        token=token,
        params=params,
        max_age_seconds=max_age,
        refresh=refresh,
    )
    if cache_hit.from_cache and cached_data is not None and cached_username:
        print_header()
        if cache_hit.age_seconds is not None and cache_hit.max_age_seconds is not None:
            print(format_cache_hit_message(cache_hit.age_seconds, cache_hit.max_age_seconds))
        render_legacy_report(
            cached_data,
            include_forecast=include_forecast,
            premium_requests_limit=premium_requests_limit,
        )
        return 0, cached_data, cached_username, cache_hit

    try:
        api = GitHubAPI(token, timeout=timeout, max_retries=max_retries)
        if not check_user_scope(api):
            print("Error: Your GitHub token is not valid for this operation.")
            return 1, None, None, CacheHit()

        print_header()
        account = fetch_account_info(api)
        username = str(account.get("login") or "?")
        rate_limits = fetch_rate_limits(api)
        data = build_legacy_report_data(
            api,
            username,
            max_repos=max_repos,
            warn_over=warn_over,
            include_release_assets=False,
            only_public=only_public,
            only_private=only_private,
            account=account,
            rate_limits=rate_limits,
        )
        if max_age > 0:
            store_cached_report(
                resolved_paths,
                kind="legacy",
                token=token,
                params=params,
                username=username,
                data=data,
            )
        render_legacy_report(
            data,
            include_forecast=include_forecast,
            premium_requests_limit=premium_requests_limit,
        )
        return 0, data, username, CacheHit(max_age_seconds=max_age)

    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1, None, None, CacheHit()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130, None, None, CacheHit()


def main(
    *,
    export: str | None = None,
    output: str | None = None,
    no_interactive: bool = False,
    month: str | None = None,
    dry_run: bool = False,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> str | None:
    """Run the legacy interactive report. Return the resolved username, or None on failure.

    Export orchestration is performed by :mod:`github_usage.cli` using the data
    returned from :func:`run_legacy_report_session`.
    """
    del export, output, no_interactive, month, dry_run  # CLI-owned kwargs
    code, _data, username, _cache = run_legacy_report_session(
        timeout=timeout, max_retries=max_retries
    )
    if code != 0:
        sys.exit(code if code != 130 else 1)
    return username
