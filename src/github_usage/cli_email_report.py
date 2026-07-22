"""Email-report subcommand helpers for ``cli._run_email_report``.

Lifted out of ``cli`` so the main CLI file stays under the 400-line
warn threshold while the email-report function is trimmed.

All helpers are module-private (underscore-prefixed). They are imported
by ``cli`` and used only from ``_run_email_report``.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import email_report, export_report
from .api import GitHubAPI
from .auth import check_user_scope


def _validate_report_sections(
    include_actions: bool,
    include_copilot: bool,
    include_lfs: bool,
    include_artifact_storage: bool,
) -> int | None:
    """Return 1 if every default report section is skipped, else None."""
    if not any([include_actions, include_copilot, include_lfs, include_artifact_storage]):
        print(
            "Error: all default report sections were skipped. Enable at least one "
            "billing/quota section or use --include-artifact-storage."
        )
        return 1
    return None


def _cli_flag_present(argv: Sequence[str], *flags: str) -> bool:
    """Return True when any of ``flags`` appears in the raw CLI argv."""
    return any(item in flags for item in argv)


def _resolve_forecast_options(
    argv: Sequence[str],
    profile_flags: Sequence[str],
    args: argparse.Namespace,
) -> tuple[bool, float | None]:
    """Apply CLI > profile > default precedence for forecast options."""
    from .setup_config import DEFAULT_EMAIL_REPORT

    if _cli_flag_present(argv, "--include-forecast", "--no-include-forecast"):
        include_forecast = args.include_forecast and not args.no_include_forecast
    elif "--include-forecast" in profile_flags or "--no-include-forecast" in profile_flags:
        include_forecast = "--include-forecast" in profile_flags
    else:
        include_forecast = bool(DEFAULT_EMAIL_REPORT["include_forecast"])

    if _cli_flag_present(argv, "--premium-requests-limit"):
        premium_requests_limit = args.premium_requests_limit
    elif "--premium-requests-limit" in profile_flags:
        index = list(profile_flags).index("--premium-requests-limit")
        try:
            premium_requests_limit = float(profile_flags[index + 1])
        except (ValueError, IndexError):
            premium_requests_limit = None
    else:
        premium_requests_limit = DEFAULT_EMAIL_REPORT["premium_requests_limit"]

    return include_forecast, premium_requests_limit


def _init_github_api(
    token: str,
    timeout: float | None,
    max_retries: int | None,
) -> tuple[GitHubAPI, str] | int:
    """Initialize the GitHub API client and resolve the authenticated username.

    Returns ``(api, username)`` on success, or an exit code (int) on failure
    (already printed).
    """

    api = GitHubAPI(token, timeout=timeout, max_retries=max_retries)
    try:
        user = api.request("GET", "/user")
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    username = user.get("login")
    if not username:
        print("Error: GitHub /user response did not include a login.")
        return 1
    if not check_user_scope(api, user=user):
        print("Error: Your GitHub token is not valid for this operation.")
        return 1
    return api, username


def _send_email(
    args: argparse.Namespace,
    body: str,
    html_body: str | None,
    username: str,
    generated_at: str,
    *,
    subject: str | None = None,
    recipient: str | None = None,
    from_addr: str | None = None,
) -> None:
    """Build the subject and dispatch the email via email_report.send_email."""
    import os

    resolved_subject = (subject or "").strip() or os.environ.get("REPORT_SUBJECT", "").strip()
    if not resolved_subject:
        resolved_subject = email_report.default_subject(username, generated_at)
    resolved_recipient = (recipient or "").strip() or os.environ.get("REPORT_EMAIL", "").strip()
    resolved_from = (from_addr or "").strip() or os.environ.get("RESEND_FROM", "").strip()
    email_report.send_email(
        os.environ["RESEND_API_KEY"],
        resolved_from,
        resolved_recipient,
        resolved_subject,
        body,
        html=html_body,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    print(f"Email report sent to {resolved_recipient}.")


def _export_report(
    args: argparse.Namespace,
    export_format: str | None,
    body: str,
    data: dict,
    username: str,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
) -> None:
    """Export the report if an export format was requested; print the path on success."""
    if not export_format or export_format == "none":
        return
    payload = body if export_format == "text" else data
    path = export_report.export(
        payload,
        export_format,
        output_path=args.output,
        username=username,
        redact_data=True,
        include_forecast=include_forecast,
        premium_requests_limit=premium_requests_limit,
    )
    print(f"Exported to: {path}")


def _format_email_bodies(
    data: dict,
    email_format: str,
    *,
    include_forecast: bool,
    premium_requests_limit: float | None,
) -> tuple[str, str | None]:
    """Return ``(text_body, html_body_or_none)`` from report data."""
    body = email_report.format_report_email(
        data,
        include_forecast=include_forecast,
        premium_requests_limit=premium_requests_limit if include_forecast else None,
    )
    html_body = None
    if email_format == "html":
        html_body = email_report.format_html_report(
            data,
            include_forecast=include_forecast,
            premium_requests_limit=premium_requests_limit if include_forecast else None,
        )
    return body, html_body


def _check_email_env_vars(args: argparse.Namespace) -> int | None:
    """Return 1 if required email environment variables are missing, else None."""
    import os

    recipient = (getattr(args, "to", None) or "").strip() or os.environ.get(
        "REPORT_EMAIL", ""
    ).strip()
    missing = []
    for name in ("RESEND_API_KEY", "RESEND_FROM"):
        if not os.environ.get(name, "").strip():
            missing.append(name)
    if not recipient:
        missing.append("REPORT_EMAIL")
    if missing:
        print("Error: missing required email environment variable(s):")
        for name in missing:
            print(f"  - {name}")
        return 1
    return None


def _load_or_fetch_email_data(
    args: argparse.Namespace,
    token: str,
) -> tuple[dict, str] | int:
    """Load cached email data or fetch fresh; return ``(data, username)`` or exit code."""
    from .report_cache import (
        email_cache_params,
        format_cache_hit_message,
        load_cached_report,
        resolve_cache_max_age,
        store_cached_report,
    )
    from .setup_config import SetupPaths, repo_root

    include_actions = not args.skip_actions
    include_copilot = not args.skip_copilot
    include_lfs = not args.skip_lfs

    paths = SetupPaths.from_root(repo_root())
    max_age = resolve_cache_max_age(paths)
    cache_params = email_cache_params(
        include_actions=include_actions,
        include_copilot=include_copilot,
        include_lfs=include_lfs,
        include_consumers=args.include_consumers,
        include_artifact_storage=args.include_artifact_storage,
        include_release_assets=args.include_release_assets,
        max_repos=args.max_repos,
        warn_over=args.warn_over,
        only_public=getattr(args, "only_public", False),
        only_private=getattr(args, "only_private", False),
    )
    cached_data, cached_username, cache_hit = load_cached_report(
        paths,
        kind="email",
        token=token,
        params=cache_params,
        max_age_seconds=max_age,
        refresh=getattr(args, "refresh", False),
    )
    if cache_hit.from_cache and cached_data is not None:
        if cache_hit.age_seconds is not None and cache_hit.max_age_seconds is not None:
            print(format_cache_hit_message(cache_hit.age_seconds, cache_hit.max_age_seconds))
        return cached_data, cached_username or "unknown"

    api_result = _init_github_api(token, args.timeout, args.max_retries)
    if isinstance(api_result, int):
        return api_result
    api, username = api_result
    try:
        from . import report_data

        data = report_data.build_report_data(
            api,
            username,
            include_actions=include_actions,
            include_copilot=include_copilot,
            include_lfs=include_lfs,
            include_consumers=args.include_consumers,
            include_artifact_storage=args.include_artifact_storage,
            include_release_assets=args.include_release_assets,
            max_repos=args.max_repos,
            warn_over=args.warn_over,
            only_public=getattr(args, "only_public", False),
            only_private=getattr(args, "only_private", False),
        )
        if max_age > 0:
            store_cached_report(
                paths,
                kind="email",
                token=token,
                params=cache_params,
                username=username,
                data=data,
            )
        return data, username
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
