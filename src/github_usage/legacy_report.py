"""Orchestration for the legacy interactive report."""

from __future__ import annotations

import sys

from .api import GitHubAPI
from .auth import check_user_scope, resolve_token
from .legacy_report_data import LEGACY_DEFAULT_MAX_REPOS, build_legacy_report_data
from .legacy_terminal import render_legacy_report
from .report_account import fetch_account_info, fetch_rate_limits
from .terminal import print_header


def run_legacy_report_session(
    *,
    timeout: float | None = None,
    max_retries: int | None = None,
    warn_over: list[str] | str | None = None,
    max_repos: int = LEGACY_DEFAULT_MAX_REPOS,
) -> tuple[int, dict | None, str | None]:
    """Fetch once, render terminal report; return ``(exit_code, data, username)``."""
    token = resolve_token()
    if not token:
        from .auth import print_missing_token_error

        print_missing_token_error()
        return 1, None, None

    try:
        api = GitHubAPI(token, timeout=timeout, max_retries=max_retries)
        if not check_user_scope(api):
            print("Error: Your GitHub token is not valid for this operation.")
            return 1, None, None

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
            account=account,
            rate_limits=rate_limits,
        )
        render_legacy_report(data)
        return 0, data, username

    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1, None, None
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130, None, None


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
    code, _data, username = run_legacy_report_session(timeout=timeout, max_retries=max_retries)
    if code != 0:
        sys.exit(code if code != 130 else 1)
    return username
