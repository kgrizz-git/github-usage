"""Command-line entry point for github-usage."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__, email_report, report_data
from .api import GitHubAPI
from .auth import check_user_scope, resolve_token
from .legacy_report import main as legacy_main

HELP = """GitHub Monthly Usage Report

Usage:
  github-usage [GITHUB_TOKEN]
  github-usage email-report [options]

Token resolution:
  1. Command-line argument
  2. GITHUB_TOKEN environment variable
  3. gh auth token
  4. ~/.config/github-cli/github.yaml
"""


def _email_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-usage email-report",
        description="Send or preview a scheduled plain-text GitHub usage email report.",
    )
    parser.add_argument("--include-consumers", action="store_true")
    parser.add_argument("--include-artifact-storage", action="store_true")
    parser.add_argument("--include-release-assets", action="store_true")
    parser.add_argument("--yes-include-release-assets", action="store_true")
    parser.add_argument("--max-repos", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--warn-over")
    parser.add_argument("--skip-actions", action="store_true")
    parser.add_argument("--skip-copilot", action="store_true")
    parser.add_argument("--skip-lfs", action="store_true")
    return parser


def _resolve_email_token() -> str | None:
    old_argv = sys.argv[:]
    sys.argv = ["github-usage"]
    try:
        return resolve_token()
    finally:
        sys.argv = old_argv


def _missing_env(names: list[str]) -> list[str]:
    return [name for name in names if not os.environ.get(name, "").strip()]


def _confirm_release_assets(args: argparse.Namespace) -> bool:
    if not args.include_release_assets or args.yes_include_release_assets:
        return True
    if not sys.stdin.isatty():
        print(
            "Error: --include-release-assets requires --yes-include-release-assets "
            "in non-interactive runs."
        )
        return False
    print(
        "Release assets are optional inventory, not a billing/quota report. "
        "Listing them may use one REST API request per scanned repository."
    )
    answer = input("Include release asset inventory? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _safe_exit_code(code: Any) -> int:
    try:
        return int(code or 0)
    except (ValueError, TypeError):
        return 1


def _run_email_report(argv: Sequence[str]) -> int:
    parser = _email_parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return _safe_exit_code(exc.code)

    if args.max_repos < 1:
        print("Error: --max-repos must be at least 1.")
        return 1

    include_actions = not args.skip_actions
    include_copilot = not args.skip_copilot
    include_lfs = not args.skip_lfs
    if not any([include_actions, include_copilot, include_lfs, args.include_artifact_storage]):
        print(
            "Error: all default report sections were skipped. Enable at least one "
            "billing/quota section or use --include-artifact-storage."
        )
        return 1

    token = _resolve_email_token()
    if not token:
        from .auth import print_missing_token_error

        print_missing_token_error()
        return 1

    if not args.dry_run:
        missing = _missing_env(["RESEND_API_KEY", "REPORT_EMAIL", "RESEND_FROM"])
        if missing:
            print("Error: missing required email environment variable(s):")
            for name in missing:
                print(f"  - {name}")
            return 1

    if not _confirm_release_assets(args):
        return 1

    api = GitHubAPI(token)
    try:
        user = api.request("GET", "/user")
        username = user.get("login")
        if not username:
            print("Error: GitHub /user response did not include a login.")
            return 1
        if not check_user_scope(api):
            print("Error: Your GitHub token is missing the 'user' scope.")
            print("  The billing endpoints require the 'user' scope.")
            print("  Fix: run 'gh auth refresh -h github.com -s user'")
            return 1
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
        )
        body = email_report.format_report_email(data)
        if args.dry_run:
            print(body, end="")
            return 0
        subject = os.environ.get("REPORT_SUBJECT", "").strip() or email_report.default_subject(
            username, data.get("generated_at")
        )
        email_report.send_email(
            os.environ["RESEND_API_KEY"],
            os.environ["RESEND_FROM"],
            os.environ["REPORT_EMAIL"],
            subject,
            body,
        )
        print(f"Email report sent to {os.environ['REPORT_EMAIL']}.")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in {"-h", "--help"}:
        print(HELP)
        return 0

    if args and args[0] == "--version":
        print(f"github-usage {__version__}")
        return 0

    if args and args[0] == "email-report":
        return _run_email_report(args[1:])

    old_argv = sys.argv[:]
    sys.argv = ["github-usage", *args]
    try:
        if not resolve_token():
            from .auth import print_missing_token_error

            print_missing_token_error()
            return 1
        try:
            legacy_main()
            return 0
        except SystemExit as exc:
            return _safe_exit_code(exc.code)
    finally:
        sys.argv = old_argv
