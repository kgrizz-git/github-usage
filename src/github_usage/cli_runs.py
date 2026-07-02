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
from .setup_workflow import DEFAULT_PROFILE_NAME, workflow_path

# launchd weekday: 0/7 = Sunday, 1 = Monday, …, 6 = Saturday (matches setup wizard).
_WEEKDAY_NAMES: dict[int, str] = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}
_WEEKDAY_PLURAL: dict[int, str] = {
    0: "Sundays",
    1: "Mondays",
    2: "Tuesdays",
    3: "Wednesdays",
    4: "Thursdays",
    5: "Fridays",
    6: "Saturdays",
    7: "Sundays",
}

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


def _weekday_name(weekday: int) -> str:
    """Return the English weekday name for a launchd ``weekday`` value."""
    return _WEEKDAY_NAMES.get(weekday, f"weekday {weekday}")


def _describe_dow_field(field: str) -> str | None:
    """Return a human phrase for a cron day-of-week field, or ``None`` if unsupported."""
    if field.isdigit():
        return _WEEKDAY_PLURAL.get(int(field))
    if "," in field:
        names = [_WEEKDAY_PLURAL.get(int(part)) for part in field.split(",") if part.isdigit()]
        if names and all(names):
            if len(names) == 1:
                return names[0]
            return ", ".join(names[:-1]) + f", and {names[-1]}"
    if "-" in field and not field.startswith("*/"):
        start, end = field.split("-", 1)
        if start.isdigit() and end.isdigit():
            start_name = _WEEKDAY_NAMES.get(int(start), start)
            end_name = _WEEKDAY_NAMES.get(int(end), end)
            return f"{start_name} through {end_name}"
    return None


def describe_cron_human(expr: str) -> str | None:
    """Return a short human description for common 5-field GitHub Actions cron expressions.

    GitHub Actions evaluates cron in UTC. Only simple fixed minute/hour patterns with
    ``*`` wildcards for month (and usually day-of-month) are translated; complex
    expressions return ``None`` so callers can show the raw cron only.
    """
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute_s, hour_s, dom_s, month_s, dow_s = parts
    if month_s != "*" or not minute_s.isdigit() or not hour_s.isdigit():
        return None

    minute, hour = int(minute_s), int(hour_s)
    time_str = f"{hour:02d}:{minute:02d}"

    if dom_s == "*" and dow_s == "*":
        return f"Daily at {time_str} UTC"

    if dom_s == "*" and dow_s != "*":
        dow_desc = _describe_dow_field(dow_s)
        if dow_desc:
            return f"{dow_desc} at {time_str} UTC"

    if dom_s.isdigit() and dow_s == "*":
        return f"Day {int(dom_s)} of each month at {time_str} UTC"

    return None


def _describe_profile(name: str) -> str:
    """Return a short parenthetical explaining a profile label."""
    if name == DEFAULT_PROFILE_NAME:
        return "primary report profile → .github/workflows/email-report.yml"
    if name == "(legacy)":
        return "pre-multi-profile macOS LaunchAgent"
    if name == UNCONFIGURED:
        return "workflow on disk with no matching config.toml profile"
    return f"named report profile → .github/workflows/email-report-{name}.yml"


def _format_schedule(row: dict) -> str:
    """Return a human-readable schedule string for a run row."""
    schedule = row.get("schedule")
    if row.get("source") == "launchd":
        if isinstance(schedule, dict) and schedule:
            weekday = int(schedule.get("weekday", 1))
            hour = int(schedule.get("hour", 0))
            minute = int(schedule.get("minute", 0))
            return f"{_weekday_name(weekday)} {hour:02d}:{minute:02d} local time"
        return "(unknown)"
    # github_actions schedules are cron expressions, always evaluated in UTC.
    if schedule:
        human = describe_cron_human(str(schedule))
        if human:
            return f"{human} (cron: {schedule})"
        return f"cron {schedule} UTC (minute hour day-of-month month day-of-week)"
    return "(no cron in workflow)"


def _print_runs(rows: list[dict]) -> None:
    """Print the configured runs in a compact, human-readable form."""
    if not rows:
        print("No configured runs found.")
        return
    print("Configured runs (local config.toml profiles + .github/workflows/email-report*.yml):")
    print(
        "  Each profile can schedule email reports twice: launchd (macOS, local time) "
        "and github_actions (GitHub cron, UTC)."
    )
    print(
        f'  Profile name "{DEFAULT_PROFILE_NAME}" is the primary report configuration; '
        "additional names come from [[reports]] in config.toml."
    )
    for row in rows:
        profile = row["profile"]
        print(
            f"  [{row['active']}] {profile} ({_describe_profile(profile)}) · "
            f"{row['source']} · {_format_schedule(row)}"
        )
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

    # --no-fetch is only meaningful with --diff; reject it as a user error
    # if --diff isn't set. Must run before the diff/regular split because
    # the regular path doesn't use --no-fetch.
    if args.no_fetch and not args.diff:
        from . import cli_runs_diff

        print(cli_runs_diff.ERR_NO_FETCH_WITHOUT_DIFF, file=__import__("sys").stderr)
        return 1

    root = repo_root()

    if args.diff:
        return _run_diff(args, root)

    paths = SetupPaths.from_root(root)
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


def _run_diff(args, root: Path) -> int:
    """Run the ``--diff`` path: a per-file drift report vs. the remote default branch.

    Replaces the ``list_local_runs()`` path entirely when ``--diff`` is set.
    The output is always either a JSON object (``--json``) or a compact
    text table; the regular ``runs`` row shape is never emitted in this
    mode.
    """
    import os
    import sys

    from . import cli_runs_diff

    # 0. Early environment checks: fail fast, fail clearly.
    prereq_err = cli_runs_diff.check_prerequisites(root)
    if prereq_err is not None:
        print(prereq_err, file=sys.stderr)
        return 1

    # 1. Constraint checks (argparse can't enforce "valid only with").
    if args.owner is not None or args.repo is not None:
        print(cli_runs_diff.ERR_OWNER_REPO_WITH_DIFF, file=sys.stderr)
        return 1

    skip_fetch = args.no_fetch or os.environ.get("GITHUB_USAGE_SKIP_FETCH") == "1"
    candidate_path, early_exit = _resolve_diff_profile(args, root, skip_fetch)
    if early_exit is not None:
        return early_exit

    # 2. Pre-classify_drift setup. Ordering matters: fetch first so the
    #    default-branch resolver sees fresh refs on a first run.
    remote = cli_runs_diff.resolve_remote_name(root)
    fetched, _using_cached_ref_from_fetch = cli_runs_diff.fetch_remote(
        root, remote, skip_fetch=skip_fetch, env=cli_runs_diff.GIT_ENV
    )
    default_branch = cli_runs_diff.resolve_default_branch(root, remote)
    using_cached_ref = (not fetched) and (default_branch is not None)

    rows = cli_runs_diff.classify_drift(
        root,
        remote,
        default_branch,
        candidate_path=candidate_path,
    )

    if (not fetched) and default_branch and not skip_fetch:
        print(
            cli_runs_diff.FETCH_FALLBACK_WARNING_TEMPLATE.format(
                remote=remote, default_branch=default_branch
            ),
            file=sys.stderr,
        )

    print(
        cli_runs_diff.render_drift(
            rows,
            remote=remote,
            default_branch=default_branch,
            fetched=fetched,
            using_cached_ref=using_cached_ref,
            skipped_fetch=skip_fetch,
            as_json=args.json,
        )
    )
    return 0


def _resolve_diff_profile(args, root: Path, skip_fetch: bool) -> tuple[Path | None, int | None]:
    """Resolve ``--profile`` for the diff path.

    Returns ``(candidate_path, None)`` for a normal profile (or no
    profile at all). Returns ``(None, exit_code)`` for early-exit
    conditions (unknown profile, malformed config, profile with no
    GitHub Actions workflow file).
    """
    from . import cli_runs_diff

    if not args.profile:
        return None, None

    paths = SetupPaths.from_root(root)
    try:
        config = load_config(paths.config_file)
    except tomllib.TOMLDecodeError as exc:
        print(f"Error: Failed to parse config.toml: {exc}")
        return None, 1
    except (ValueError, KeyError) as exc:
        print(f"Error: Invalid config.toml: {exc}")
        return None, 1

    try:
        find_profile(config, args.profile)
    except KeyError:
        print(cli_runs_diff.ERR_PROFILE_NOT_FOUND_TEMPLATE.format(name=args.profile))
        return None, 1

    wf = workflow_path(root, args.profile)
    if not wf.is_file():
        print(
            cli_runs_diff.NO_GA_WORKFLOW_NOTICE_TEMPLATE.format(name=args.profile),
            file=__import__("sys").stderr,
        )
        # Render an empty diff so the output shape is consistent.
        print(
            cli_runs_diff.render_drift(
                [],
                remote="",
                default_branch=None,
                fetched=False,
                using_cached_ref=False,
                skipped_fetch=skip_fetch,
                as_json=args.json,
            )
        )
        return None, 0
    return wf, None
