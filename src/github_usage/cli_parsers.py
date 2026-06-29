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
            "locally. --diff reports per-file drift between the local "
            "working tree and the configured remote's default branch for "
            "the tracked workflow YAMLs (mutually exclusive with --api, "
            "and respecting --profile if given); --no-fetch (or "
            "GITHUB_USAGE_SKIP_FETCH=1) skips the git fetch step. The "
            "view matches what is configured on GitHub only when local "
            "files reflect the pushed repo."
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
    # --api and --diff are alternative views; enforce at parse time.
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument(
        "--api",
        action="store_true",
        help="Also query GitHub API for active workflows and latest runs",
    )
    exclusive.add_argument(
        "--diff",
        action="store_true",
        help=(
            "Report per-file drift between the local working tree and "
            "the configured remote's default branch for the tracked "
            "workflow YAMLs. Runs `git fetch <remote>` by default; pass "
            "--no-fetch (or set GITHUB_USAGE_SKIP_FETCH=1) to skip the "
            "fetch. Cannot be combined with --api, --owner, or --repo. "
            "With --profile NAME, scopes the diff to that profile's "
            "workflow file only. Requires git on PATH and a git "
            "working tree."
        ),
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help=(
            "Skip `git fetch <remote>` when using --diff. Use the local "
            "<remote>/<branch> ref as-is. Equivalent to setting "
            "GITHUB_USAGE_SKIP_FETCH=1."
        ),
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
