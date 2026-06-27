"""Email-report subcommand helpers for ``cli._run_email_report``.

Lifted out of ``cli`` so the main CLI file stays under the 400-line
warn threshold while the email-report function is trimmed.

All helpers are module-private (underscore-prefixed). They are imported
by ``cli`` and used only from ``_run_email_report``.
"""

from __future__ import annotations

import argparse

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
    )
    print(f"Exported to: {path}")
