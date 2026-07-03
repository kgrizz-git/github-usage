"""TUI entry-point routing and Textual launch (lazy imports only)."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass

KNOWN_SUBCOMMANDS = frozenset({"setup", "email-report", "runs"})

_MISSING_GUI_MESSAGE = """\
Error: TUI dependencies are not installed.
To launch the terminal interface, install the optional gui package:
  pip install 'github-usage[gui]'
Or if developing locally:
  uv pip install -e '.[gui]'
Or use command-line mode:
  github-usage --cli
  ./start.sh --cli
"""


@dataclass
class RouteResult:
    """Result of top-level argv routing before CLI subcommand dispatch."""

    handled: bool
    argv: list[str]
    exit_code: int = 0


def _strip_cli_flag(argv: list[str]) -> tuple[list[str], bool]:
    """Remove ``--cli`` and honor ``GITHUB_USAGE_CLI=1``."""
    cli_mode = os.environ.get("GITHUB_USAGE_CLI") == "1"
    stripped: list[str] = []
    for arg in argv:
        if arg == "--cli":
            cli_mode = True
        else:
            stripped.append(arg)
    return stripped, cli_mode


def _wants_cli_help(argv: list[str]) -> bool:
    return any(arg in ("-h", "--help", "--version") for arg in argv)


def route_entry(argv: Sequence[str]) -> RouteResult:
    """Decide whether to launch the TUI or continue with CLI dispatch."""
    from .cli import HELP

    argv_list = list(argv)
    had_cli_flag = "--cli" in argv_list
    stripped, cli_mode = _strip_cli_flag(argv_list)

    if _wants_cli_help(stripped):
        return RouteResult(handled=False, argv=stripped)

    if stripped and stripped[0] in KNOWN_SUBCOMMANDS:
        return RouteResult(handled=False, argv=stripped)

    if stripped and not stripped[0].startswith("-"):
        return RouteResult(handled=False, argv=stripped)

    if cli_mode and not stripped:
        if had_cli_flag:
            print(HELP)
            return RouteResult(handled=True, argv=[], exit_code=0)
        return RouteResult(handled=False, argv=[])

    if cli_mode:
        return RouteResult(handled=False, argv=stripped)

    if sys.stdin.isatty() and sys.stdout.isatty():
        return RouteResult(handled=True, argv=[], exit_code=run_tui())

    if not stripped:
        print(HELP)
        return RouteResult(handled=True, argv=[], exit_code=0)

    return RouteResult(handled=False, argv=stripped)


def run_tui() -> int:
    """Launch the Textual application or print install instructions."""
    try:
        from .gui.app import GitHubUsageApp
    except ImportError:
        print(_MISSING_GUI_MESSAGE, file=sys.stderr)
        return 1
    app = GitHubUsageApp()
    app.run()
    return 0
