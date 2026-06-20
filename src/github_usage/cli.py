"""Command-line entry point for github-usage."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__, email_report, export_report, report_data
from .api import GitHubAPI
from .auth import check_user_scope, resolve_token
from .cli_parsers import _email_parser, _legacy_parser
from .legacy_report import main as legacy_main

HELP = """GitHub Monthly Usage Report

Usage:
  github-usage [GITHUB_TOKEN] [options]
  github-usage email-report [options]
  github-usage setup [options]

Setup:
  ./setup.sh                  Guided setup for secrets, options, launchd, CI, hooks
  github-usage setup --status Show configured paths without printing secrets
  github-usage setup --verify Run email-report --dry-run using local config
  github-usage setup --print-args Print email-report CLI args from config.toml

Legacy report options:
  --export FORMAT         Export format: csv | xlsx | pdf | json | text | none
  --output PATH           Output file path (auto-generated if omitted)
  --json                  Shorthand for --export json (prints to stdout without --output)
  --no-interactive        Never prompt; use defaults
  --dry-run               No-op for the legacy flow
  --timeout SECONDS       Seconds to wait before failing a request
  --max-retries N         Maximum number of retry attempts for transient errors

Email-report options:
  --export FORMAT         Export the report to a file in the given format
  --output PATH           Output file path (auto-generated if omitted)
  --email-format FMT      Email body format: text | html (html deferred)
  --include-consumers, --include-artifact-storage, --include-release-assets,
  --yes-include-release-assets, --max-repos N, --warn-over VALUE,
  --skip-actions, --skip-copilot, --skip-lfs, --dry-run,
  --timeout SECONDS, --max-retries N

Note: a --month YYYY-MM flag for historical billing queries is planned but
deferred. GitHub's billing endpoints do not currently support date-range
filtering; see docs/api-discovery-month.md.

Token resolution:
  1. Command-line argument
  2. GITHUB_TOKEN environment variable
  3. gh auth token
  4. ~/.config/github-cli/github.yaml

Export optional dependencies:
  pip install github-usage[export-xlsx]   # for --export xlsx
  pip install github-usage[export-pdf]    # for --export pdf
"""

_EXPORT_PROMPT_CHOICES = {
    "1": "csv",
    "2": "xlsx",
    "3": "pdf",
    "4": "json",
    "5": "text",
    "6": "none",
    "": "none",
}


def _split_optional_token(argv: Sequence[str]) -> tuple[str | None, list[str]]:
    """Peel a leading CLI token from argv when it is not a flag."""
    argv = list(argv)
    if argv and not argv[0].startswith("-"):
        return argv.pop(0), argv
    return None, argv


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


def _prompt_export_format() -> str:
    """Prompt the user for an export format in a TTY.

    Returns the chosen format, defaulting to ``"none"`` on empty input.
    Reprompts until the user enters a valid choice (1-6 or Enter).
    """
    print("Export options:")
    print("  1) CSV   - Spreadsheet-compatible comma-separated values")
    print("  2) XLSX  - Excel workbook (requires openpyxl)")
    print("  3) PDF   - Formatted PDF document (requires fpdf2)")
    print("  4) JSON  - Machine-readable JSON")
    print("  5) Text  - Plain text report")
    print("  6) None  - No export file")
    while True:
        choice = input("Choose an export format [None]: ").strip()
        export_format = _EXPORT_PROMPT_CHOICES.get(choice)
        if export_format is not None:
            return export_format
        print("Invalid choice. Enter 1-6 or press Enter for None.")


def _validate_export_args(args: argparse.Namespace) -> str | None:
    """Return an error message if the export-related args are invalid."""
    is_json = getattr(args, "json", False)
    if is_json and args.export:
        return "Error: --json and --export are mutually exclusive."
    if args.output and not (args.export or is_json):
        return "Error: --output requires --export or --json."
    return None


def _resolve_export_format(args: argparse.Namespace) -> str | None:
    """Return the effective export format (with --json sugar) or None if no export."""
    if getattr(args, "json", False):
        return "json"
    return args.export


def _run_email_report(argv: Sequence[str]) -> int:
    parser = _email_parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return _safe_exit_code(exc.code)

    if args.max_repos < 1:
        print("Error: --max-repos must be at least 1.")
        return 1

    if args.email_format == "html":
        print("Error: --email-format html is not yet supported.")
        return 1

    export_format = _resolve_export_format(args)
    error = _validate_export_args(args)
    if error:
        print(error)
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

    token = resolve_token(argv=[])
    if not token:
        from .auth import print_missing_token_error

        print_missing_token_error()
        return 1

    api = GitHubAPI(token, timeout=args.timeout, max_retries=args.max_retries)
    if not args.dry_run:
        missing = _missing_env(["RESEND_API_KEY", "REPORT_EMAIL", "RESEND_FROM"])
        if missing:
            print("Error: missing required email environment variable(s):")
            for name in missing:
                print(f"  - {name}")
            return 1

    if not _confirm_release_assets(args):
        return 1

    try:
        user = api.request("GET", "/user")
        username = user.get("login")
        if not username:
            print("Error: GitHub /user response did not include a login.")
            return 1
        if not check_user_scope(api, user=user):
            print("Error: Your GitHub token is not valid for this operation.")
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
        if export_format and export_format != "none":
            payload = body if export_format == "text" else data
            path = export_report.export(
                payload,
                export_format,
                output_path=args.output,
                username=username,
                redact_data=True,
            )
            print(f"Exported to: {path}")
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
            timeout=args.timeout,
            max_retries=args.max_retries,
        )
        print(f"Email report sent to {os.environ['REPORT_EMAIL']}.")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1


def _run_legacy_report(argv: Sequence[str]) -> int:
    token, flag_argv = _split_optional_token(argv)
    parser = _legacy_parser()
    try:
        args = parser.parse_args(flag_argv)
    except SystemExit as exc:
        return _safe_exit_code(exc.code)

    if args.help:
        print(HELP)
        return 0
    if args.version:
        print(f"github-usage {__version__}")
        return 0

    error = _validate_export_args(args)
    if error:
        print(error)
        return 1

    export_format = _resolve_export_format(args)

    legacy_argv = ["github-usage", *([token] if token else []), *flag_argv]
    if not resolve_token(argv=legacy_argv):
        from .auth import print_missing_token_error

        print_missing_token_error()
        return 1

    if not export_format and sys.stdin.isatty() and not args.no_interactive:
        export_format = _prompt_export_format()

    try:
        legacy_main(
            export=export_format,
            output=args.output,
            no_interactive=args.no_interactive,
            month=None,
            dry_run=args.dry_run,
            timeout=getattr(args, "timeout", None),
            max_retries=getattr(args, "max_retries", None),
        )
    except SystemExit as exc:
        return _safe_exit_code(exc.code)

    if export_format and export_format != "none":
        token = resolve_token(argv=legacy_argv)
        api = GitHubAPI(token)
        user = api.request("GET", "/user")
        username = user.get("login") or "unknown"
        data = report_data.build_report_data(
            api,
            username,
            include_actions=True,
            include_copilot=True,
            include_lfs=True,
            include_consumers=True,
            include_artifact_storage=True,
            include_release_assets=False,
            max_repos=100,
            warn_over=None,
        )
        if not args.json or args.output:
            path = export_report.export(
                data,
                export_format,
                output_path=args.output,
                username=username,
                month=None,
                redact_data=True,
            )
            print(f"Exported to: {path}")
        else:
            export_report.export(data, export_format, redact_data=True, to_stdout=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    try:
        args = list(sys.argv[1:] if argv is None else argv)

        if args and args[0] == "email-report":
            return _run_email_report(args[1:])

        if args and args[0] == "setup":
            from .setup_wizard import run_setup

            return run_setup(args[1:])

        return _run_legacy_report(args)
    except SystemExit as exc:
        return _safe_exit_code(exc.code)
