> **Status:** COMPLETE

**Date:** 2026-06-28

> **Done (2026-06-28):** Implemented all four phases. Added `cli_runs.py` (`list_local_runs`,
> `extract_first_cron_from_workflow`, `_resolve_owner_repo`, `_enrich_with_api`, `RunsApiError`,
> `_print_runs`, `main`), `_runs_parser()` in `cli_parsers.py`, routing + HELP in `cli.py`, and a
> `runs)` case in `start.sh`. Added 32 tests in `tests/test_cli_runs.py`; extended `scripts/smoke`;
> documented in `README.md`; added a CHANGELOG `Added` entry; removed the `TO_DO.md` item.
> `scripts/check`, `scripts/smoke`, and `scripts/docs-check` all pass.
> **Deviation:** each row carries an extra `workflow_file` field (repo-relative path) so
> `_enrich_with_api` can match the GitHub API's workflow `path` without re-deriving paths; this keeps
> the documented `_enrich_with_api(rows, args)` signature unchanged and is reflected in JSON output.

> **Review note (2026-06-28, second pass):** Verified all referenced functions/signatures against the
> codebase (`SetupPaths.from_root`, `load_config`, `find_profile`, `repo_root`, `launch_agent_dest`,
> `legacy_launch_agent_dest`, `workflow_path`, `resolve_token(argv=[])`, `GitHubAPI.request`). Corrected
> six control-flow/error-handling gaps: (1) API failures now propagate an exit code via a dedicated
> `RunsApiError`; (2) invalid `--profile` is now caught in `main()`; (3) `load_config` `ValueError`/`KeyError`
> (duplicate/missing profile name) are now handled; (4) stray-workflow detection now de-dupes against
> configured profile workflow paths; (5) stray detection is skipped when `--profile` is set; (6) Phase 3
> workflow matching now compares repo-relative paths.

## Objective

Add a `github-usage runs` subcommand that displays all currently configured scheduled/automated runs — both local config entries (launchd schedules, GitHub Actions workflow cron expressions) and the actual GitHub Actions workflows detected in the repository. This addresses the TO_DO item: "Add support for viewing currently configured runs in the GitHub config (e.g., GitHub Actions schedules)."

## Current State

The project stores run configuration in two places:

1. **`config.toml`** — managed by `setup_config.py`:
   - On disk the file uses a `[[reports]]` array of tables; each entry carries `[schedule]`, `[github_actions]`, and `[email_report]` sub-tables.
   - `load_config()` normalises this into an in-memory dict that additionally exposes a synthetic `"profiles"` key (a list of dicts). Code that reads config must call `load_config()` first — never access `config["profiles"]` on a raw `tomllib` dict.
   - Per-profile: `[reports.schedule]` and `[reports.github_actions]` on disk; `profile["schedule"]` and `profile["github_actions"]` in-memory.

2. **`.github/workflows/email-report*.yml`** — rendered by `setup_workflow.py` from a template, containing a `schedule:` trigger with a cron expression.

There is no existing CLI command to view these configurations in a consolidated way. Users must manually inspect `config.toml` and `.github/workflows/` files, or run `setup --status` (which shows paths but not the schedule details in a queryable format).

The `setup --status` command (in `setup_config.py:~420-460`) already prints schedule and workflow status for each profile, but it requires an interactive TTY and is tied to the setup wizard flow. The goal here is a lightweight, non-interactive read-only view.

## Definition of Done

- A new CLI subcommand `github-usage runs` that prints a summary of all configured runs.
- The command reads from `config.toml` (via `SetupPaths.from_root().config_file` and existing `load_config`).
- No live network requests are required by default; offline operation reads only local config/files.
- The optional `--api` flag queries the GitHub API for workflow status (see Phase 3).
- `ruff check` and `ruff format --check` pass.
- `./scripts/check` and `./scripts/docs-check` pass.
- `scripts/smoke` includes subcommand routing checks and passes.
- A `CHANGELOG.md` entry is added under `[Unreleased] → ### Added`.
- The matching item is removed from `TO_DO.md` upon completion.
- `README.md` is updated to document the new `runs` subcommand (add it to the **Commands** section alongside `setup`, `email-report`, and `report`).
- `start.sh` is updated to route the new `runs` command.

## Proposed Implementation Plan

### Phase 1: CLI Subcommand Skeleton & Routing

1. Add routing for the `runs` subcommand in `src/github_usage/cli.py:main()`. Insert it **before** the `return _run_legacy_report(args)` fallthrough, as a sibling block alongside the existing `email-report` and `setup` checks. Without this placement, `runs` will be silently consumed by the legacy handler as a bare token and never dispatched.
   ```python
   if args and args[0] == "runs":
       from .cli_runs import main as runs_main
       return runs_main(args[1:])
   ```

2. Define `_runs_parser()` in `src/github_usage/cli_parsers.py`:
   ```python
   def _runs_parser() -> argparse.ArgumentParser:
       parser = argparse.ArgumentParser(
           prog="github-usage runs",
           description="View all currently configured scheduled runs (launchd and GitHub Actions).",
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
   ```

3. Update the `HELP` string in `src/github_usage/cli.py` to document the new `runs` subcommand.

4. Update `start.sh` to include `runs` in the help text and route the command. The new `runs)` case must be inserted **before** the `*)` wildcard catch-all (which currently exits with an error for unknown commands).
   ```bash
   # Under the heredoc help block — add to the Commands list:
   runs          View all currently configured scheduled runs.

   # Under case — insert before the *) wildcard:
   runs)
     shift
     exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage runs "$@"
     ;;
   ```

### Phase 2: Local Config Parsing & Display (`cli_runs.py`)

Create a new file `src/github_usage/cli_runs.py` which implements the subcommand:

0. **Required Imports:**
   `cli_runs.py` must include at least the following imports:
   ```python
   from __future__ import annotations

   import json
   import re
   import sys
   import tomllib
   from collections.abc import Sequence
   from pathlib import Path

   from .setup_config import SetupPaths, find_profile, load_config, repo_root
   from .setup_launchd import launch_agent_dest, legacy_launch_agent_dest
   from .setup_workflow import workflow_path
   ```
   Additional imports (`subprocess`, `.auth`, `.api`) are added in Phase 3 when `--api` is implemented.

1. **`main()` Entry Point:**
   Define the public entry point that Phase 1 imports. Note the three distinct error
   guards — they correspond to real exceptions raised by the helpers (verified against the code):
   - `tomllib.TOMLDecodeError` from `load_config()` on malformed TOML syntax.
   - `ValueError` / `KeyError` from `load_report_profiles()` (called inside `load_config()`) on a
     structurally invalid config — a duplicate profile name raises `ValueError`; a `[[reports]]`
     entry missing its `name` raises `KeyError`.
   - `KeyError` from `find_profile()` (called inside `list_local_runs()`) when `--profile` names a
     profile that does not exist.
   ```python
   def main(argv: Sequence[str]) -> int:
       """Entry point for `github-usage runs`."""
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
               rows = _enrich_with_api(rows, args)  # defined in Phase 3
           except RunsApiError as exc:
               # Raised for missing token or unresolvable owner/repo (see Phase 3).
               print(str(exc))
               return 1

       if no_config:
           # Warning placed here (not inside `if args.api`) because load_config always
           # returns a synthetic profile, so `rows` is never empty even without a config
           # file — the `not rows` guard would be unreachable.
           print("Warning: No config.toml found — showing defaults.")

       if args.json:
           print(json.dumps(rows, indent=2))
       else:
           _print_runs(rows)
       return 0
   ```

2. **Config Path Resolution & Parsing:**
   - Resolve config paths using `SetupPaths.from_root()`.
   - `tomllib.TOMLDecodeError` propagates from `load_config()` without being caught internally (handled in `main()` above).
   - If `config.toml` does not exist, `load_config()` returns a synthetic default profile (it does not raise).

3. **Core Data Contract:**
   Define the function:
   ```python
   def list_local_runs(config: dict, paths: SetupPaths, profile_filter: str | None = None) -> list[dict]:
       ...
   ```
   When `profile_filter` is not `None`, validate it by calling `find_profile(config, profile_filter)`
   first and let the resulting `KeyError` propagate (caught and translated in `main()`); then restrict
   iteration to that single profile and **skip** stray on-disk workflow detection (step 6), since the
   caller asked for one specific configured profile.

   Each dict in the returned list conforms to this schema:
   - `profile`: profile name (`str`)
   - `source`: `"launchd" | "github_actions"` (`str`). **Note:** the original design had a third `"workflow"` source type for physical on-disk files, but this was removed because `github_actions` already uses `workflow_path()` to check the physical file and the two sources would refer to the same object. If a `config.toml` profile has a `github_actions` block, one row is emitted with `source="github_actions"` regardless of whether the file exists (the `active` field reflects presence). There is no separate `"workflow"` source.
   - `schedule`: parsed schedule dictionary `{"weekday": int, "hour": int, "minute": int}` (for `launchd`) or cron expression string (`str`) (for `github_actions`)
   - `active`: one of the string literals `"active"`, `"inactive"`, or `"unsupported"` (`str`). Using a uniform string enum (rather than `bool | str`) keeps JSON output consistent and avoids mixed-type serialization issues.
   - `notes`: additional info/details (`str`)
   - `api_last_run`: ISO 8601 timestamp of the last GitHub Actions run for this workflow (`str | None`). Always `None` unless `--api` is passed; added by `_enrich_with_api()` in Phase 3.
   - `api_status`: conclusion status of the last run, e.g. `"success"`, `"failure"`, `"cancelled"` (`str | None`). Always `None` unless `--api` is passed.

4. **Active State Semantics & Platform Gating:**
   - **`launchd` (LaunchAgent schedules):**
     - Gate verification behind `sys.platform == "darwin"`.
     - On macOS, `active` is `"active"` if the **installed** plist exists in `~/Library/LaunchAgents/` (`launch_agent_dest(profile_name).is_file()`); otherwise `"inactive"`.
     - On non-macOS, set `active` to `"unsupported"`.
   - **`github_actions` (GitHub Actions config in `config.toml`):**
     - `active` is `"active"` if the physical workflow file (`workflow_path(root, profile_name)`) exists on disk; otherwise `"inactive"`.
     - There is no separate `"workflow"` source — the physical file check is already embedded here. Emitting a second row for the same physical file would duplicate output.

5. **LaunchAgent & Legacy Plist Verification:**
   There are two distinct plist locations — do not conflate them:
   - **Generated/staged** (inside the repo): `paths.launchd_plist_for(profile_name)` → `.github-usage/launchd/com.github.github-usage.email-report.{name}.plist`. This file being present means a plist has been written but not necessarily loaded.
   - **Installed/active** (in LaunchAgents): `launch_agent_dest(profile_name)` → `~/Library/LaunchAgents/com.github.github-usage.email-report.{name}.plist`. This is the authoritative `active` signal.

   Verification logic:
   - Use `setup_launchd.launch_agent_dest(profile_name)` to check the installed path (`active` field).
   - Use `setup_launchd.legacy_launch_agent_dest()` for the legacy single-profile plist (`com.github.github-usage.email-report.plist`). If both legacy and default profile plists are found, report both as separate rows.
   - If the generated plist exists but the installed plist does not, note this in the `notes` field: `"plist generated but not installed"`.

6. **Avoid Profile Double-Counting; Detect Stray On-Disk Workflows:**
   - Iterate over `config["profiles"]` returned by `load_config()` (synthetic in-memory key; on-disk TOML key is `reports`). Do not iterate over top-level keys like `config["schedule"]` or `config["github_actions"]` to avoid double-counting.
   - **Additionally** (only when `profile_filter is None` — see step 3), glob `.github/workflows/email-report*.yml` in the repo root to detect on-disk workflow files that do not correspond to any profile in `config.toml`. These represent workflows checked in by others, or configs that have drifted from the local `config.toml`.
   - **Critical de-dup:** the glob `email-report*.yml` matches the *configured* files too — the default profile maps to `email-report.yml` and named profiles to `email-report-{name}.yml` (see `workflow_path()`). Before treating a globbed file as "stray", build the set of resolved configured paths `{workflow_path(paths.root, p["name"]).resolve() for p in config["profiles"]}` and skip any globbed file already in that set. Only files **not** in the configured set are stray. (The `.yml.template` source is not matched by `*.yml`, so it is naturally excluded.)
   - For each genuinely stray file:
     - Emit a row with `profile="<unconfigured>"`, `source="github_actions"`, `active="active"`, and `schedule` set to the extracted cron string (or `None` if extraction fails).
     - Include the file path in the `notes` field.
   - This satisfies the objective of showing "the actual GitHub Actions workflows detected in the repository".

7. **Workflow Cron Extraction (No Third-Party Dependency):**
   - Extract the cron expression from on-disk `.github/workflows/email-report*.yml` files. The regex must support both quoted (template-generated) and unquoted (manually edited) cron expressions:
     ```python
     def extract_first_cron_from_workflow(path: Path, fallback: str | None = None) -> str | None:
         """Extract the first cron schedule expression found in the workflow file.

         Supports both quoted (`'0 9 * * 1'`) and unquoted (`0 9 * * 1`) forms.
         Returns `fallback` if the file is missing or no cron line is found.
         """
         if not path.is_file():
             return fallback
         content = path.read_text(encoding="utf-8")
         match = re.search(r"-\s+cron:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", content, re.MULTILINE)
         if match:
             return match.group(1).strip()
         return fallback
     ```
   - The `fallback` parameter should receive the `cron` value from the profile's `github_actions` config block (if any), so callers always get a schedule value even when the physical file is absent or the cron line cannot be parsed.
   - *Note:* This retrieves the first match, which fits the template design of single cron schedules per file.

8. **Profile Exception Handling:**
   - `list_local_runs()` calls `find_profile(config, profile_filter)` when a filter is given and lets
     the `KeyError` propagate. `main()` (step 1) catches it and prints
     `Error: Profile '{args.profile}' not found in configuration.`, returning exit code 1.
   - Do **not** swallow the `KeyError` inside `list_local_runs()`; keeping the translation in `main()`
     keeps the data function pure (it either returns rows or raises) and avoids returning a sentinel.

9. **Output Formatting:**
   - Print human-readable output (default format) or JSON output (if `--json` is specified).
   - Ensure local time schedules show local time format, and GitHub Actions cron displays UTC format.

### Phase 3: Owner/Repo Resolution & API Query (`--api` flag)

When `--api` is passed:

0. **Error signaling contract:**
   `_enrich_with_api()` is typed to return `list[dict]`, so it cannot also return an exit code. Define a
   dedicated exception at module scope so the failure paths below propagate cleanly to `main()` (which
   catches `RunsApiError`, prints the message, and returns 1 — see Phase 2 step 1):
   ```python
   class RunsApiError(Exception):
       """Raised when --api enrichment cannot proceed (no token, unresolvable owner/repo)."""
   ```
   Every "print an error and exit with code 1" instruction in this phase means `raise RunsApiError(<message>)`.

1. **Token Verification:**
   - Resolve the GitHub token by importing `resolve_token` from `.auth` (not from `.cli`).
   - Call it as `resolve_token(argv=[])` (explicitly passing an empty list) to prevent it from reading `sys.argv[1:]` and consuming the `runs` subcommand's own flags. This matches the established pattern in `cli.py:228`.
   - If `resolve_token(argv=[])` returns `None`, raise
     `RunsApiError("Error: No GitHub token found. Please set GITHUB_TOKEN or authenticate via gh CLI.")`.

2. **Resolve Owner/Repo:**
   - Determine the owner and repository using a dedicated resolver:
     - Use `--owner` and `--repo` argument overrides if provided.
     - Otherwise, parse the local repository's remote URL using `subprocess.run` with `check=False`, `capture_output=True`, `text=True`, and a short timeout:
        ```python
        result = subprocess.run(  # nosec
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        url = result.stdout.strip() if result.returncode == 0 else ""
        ```
     - Extract owner and repo from SSH/HTTPS formats using regex:
        ```python
        # Matches:
        # https://github.com/owner/repo.git
        # git@github.com:owner/repo.git
        # ssh://git@github.com/owner/repo
        # group 1 = owner, group 2 = repo
        re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
        ```
     - If resolution fails, raise `RunsApiError(...)` with a descriptive message (caught in `main()`).

3. **Query GitHub API & Merge Results:**
   Implement as `_enrich_with_api(rows: list[dict], args) -> list[dict]`:
   - Initialize `GitHubAPI(token)` client and call `client.request("GET", path, params=...)` (the client's `request()` method returns parsed JSON; see `api.py`).
   - Query `GET /repos/{owner}/{repo}/actions/workflows` to enumerate workflows and find their GitHub-assigned IDs by matching each workflow's `path` field against the **repo-relative POSIX paths** of the local workflows. The API returns `path` values like `.github/workflows/email-report.yml`; compute the comparison key for a local file as `workflow_path(paths.root, name).relative_to(paths.root).as_posix()` (or equivalently for stray files, the globbed path relative to the repo root). Do not compare against absolute paths or bare basenames.
   - For each matched workflow, use the **workflow-specific runs endpoint** to fetch only the latest run without pagination overhead:
     ```
     GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs?per_page=1
     ```
     Do **not** use the repository-wide `GET /repos/{owner}/{repo}/actions/runs` — that endpoint returns runs for all workflows (CI, linters, etc.) and may require expensive pagination to find the email-report run.
   - **Merge strategy:** mutate the existing row dicts in-place by setting `api_last_run` (ISO 8601 `created_at` of the most recent run, or `None` if no runs exist) and `api_status` (the run's `conclusion` field, or `None`). Do not emit additional rows.
   - Return the mutated rows list.
   - For `launchd` rows (which have no GitHub Actions workflow), leave `api_last_run` and `api_status` as `None`.

### Phase 4: Test Coverage & Verification

1. **Unit Tests:**
   - Implement comprehensive tests in `tests/test_cli_runs.py`:
     - Test `list_local_runs()` with a legacy config structure (no `config.toml` — synthetic defaults).
     - Test `list_local_runs()` with a multi-profile `reports`-keyed config.
     - Test profile filtering and error handling for missing profiles.
     - Test regex parsing of cron expressions from mock workflow files. Note: the cron regex matches only single- or double-quoted expressions — test both quote styles.
     - Test git remote parsing helpers with various URL formats (HTTPS, SSH, SSH-over-HTTPS, with/without `.git`, and repository names containing dots like `my.repo`).
     - Test launchd gating and non-macOS platform behavior (`active == "unsupported"`).
     - Test that generated-but-not-installed plist produces `notes == "plist generated but not installed"`.
     - Test config parsing error handling on corrupted TOML (verify exit code 1 and user-friendly message).
     - Test structurally-invalid config handling: a `[[reports]]` entry with a duplicate `name` (raises `ValueError`) and one missing `name` (raises `KeyError`) both produce exit code 1 with an `Invalid config.toml:` message rather than a traceback.
     - Test that `--profile <unknown>` produces exit code 1 with the `Profile '<unknown>' not found` message.
     - Test stray-workflow de-dup: a repo containing only the configured `email-report.yml` emits **no** `<unconfigured>` row, while an extra unconfigured `.github/workflows/email-report-orphan.yml` emits exactly one stray row.
     - Test that passing `--profile` suppresses stray-workflow detection entirely.
     - Test stdout formatting in both text and JSON modes; verify JSON `active` field is always a string (`"active"` / `"inactive"` / `"unsupported"`), never a boolean.
     - **`--api` path (all using mocks — no live network calls):**
       - Test that `resolve_token(argv=[])` is called (not `resolve_token()` bare), and that missing token exits with code 1.
       - Test mocked `GitHubAPI` calls for `GET /repos/{owner}/{repo}/actions/workflows` (workflow ID lookup) and `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs?per_page=1` (latest run fetch).
       - Test mocked `subprocess.run` for git remote URL resolution (HTTPS and SSH formats).
       - Test that `--owner`/`--repo` overrides bypass the git remote lookup.
       - Test that a missing token and an unresolvable owner/repo each raise `RunsApiError`, and that `main()` translates it into exit code 1 with the message printed (no traceback).
       - Test the absent-config warning under `--api`.

2. **Verification & Smoke Tests:**
   - Run `ruff check` and `ruff format --check`.
   - Update `scripts/smoke` to test the new `runs` routing:
     ```bash
     PYTHONPATH=src scripts/python -m github_usage runs --help
     ```
   - Ensure `scripts/check` and `scripts/docs-check` pass.
   - Update `README.md` to document `runs`.
   - Update `CHANGELOG.md` with the new feature under `[Unreleased]`.
   - Archive the plan after completion.
