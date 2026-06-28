"""Implementation of the ``github-usage runs`` subcommand.

Overview:
    Provides a lightweight, non-interactive, read-only view of every currently
    configured scheduled/automated run for this repository. It consolidates two
    sources of run configuration:

      1. ``config.toml`` profiles (parsed via ``setup_config.load_config``) — each
         profile contributes a ``launchd`` schedule row and a ``github_actions``
         (cron) row.
      2. On-disk ``.github/workflows/email-report*.yml`` files — any workflow file
         that does not correspond to a configured profile is surfaced as a
         ``<unconfigured>`` (stray) row.

    With ``--api`` the command additionally queries the GitHub Actions API for the
    latest run timestamp and conclusion of each matching workflow.

Inputs:
    Command-line arguments parsed by ``cli_parsers._runs_parser`` — ``--profile``,
    ``--json``, ``--api``, ``--owner``, ``--repo``. Local config/files under the
    repository root. Optionally a GitHub token (for ``--api``).

Outputs:
    Human-readable text (default) or structured JSON (``--json``) on stdout, plus a
    process exit code (0 on success, 1 on user-facing errors).

Requirements:
    Standard library only for the offline path. ``--api`` relies on the project's
    ``GitHubAPI`` client and token resolution (``auth.resolve_token``).
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

from .setup_config import SetupPaths, find_profile, load_config, repo_root
from .setup_launchd import launch_agent_dest, legacy_launch_agent_dest
from .setup_workflow import workflow_path

# Regex extracting the owner/repo pair from common GitHub remote URL forms:
#   https://github.com/owner/repo.git
#   git@github.com:owner/repo.git
#   ssh://git@github.com/owner/repo
# group 1 = owner, group 2 = repo (trailing ".git" stripped).
_REMOTE_URL_RE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$")

# Regex extracting the first cron expression from a workflow file. Supports both
# quoted (template-generated) and unquoted (hand-edited) forms.
_CRON_RE = re.compile(r"-\s+cron:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", re.MULTILINE)

# Sentinel profile label used for on-disk workflows with no matching config profile.
UNCONFIGURED = "<unconfigured>"


class RunsApiError(Exception):
    """Raised when ``--api`` enrichment cannot proceed (no token, unresolvable owner/repo)."""


def extract_first_cron_from_workflow(path: Path, fallback: str | None = None) -> str | None:
    """Extract the first cron schedule expression found in the workflow file.

    Supports both quoted (``'0 9 * * 1'``) and unquoted (``0 9 * * 1``) forms.
    Returns ``fallback`` if the file is missing or no cron line is found.
    """
    if not path.is_file():
        return fallback
    content = path.read_text(encoding="utf-8")
    match = _CRON_RE.search(content)
    if match:
        return match.group(1).strip()
    return fallback


def _launchd_row(name: str, profile: dict, paths: SetupPaths, is_macos: bool) -> dict:
    """Build a ``launchd`` run row for a single configured profile."""
    installed = launch_agent_dest(name).is_file()
    generated = paths.launchd_plist_for(name).is_file()
    if not is_macos:
        active = "unsupported"
    elif installed:
        active = "active"
    else:
        active = "inactive"
    notes = ""
    if generated and not installed:
        # The plist was written into the repo but never loaded into LaunchAgents.
        notes = "plist generated but not installed"
    return {
        "profile": name,
        "source": "launchd",
        "schedule": dict(profile.get("schedule", {})),
        "active": active,
        "notes": notes,
        "workflow_file": None,
        "api_last_run": None,
        "api_status": None,
    }


def _github_actions_row(name: str, profile: dict, paths: SetupPaths) -> dict:
    """Build a ``github_actions`` run row for a single configured profile."""
    wf_path = workflow_path(paths.root, name)
    ga = profile.get("github_actions", {})
    cron = extract_first_cron_from_workflow(wf_path, fallback=ga.get("cron"))
    active = "active" if wf_path.is_file() else "inactive"
    return {
        "profile": name,
        "source": "github_actions",
        "schedule": cron,
        "active": active,
        "notes": "",
        # Repo-relative POSIX path; used to match the GitHub API's workflow `path`.
        "workflow_file": wf_path.relative_to(paths.root).as_posix(),
        "api_last_run": None,
        "api_status": None,
    }


def _legacy_launchd_row() -> dict:
    """Build a row for the legacy single-profile LaunchAgent plist."""
    return {
        "profile": "(legacy)",
        "source": "launchd",
        "schedule": None,
        "active": "active",
        "notes": "legacy single-profile LaunchAgent installed",
        "workflow_file": None,
        "api_last_run": None,
        "api_status": None,
    }


def _stray_workflow_rows(config: dict, paths: SetupPaths) -> list[dict]:
    """Detect on-disk workflow files that do not match any configured profile.

    The glob ``email-report*.yml`` also matches the *configured* files (the default
    profile maps to ``email-report.yml`` and named profiles to
    ``email-report-{name}.yml``), so each globbed file is de-duped against the set of
    resolved configured workflow paths before being treated as stray.
    """
    workflows_dir = paths.root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []
    configured = {
        workflow_path(paths.root, p["name"]).resolve() for p in (config.get("profiles") or [])
    }
    rows: list[dict] = []
    for wf in sorted(workflows_dir.glob("email-report*.yml")):
        if wf.resolve() in configured:
            continue
        rel = wf.relative_to(paths.root).as_posix()
        rows.append(
            {
                "profile": UNCONFIGURED,
                "source": "github_actions",
                "schedule": extract_first_cron_from_workflow(wf, fallback=None),
                "active": "active",
                "notes": f"unconfigured workflow: {rel}",
                "workflow_file": rel,
                "api_last_run": None,
                "api_status": None,
            }
        )
    return rows


def list_local_runs(
    config: dict, paths: SetupPaths, profile_filter: str | None = None
) -> list[dict]:
    """Return one row per configured run, read entirely from local config/files.

    When ``profile_filter`` is given it is validated via ``find_profile`` (which
    raises ``KeyError`` for an unknown name); iteration is then restricted to that
    profile and stray on-disk workflow detection is skipped.
    """
    if profile_filter is not None:
        # Raises KeyError for an unknown profile; translated to a message in main().
        profiles = [find_profile(config, profile_filter)]
    else:
        profiles = config.get("profiles") or []

    is_macos = sys.platform == "darwin"
    rows: list[dict] = []
    for profile in profiles:
        name = profile["name"]
        rows.append(_launchd_row(name, profile, paths, is_macos))
        rows.append(_github_actions_row(name, profile, paths))

    if profile_filter is None:
        if is_macos and legacy_launch_agent_dest().is_file():
            rows.append(_legacy_launchd_row())
        rows.extend(_stray_workflow_rows(config, paths))

    return rows


def _resolve_owner_repo(args) -> tuple[str, str]:
    """Resolve the GitHub owner/repo for ``--api`` queries.

    Uses explicit ``--owner``/``--repo`` overrides when provided, otherwise parses
    the local ``remote.origin.url``. Raises ``RunsApiError`` if neither yields both
    an owner and a repo.
    """
    owner, repo = args.owner, args.repo
    if owner and repo:
        return owner, repo

    url = ""
    try:
        result = subprocess.run(  # nosec
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        url = result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        url = ""

    match = _REMOTE_URL_RE.search(url)
    if match:
        owner = owner or match.group(1)
        repo = repo or match.group(2)

    if not owner or not repo:
        raise RunsApiError(
            "Error: Could not resolve GitHub owner/repo. "
            "Use --owner and --repo, or run inside a git repo with a github.com remote."
        )
    return owner, repo


def _enrich_with_api(rows: list[dict], args) -> list[dict]:
    """Augment ``github_actions`` rows in-place with the latest GitHub Actions run.

    Sets ``api_last_run`` (ISO 8601 ``created_at`` of the most recent run) and
    ``api_status`` (the run's ``conclusion``) for each row whose ``workflow_file``
    matches a workflow returned by the API. Rows without a matching workflow (and all
    ``launchd`` rows) are left untouched. Raises ``RunsApiError`` on missing token or
    unresolvable owner/repo.
    """
    from .auth import resolve_token

    # Explicit empty argv prevents resolve_token from reading sys.argv and consuming
    # this subcommand's own flags (matches the established pattern in cli.py).
    token = resolve_token(argv=[])
    if not token:
        raise RunsApiError(
            "Error: No GitHub token found. Please set GITHUB_TOKEN or authenticate via gh CLI."
        )

    owner, repo = _resolve_owner_repo(args)

    from .api import GitHubAPI

    client = GitHubAPI(token)
    listing = client.request("GET", f"/repos/{owner}/{repo}/actions/workflows")
    # Map each workflow's repo-relative path to its GitHub-assigned id.
    path_to_id = {
        wf.get("path"): wf.get("id")
        for wf in (listing.get("workflows") or [])
        if wf.get("path") and wf.get("id") is not None
    }

    for row in rows:
        if row.get("source") != "github_actions":
            continue
        workflow_file = row.get("workflow_file")
        wf_id = path_to_id.get(workflow_file)
        if wf_id is None:
            continue
        runs = client.request(
            "GET",
            f"/repos/{owner}/{repo}/actions/workflows/{wf_id}/runs",
            params={"per_page": 1},
        )
        run_list = runs.get("workflow_runs") or []
        if run_list:
            latest = run_list[0]
            row["api_last_run"] = latest.get("created_at")
            row["api_status"] = latest.get("conclusion")
    return rows


def _format_schedule(row: dict) -> str:
    """Return a human-readable schedule string for a run row."""
    schedule = row.get("schedule")
    if row.get("source") == "launchd":
        if isinstance(schedule, dict) and schedule:
            return (
                f"weekday {schedule.get('weekday')} "
                f"{int(schedule.get('hour', 0)):02d}:{int(schedule.get('minute', 0)):02d} local"
            )
        return "(unknown)"
    # github_actions schedules are cron expressions, always evaluated in UTC.
    if schedule:
        return f"{schedule} UTC"
    return "(no cron)"


def _print_runs(rows: list[dict]) -> None:
    """Print the configured runs in a compact, human-readable form."""
    if not rows:
        print("No configured runs found.")
        return
    print("Configured runs:")
    for row in rows:
        print(f"  [{row['active']}] {row['profile']} · {row['source']} · {_format_schedule(row)}")
        if row.get("notes"):
            print(f"      note: {row['notes']}")
        if row.get("api_last_run") or row.get("api_status"):
            last = row.get("api_last_run") or "n/a"
            status = row.get("api_status") or "n/a"
            print(f"      last run: {last} ({status})")


def main(argv: Sequence[str]) -> int:
    """Entry point for ``github-usage runs``."""
    from .cli_parsers import _runs_parser

    parser = _runs_parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return int(exc.code or 0)

    paths = SetupPaths.from_root(repo_root())
    no_config = not paths.config_file.is_file()
    try:
        config = load_config(paths.config_file)
    except tomllib.TOMLDecodeError as exc:
        print(f"Error: Failed to parse config.toml: {exc}")
        return 1
    except (ValueError, KeyError) as exc:
        # load_report_profiles raises ValueError (duplicate profile name) or
        # KeyError (reports entry missing 'name') on a structurally invalid config.
        print(f"Error: Invalid config.toml: {exc}")
        return 1

    try:
        rows = list_local_runs(config, paths, profile_filter=args.profile)
    except KeyError:
        # find_profile raises KeyError when --profile names an unknown profile.
        print(f"Error: Profile '{args.profile}' not found in configuration.")
        return 1

    if args.api:
        try:
            rows = _enrich_with_api(rows, args)
        except RunsApiError as exc:
            print(str(exc))
            return 1

    if no_config:
        # load_config always returns a synthetic profile, so `rows` is never empty
        # even without a config file — a `not rows` guard would be unreachable.
        print("Warning: No config.toml found — showing defaults.")

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        _print_runs(rows)
    return 0
