"""Command-line entry point for github-usage."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from . import __version__
from . import legacy


HELP = """GitHub Monthly Usage Report

Usage:
  github-usage [GITHUB_TOKEN]
  github-usage-v3 [GITHUB_TOKEN]

Token resolution:
  1. Command-line argument
  2. GITHUB_TOKEN environment variable
  3. gh auth token
  4. ~/.config/github-cli/github.yaml
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in {"-h", "--help"}:
        print(HELP)
        return 0

    if args and args[0] == "--version":
        print(f"github-usage {__version__}")
        return 0

    old_argv = sys.argv[:]
    sys.argv = ["github-usage", *args]
    try:
        if not legacy.resolve_token():
            print("Error: No GitHub token found.")
            print("  Usage: github-usage <token>")
            print("  Or set GITHUB_TOKEN env var.")
            print("  Or run: gh auth login")
            return 1
        try:
            legacy.main()
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)
    finally:
        sys.argv = old_argv
