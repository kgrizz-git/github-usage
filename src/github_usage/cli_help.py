"""CLI help and shell-safe install commands for the running interpreter."""

from __future__ import annotations

import shlex
import sys
import textwrap
from typing import Literal

_HELP = """GitHub Monthly Usage Report

Default (interactive terminal): launch the Textual TUI
  github-usage
  ./start.sh

Command-line mode: pass --cli
  github-usage --cli [GITHUB_TOKEN] [options]
  github-usage --cli setup [options]
  ./start.sh --cli                  Interactive bash menu
  ./start.sh setup                  Setup shortcut (no --cli required)

Subcommands (CLI shortcuts, no --cli required):
  github-usage email-report [options]
  github-usage setup [options]
  github-usage runs [options]

Setup:
  ./start.sh setup            Guided setup for secrets, options, launchd, CI, hooks
  github-usage setup --status Show configured paths without printing secrets
  github-usage setup --verify Run email-report --dry-run using local config
  github-usage setup --print-args Print email-report CLI args from config.toml

Runs:
  github-usage runs           View all currently configured scheduled runs
  github-usage runs --json    Output the configured runs as structured JSON
  github-usage runs --api     Also query the GitHub API for latest workflow runs
  github-usage runs --diff    Check for drift between local workflows and the remote default branch
                              (mutually exclusive with --api; --no-fetch skips the git fetch)

Local full report options:
  --export FORMAT         Export format: csv | xlsx | pdf | json | text | none
  --output PATH           Output file path (auto-generated if omitted)
  --json                  Shorthand for --export json (prints to stdout without --output)
  --no-interactive        Never prompt; use defaults
  --dry-run               No-op for the local full report flow
  --timeout SECONDS       Seconds to wait before failing a request
  --max-retries N         Maximum number of retry attempts for transient errors
  --refresh               Bypass local report cache and fetch fresh billing data

Cache:
  Recent report snapshots are stored under .github-usage/cache/ (gitignored).
  Configure TTL in .github-usage/config.toml: [cache] max_age_seconds = 3600
  Set max_age_seconds = 0 to disable caching.
  Setup rewrites config.toml without preserving [cache]; reapply custom TTLs
  or set GITHUB_USAGE_DISABLE_CACHE=1 to disable caching via environment.

Email-report options:
  --profile NAME, --to ADDRESS, --subject SUBJECT
  --include-forecast, --no-include-forecast
  --export FORMAT         Export the report to a file in the given format
  --output PATH           Output file path (auto-generated if omitted)
  --email-format FMT      Email body format: text | html
  --include-consumers, --include-artifact-storage, --include-release-assets,
  --yes-include-release-assets, --max-repos N, --warn-over VALUE,
  --skip-actions, --skip-copilot, --skip-lfs, --dry-run,
  --timeout SECONDS, --max-retries N, --refresh

TUI optional dependency:
  From a checkout: scripts/python -m pip install -e '.[gui]'
  Add the GUI dependency to this running interpreter (equivalent to the gui extra):
{gui_install}

Note: a --month YYYY-MM flag for historical billing queries is planned but
deferred. GitHub's billing endpoints do not currently support date-range
filtering; see docs/api-discovery-month.md.

Token resolution:
  1. Command-line argument
  2. GH_USAGE_TOKEN environment variable
  3. GITHUB_TOKEN environment variable
  4. gh auth token
  5. ~/.config/github-cli/github.yaml

Export optional dependencies (checkout commands):
  scripts/python -m pip install -e '.[export-xlsx]'   # for --export xlsx
  scripts/python -m pip install -e '.[export-pdf]'    # for --export pdf
  Outside a checkout, use the same Python environment running github-usage:
  XLSX:
{xlsx_install}
  PDF:
{pdf_install}
"""


InstallShell = Literal["posix", "cmd", "powershell"]


def pip_install_command(requirement: str, *, target_shell: InstallShell | None = None) -> str:
    """Render pip installation using the running interpreter for the selected shell.

    With no shell specified, POSIX platforms retain shlex rendering. Windows
    displays labeled cmd.exe and PowerShell alternatives rather than guessing
    the parent shell. cmd.exe cannot safely represent quotes, percent signs,
    exclamation marks, or line breaks here; explicit cmd requests reject those
    arguments, and automatic Windows output gives PowerShell guidance instead.
    """
    if target_shell is None:
        if sys.platform != "win32":
            return pip_install_command(requirement, target_shell="posix")
        powershell = pip_install_command(requirement, target_shell="powershell")
        try:
            cmd = pip_install_command(requirement, target_shell="cmd")
        except ValueError:
            return (
                "PowerShell:\n  "
                + powershell
                + "\ncmd.exe: use PowerShell above for these argument characters."
            )
        return f"cmd.exe:\n  {cmd}\nPowerShell:\n  {powershell}"
    if target_shell == "posix":
        return shlex.join([sys.executable, "-m", "pip", "install", requirement])
    if target_shell == "powershell":
        executable = sys.executable.replace("'", "''")
        package = requirement.replace("'", "''")
        return f"& '{executable}' -m pip install '{package}'"
    if target_shell == "cmd":
        if any(character in sys.executable + requirement for character in '\r\n"%!'):
            raise ValueError(
                "Use PowerShell for arguments containing quotes, %, !, or line breaks."
            )
        return f'"{sys.executable}" -m pip install "{requirement}"'
    raise ValueError(f"Unsupported installation shell: {target_shell}")


def get_help() -> str:
    """Render CLI help with installation commands for the current platform."""
    return _HELP.format(
        gui_install=textwrap.indent(pip_install_command("textual>=0.70.0"), "  "),
        xlsx_install=textwrap.indent(pip_install_command("openpyxl>=3.1"), "  "),
        pdf_install=textwrap.indent(pip_install_command("fpdf2>=2.7"), "  "),
    )
