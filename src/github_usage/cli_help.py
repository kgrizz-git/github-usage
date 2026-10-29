"""CLI help and shell-safe install commands for the running interpreter."""

from __future__ import annotations

import shlex
import sys

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
  {xlsx_install}   # XLSX
  {pdf_install}    # PDF
"""


def pip_install_command(requirement: str) -> str:
    """Return a POSIX-shell pip install command using this process's interpreter."""
    return shlex.join([sys.executable, "-m", "pip", "install", requirement])


def get_help() -> str:
    """Render CLI help with installation commands for the current interpreter."""
    return _HELP.format(
        gui_install=pip_install_command("textual>=0.70.0"),
        xlsx_install=pip_install_command("openpyxl>=3.1"),
        pdf_install=pip_install_command("fpdf2>=2.7"),
    )
