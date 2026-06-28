"""CLI argument parsers for github-usage."""

from __future__ import annotations

import argparse

_EXPORT_FORMATS = ("csv", "xlsx", "pdf", "json", "text", "none")


def _legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-usage",
        description="Run the GitHub usage report and optionally export to a file.",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--export", choices=_EXPORT_FORMATS, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-interactive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Seconds to wait before failing a request"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retry attempts for transient errors",
    )
    return parser


def _runs_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``runs`` subcommand."""
    parser = argparse.ArgumentParser(
        prog="github-usage runs",
        description=(
            "View all currently configured scheduled runs (launchd and GitHub "
            "Actions). Reflects local state: reads every config.toml profile "
            "and any email-report*.yml files in .github/workflows/, so it "
            "shows only what is on disk in this checkout. --api only "
            "enriches the local rows with each workflow's latest run; it "
            "does not enumerate workflows that exist on GitHub but not "
            "locally. The view matches what is configured on GitHub only "
            "when local files reflect the pushed repo."
        ),
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Show only the named profile's runs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of human-readable text",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Also query GitHub API for active workflows and latest runs",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner override for --api queries (default: parsed from local git remote)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repository name override for --api queries (default: parsed from local git remote)",
    )
    return parser


def _email_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-usage email-report",
        description="Send or preview a scheduled GitHub usage email report.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Expand options from a named report profile in config.toml",
    )
    parser.add_argument("--to", default=None, help="Recipient email address")
    parser.add_argument("--subject", default=None, help="Email subject line")
    parser.add_argument("--include-consumers", action="store_true")
    parser.add_argument("--include-artifact-storage", action="store_true")
    parser.add_argument("--include-release-assets", action="store_true")
    parser.add_argument("--yes-include-release-assets", action="store_true")
    parser.add_argument("--max-repos", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--warn-over", action="append")
    parser.add_argument("--skip-actions", action="store_true")
    parser.add_argument("--skip-copilot", action="store_true")
    parser.add_argument("--skip-lfs", action="store_true")
    parser.add_argument("--export", choices=_EXPORT_FORMATS, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--email-format", choices=("text", "html"), default="text")
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Seconds to wait before failing a request"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retry attempts for transient errors",
    )
    return parser
