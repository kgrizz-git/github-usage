> **Status:** COMPLETE (merged in c34a025)

> **Done (2026-06-28):** All six phases implemented. New module
> `src/github_usage/cli_runs_diff.py` (576 lines, file-size warning
> is advisory), `cli_parsers.py` `--diff` / `--no-fetch` flags in a
> mutually exclusive group with `--api`, `cli_runs.py` early-return
> diff path with constraint / prereq / profile / setup checks, and
> `start.sh runs-diff` shortcut. 42 new tests in
> `tests/test_cli_runs_diff.py` and a `FakeGit` helper in
> `tests/_fakes.py` (response keys are argv lists without the
> leading `"git"` because the mocked layer is the `_run_git`
> wrapper, which is what prepends `"git"`). README "Checking for
> drift" subsection and CHANGELOG entry added. `scripts/check`,
> `scripts/smoke`, and `scripts/docs-check` all pass; full test
> suite (436 tests) is green.

**Date:** 2026-06-28

## Objective

Add a `runs --diff` flag (and a `start.sh runs-diff` shortcut) that reports
drift between the local working tree and the configured remote's default
branch for the files that define "configured runs" on GitHub — specifically
the tracked `.github/workflows/email-report*.yml` files. This complements the
existing `--api` flag, which only enriches local rows with the latest-run
timestamp; `--diff` answers a different question ("is what I have locally
what GitHub has?") without requiring a token.

This continues the work of the archived `view-configured-runs` plan
(`docs/superpowers/plans/archived/2026-06-28-view-configured-runs.md`) and the
follow-up doc-tightening commit that clarified the `runs` subcommand reflects
local state only.

## Current State

`github-usage runs` reports configured runs from three local sources:
`config.toml` profiles, on-disk `.github/workflows/email-report*.yml` files,
and `launchd` plists. The `--api` flag hits `GET /repos/{owner}/{repo}/actions/workflows`
and `GET /actions/workflows/{id}/runs` to attach the latest run timestamp and
conclusion — but it does not, and cannot, detect drift between local files and
what is on `origin`. Users currently have to run `git fetch && git diff
origin/main -- .github/workflows/ email-report` by hand, and they must remember
to fetch.

There is no existing `git`-backed drift view. The relevant paths are the
tracked `.github/workflows/email-report*.yml` files (rendered from the
template by `setup_workflow.py`). The local `.github-usage/config.toml` is
created by the setup wizard and is intentionally not pushed to GitHub, so
it has no remote counterpart and is out of scope for the drift view.

## Design Overview

- New `runs --diff` flag (no new subcommand); mutually exclusive with `--api`
  via `add_mutually_exclusive_group()`. `--no-fetch` and
  `GITHUB_USAGE_SKIP_FETCH=1` skip the fetch.
- Per-file classification: HEAD vs `<remote>/<default_branch>` blob hashes
  via `git ls-tree <ref> -- <path>`. Direction from three-dot `git diff` in
  all differing cases (handles additions and deletions); blob presence only
  picks the category name (`remote-only` vs `behind`).
- Remote files enumerated via
  `git ls-tree -r <remote>/<default_branch> -- .github/workflows/` filtered
  to the glob; union with local paths, all normalized to repo-relative POSIX.
- `--profile NAME` narrows to that profile's single workflow (via
  `workflow_path(repo_root, name)`); launchd-only profiles emit a notice
  and return `[]`.
- Fetch is a hint: a failed fetch falls back to the cached
  `<remote>/<default_branch>` ref with a stderr warning; rows degrade to
  `unknown` only when no cached ref exists.
- Robustness: `cwd=repo_root` on every subprocess call; missing `git`
  binary degrades to `unknown`; `git status --porcelain` parsed with
  column-based precedence for `MM`/`AM`/`MD`; paths normalized to
  repo-relative POSIX.
- JSON output:
  `{"kind": "diff", "default_branch", "remote", "fetched", "using_cached_ref",
  "skipped_fetch", "rows"}`. Categories: `in-sync`, `uncommitted`, `staged`,
  `untracked`, `ahead`, `behind`, `remote-only`, `diverged`, `unknown`.
- No token, no API, no new dependencies. `./start.sh runs-diff` is a thin
  alias for `./start.sh runs --diff`; `./start.sh runs` (no flag) keeps its
  current offline-only behavior.

## Definition of Done

- `runs --diff` produces a per-file row for every tracked workflow YAML,
  with a `drift` category and summary.
- Per-file classification via three-dot `git diff`; remote-only files
  enumerated from `git ls-tree -r`; `--profile` narrows scope;
  `--no-fetch` / `GITHUB_USAGE_SKIP_FETCH=1` skip fetch; a failed fetch
  falls back to the cached ref, and rows degrade to `unknown` only when
  no cached ref exists.
- `--diff` and `--api` mutually exclusive via argparse. Remote name
  resolved dynamically (`git config branch.<current>.remote` with
  `origin` fallback); default-branch resolver verifies each candidate
  with `git rev-parse --verify`.
- All subprocess calls use `cwd=repo_root`; missing `git` degrades
  gracefully. Paths normalized to repo-relative POSIX; `git status`
  parsed with column precedence.
- `start.sh runs-diff` ≡ `start.sh runs --diff`. `scripts/check`,
  `scripts/smoke`, `scripts/docs-check` pass.
- Unit tests (FakeGit, no live network/git) cover: all categories; the
  local-deletion and remote-deletion regressions; `--profile` + `--diff`;
  fetch-failure fallback (with and without cached ref); default-branch
  fallback verification; missing `git`; path normalization; combined
  `git status` states; mutually exclusive `--api`/`--diff` rejection;
  JSON shape; and the per-file-vs-per-repo bug.
- `scripts/smoke` extended with offline drift runs.
- `README.md` gains a "Checking for drift" subsection; argparse
  description and help text are updated; `CHANGELOG.md` gains an
  `### Added` entry.

## Proposed Implementation Plan

### Phase 1 — Parser, routing, help text

- Add `--diff` and `--no-fetch` to `_runs_parser()` in
  `src/github_usage/cli_parsers.py`. Wrap `--diff` and the existing
  `--api` flag in a `parser.add_mutually_exclusive_group()` so they
  cannot be combined.
- Extend the subcommand `description` to mention both flags and the
  opt-out.
- Add a "Checking for drift" sub-bullet to the `Runs:` section in
  `cli.py` HELP, and add a line noting that `--diff` and `--api` are
  mutually exclusive.
- Add a `runs-diff)` case to `start.sh` that `exec`s
  `github-usage runs --diff "$@"`, and add a `runs-diff` line to the
  `start.sh` help output. Verify `./start.sh runs-diff --help` reaches
  the parser, and that `./start.sh runs --diff --api` exits non-zero
  with argparse's standard "not allowed with argument" error.

### Phase 2 — Drift detection core

Add a new module `src/github_usage/cli_runs_diff.py` (per the file-size
risk in the archived plan; `cli_runs.py` is at 370 lines and Phase 2
adds another 150-200). Functions:

- `resolve_remote_name(repo_root: Path) -> str` — runs
  `git rev-parse --abbrev-ref HEAD` to get the current branch, then
  `git config branch.<branch>.remote`. Falls back to `"origin"` if the
  config key is missing or the lookup fails (this includes the
  detached-HEAD case, where `git rev-parse --abbrev-ref HEAD` returns
  `HEAD` rather than a branch name, so the subsequent config lookup
  is a guaranteed miss and the fallback applies). Never raises.
  Always invoked with `cwd=repo_root`.
- `resolve_default_branch(repo_root: Path, remote: str) -> str | None` —
  runs `git symbolic-ref refs/remotes/<remote>/HEAD`, parses the
  ref to extract the branch name. If that fails, falls back to `main`
  then `master`, **verifying each candidate** with
  `git rev-parse --verify refs/remotes/<remote>/<branch>` before
  selecting it. Returns the first verified branch, or `None` if
  none of the candidates exist locally. Always invoked with
  `cwd=repo_root`.
- `fetch_remote(repo_root: Path, remote: str,
  *, skip_fetch: bool, env: Mapping[str, str]) -> tuple[bool, bool]`
  — runs `git fetch <remote>` (no branch argument; this fetches
  all branches and tags) unless `skip_fetch` is True (set when
  `--no-fetch` is passed or `GITHUB_USAGE_SKIP_FETCH=1` is in
  `env`). Returns `(fetched, using_cached_ref)`:
  - `fetched=True, using_cached_ref=False` — fresh fetch succeeded.
  - `fetched=False, using_cached_ref=False` — fetch failed (network
    error, auth failure, etc.) or was skipped; the subsequent
    `resolve_default_branch` call will then fall back to whatever
    cached refs exist locally (or return `None` if none).
  The cached-ref check lives in `resolve_default_branch` (via
  `git rev-parse --verify refs/remotes/<remote>/<branch>`); this
  function does not need to know about it. The fetch must run
  **before** `resolve_default_branch` is called, so that the
  default-branch resolver sees fresh refs on first run. Never
  raises. Always invoked with `cwd=repo_root`.
- `classify_drift(repo_root: Path, remote: str,
  default_branch: str | None,
  *, candidate_path: Path | None = None) -> list[dict]` — produces
  the per-file row list. Takes an optional pre-resolved
  `candidate_path` which restricts scope to a single path. The
  function does not validate the profile — that is `main()`'s job.
  Algorithm:
  1. Enumerate candidate paths. If `candidate_path` is set, the
     candidate set is exactly that single path (normalized). If
     it is `None`, enumerate both local and remote:
     - Local: `git ls-tree -r HEAD -- .github/workflows/` filtered
       to the `email-report*.yml` glob (this catches files
       committed in HEAD but not present in the index, e.g. after
       `git rm`), plus `git ls-files
       .github/workflows/email-report*.yml` and a `Path.glob` over
       the working tree for untracked workflow files.
     - Remote: `git ls-tree -r <remote>/<default_branch>
       -- .github/workflows/` filtered to the `email-report*.yml`
       glob. This is what makes `remote-only` discoverable.
       **Skipped when `default_branch` is `None`** (no remote ref
       available); in that case, any row that needs a remote check
       degrades to `unknown` with summary
       `no remote default branch ref available`.
     - Normalize every discovered path to repo-relative POSIX form
       via the helper `(repo_root / p).relative_to(repo_root).as_posix()`.
       This handles both absolute paths (from `Path.glob`) and
       relative paths (from `git ls-tree`/`ls-files`); the naive
       `Path(p).relative_to(repo_root)` would raise `ValueError`
       on the relative case.
     - Union the two path sets, preserving order (remote-first,
       then local-only).
   2. **Batched `git status` pre-pass:** before iterating candidate
      paths, run `git status --porcelain=v1 -- .github/workflows/`
      (always pinned to v1; the v2 format enabled by
      `git config status.porcelainFormat=2` is not supported) once
      with `cwd=repo_root` and the module-level env (see step 3).
      Parse the output into a dict mapping `repo-relative path →
      status line`. The lookup is case-sensitive and tolerates
      missing entries (a clean tracked file does not appear in
      `git status` output; treat as "no status change", which
      proceeds to step 2b). Batching replaces the earlier
      per-path-`P` approach and keeps the total subprocess call
      count constant regardless of how many workflow files exist.
      For each candidate path `P`:
      a. Look up `P` in the status dict. If present, parse the X
         (index) and Y (working-tree) columns of the line.
         Precedence (with explicit summary strings): rename
         (`R*`), copy (`C*`), and unmerged (`U*`) states are
         handled by the generic rules below (Y non-space →
         `uncommitted`, X non-space & Y space → `staged`)
         without special-casing:
         - First two chars are `??` → row is `untracked`, summary
           `untracked file`.
         - Y is non-space (e.g. ` M`, `MM`, `AM`, `MD`, ` D`) →
           row is `uncommitted`, summary
           `uncommitted changes in working tree`.
         - X is non-space and Y is space (e.g. `M `, `A `, `D `)
           → row is `staged`, summary `staged changes in index`.
         - Empty → continue to step 2b.
     b. Compute per-file blob hashes:
        - `local_blob` = sha from
          `git ls-tree HEAD -- P` (or `None` if file absent at HEAD).
        - `remote_blob` = sha from
          `git ls-tree <remote>/<default_branch> -- P` (or `None`;
          `None` if `default_branch` is `None`).
     c. If both `None`: skip the path (file doesn't exist anywhere).
     d. If `local_blob == remote_blob`: row is `in-sync`, summary
        `in sync with <remote>/<default_branch>`.
     e. If hashes differ, run two three-dot diffs:
        - `ahead_diff` = stdout of
          `git diff <remote>/<default_branch>...HEAD -- P` (empty
          or non-empty).
        - `behind_diff` = stdout of
          `git diff HEAD...<remote>/<default_branch> -- P`.
        - If `ahead_diff` and `behind_diff`: row is `diverged`,
          summary `local and remote have diverged`.
        - If `ahead_diff` only: row is `ahead`. Summary depends
          on `local_blob`/`remote_blob`:
          - `local_blob` is `None` and `remote_blob` is not
            (e.g. file deleted locally, committed): summary
            `deleted locally, not pushed`.
          - `local_blob` is not `None` and `remote_blob` is
            `None` (e.g. file added locally, committed):
            summary `added locally, not pushed`.
          - Both non-`None`: summary
            `local has newer version`.
        - If `behind_diff` only: row is `remote-only` if
          `local_blob` is `None` (file is wholly missing
          locally; summary `added on remote, not pulled`),
          otherwise `behind`. Summary for `behind` is
          `remote has newer version` (or `deleted on
          remote, not pulled` when `remote_blob` is `None`
          and `local_blob` is not — i.e. a remote deletion
          that has not been pulled).
   3. Every `subprocess.run` call passes `cwd=repo_root` and
      uses `check=False`, `capture_output=True`, `text=True`,
      `timeout=30` (or a higher value for the network-bound
      `git fetch` if needed). The env is a module-level constant
      `GIT_ENV = {**os.environ, "LC_ALL": "C"}` — `LC_ALL=C`
      ensures stable sort order for porcelain output regardless
      of the user's locale. Each call is wrapped in
      `try/except (FileNotFoundError, OSError,
      subprocess.SubprocessError)` (covers `TimeoutExpired`
      for timeouts and `FileNotFoundError` for missing `git`;
      non-zero exits are handled by checking `result.returncode`
      on the `CompletedProcess`, not by catching an exception,
      since the calls use `check=False`); on a missing
      `git` binary, the early check in Phase 3 has already
      failed with a clear error before this loop is reached, so
      the `FileNotFoundError` catch is a defense-in-depth net.
      A `git fetch` timeout is treated as a fetch failure and
      triggers the warning
      `warning: fetch of <remote> failed; falling back to cached refs (<remote>/<default_branch>)`
      to stderr; classification then proceeds with the cached
      ref. Failures on individual commands (non-zero exit)
      degrade the row to `unknown` with a descriptive note
      rather than aborting the whole command.
- `DRIFT_CATEGORIES = {"in-sync", "uncommitted", "staged", "ahead",
  "behind", "remote-only", "untracked", "diverged", "unknown"}` —
  single source of truth (module-level constant in
  `cli_runs_diff.py`), used by the printer and asserted in tests.

The `paths` scope is the tracked `.github/workflows/email-report*.yml`
glob only. `.github-usage/config.toml` is intentionally excluded: it is
created locally by the setup wizard and is not pushed, so it has no
remote counterpart and would always be reported as `untracked`. The cron
expression lives in the workflow YAML on the GitHub side, so the YAML
is the right thing to diff.

### Phase 3 — Output rendering and JSON shape

- Add `_print_drift(rows: list[dict], remote: str, default_branch: str) -> None`
  to `cli_runs_diff.py` that prints a compact table similar to
  `_print_runs`: one line per row in the format
  `<path> · <drift> · <summary>` (e.g.
  `.github/workflows/email-report.yml · ahead · added locally, not pushed`).
  When `rows` is `[]` (all workflows in-sync, or a launchd-only
  profile short-circuited), print `"No drift detected."` to stdout.
  The JSON path wraps the empty array in the metadata object as
  already specified.
- In `main()` (in `cli_runs.py`, calling into the diff module), the
  diff path **replaces** the existing `list_local_runs()` path. The
  current `main()` is `parse args → load config → list_local_runs()
  → (if --api) enrich → output`. The new flow adds an **explicit
  early branch** at the top of `main()`: when `args.diff` is set,
  main() runs the diff path and returns 0; it does **not** call
  `list_local_runs()`. The diff path:
  0. **Early environment checks** (fail fast, fail clearly):
     if `shutil.which("git") is None`, print
     `Error: git is required for --diff but was not found on PATH.`
     to stderr and return `1`. If `not (repo_root() / ".git").exists()`,
     print `Error: --diff must be run from within a git repository.`
     to stderr and return `1`. These are quick sanity checks
     before any subprocess work, so the user gets a clear error
     instead of a wall of `unknown` rows.
  1. **Constraint checks** (runtime — argparse cannot enforce
     "valid only with" cleanly): if `args.diff` and
     (`args.owner is not None` or `args.repo is not None`), print
     `Error: --owner and --repo only apply to --api.` to stderr and
     return `1`. If `args.no_fetch` and not `args.diff`, print
     `Error: --no-fetch only applies to --diff.` to stderr and
     return `1`. (The mutual exclusion of `--api` and `--diff` is
     handled by `add_mutually_exclusive_group` in Phase 1.)
  2. **Config loading** (only when needed): if `args.profile` is
     set, load config via `load_config(paths.config_file)` wrapped
     in the same `try/except (tomllib.TOMLDecodeError, ValueError,
     KeyError)` that the existing `list_local_runs()` path uses
     (see `cli_runs.py:337-342`). If `--profile` is not set, the
     diff path does not need config and skips this step.
   3. **Resolve `--profile`:** if set, call `find_profile(config,
     args.profile)` (from `src/github_usage/setup_config.py`); on
     a miss, print `Error: Profile '<name>' not found in
     configuration.` and return `1` — matching regular `runs`
     behavior. If the profile is valid, check whether its workflow
     **file exists** via
     `workflow_path(repo_root, args.profile).is_file()` (not
     `"github_actions" in profile` — every profile in
     `_default_profile` (setup_config.py:149) has that key, even
     for launchd-only profiles). If the file is missing, emit a
     stderr notice
     (`notice: profile '<name>' has no GitHub Actions workflow`)
     and return an empty diff (`[]`); do **not** call
     `classify_drift`. Otherwise, resolve the path via
     `workflow_path(repo_root, args.profile)` and pass it to
     `classify_drift(..., candidate_path=<resolved>)`.
   4. **Pre-`classify_drift` setup** (the call sequence; the
     ordering matters):
     ```python
     remote = resolve_remote_name(repo_root)
     fetched, using_cached_ref = fetch_remote(
         repo_root, remote,
         skip_fetch=(args.no_fetch or
                     os.environ.get("GITHUB_USAGE_SKIP_FETCH") == "1"),
         env=os.environ,
     )
     default_branch = resolve_default_branch(repo_root, remote)
     rows = classify_drift(
         repo_root, remote, default_branch,
         candidate_path=candidate_path,
     )
     ```
     The fetch must run **before** `resolve_default_branch` so that
     the resolver sees fresh refs on a first run. `fetch_remote`
     no longer takes a `default_branch` parameter (it has no need
     to; the cached-ref check lives in `resolve_default_branch`).
  5. **Output:** dispatch to `_print_drift` or
     `json.dumps(..., indent=2)` per `args.json`. Wrap the diff
     output in a top-level object:
     `{"kind": "diff", "default_branch": "main", "remote": "origin",
     "rows": [...], "fetched": true|false, "using_cached_ref":
     true|false, "skipped_fetch": true|false}`.
  6. Return `0`.

  Note: regular `runs --json` outputs a bare JSON array
  (`json.dumps(rows, indent=2)`); `--diff --json` outputs the
  metadata wrapper above. Consumers should check the top-level
  `kind` field (absent for the regular view, `"diff"` for the
  diff view) to discriminate.
- A diff run with no other flags does **not** also emit the regular
  `runs` rows; the two views are alternatives. The mutually exclusive
  group in Phase 1 makes `--api + --diff` a parse-time error.

### Phase 4 — Start.sh shortcut

- Add `runs-diff)` case in `start.sh`:
  ```sh
  runs-diff)
    shift
    exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage runs --diff "$@"
    ;;
  ```
- Update `start.sh` help text to include the new shortcut
  with a one-line description. Insert after the existing `runs`
  line in the Commands section:
  `  runs-diff     Check for drift between local workflows and the remote default branch`

### Phase 5 — Documentation

- `README.md`: under "Viewing Configured Runs", add a new subsection
  "Checking for drift" covering the `--diff` flag, the `--no-fetch`
  /`GITHUB_USAGE_SKIP_FETCH=1` opt-out, the row shape, the per-file
  (not per-repo) classification, the dynamic remote resolution, the
  fetch-failure-with-cached-ref fallback, the `--profile` filter
  interaction, and an example showing the typical output (in-sync,
  ahead, behind, remote-only, local deletion, remote deletion).
  Note that `.github-usage/config.toml` is intentionally not in scope.
- `cli_parsers.py` argparse description: extend the existing
  description (added in the prior doc-tightening commit) to call out
  `--diff` and the opt-out. The full help text becomes:
  > View all currently configured scheduled runs (launchd and GitHub
  > Actions). Reflects local state: reads every config.toml profile
  > and any email-report*.yml files in .github/workflows/, so it shows
  > only what is on disk in this checkout. --api only enriches the
  > local rows with each workflow's latest run; it does not enumerate
  > workflows that exist on GitHub but not locally. --diff reports
  > per-file drift between the local working tree and the configured
  > remote's default branch for the tracked workflow YAMLs (mutually
  > exclusive with --api, and respecting --profile if given);
  > --no-fetch (or GITHUB_USAGE_SKIP_FETCH=1) skips the git fetch
  > step. The view matches what is configured on GitHub only when
  > local files reflect the pushed repo.
- Per-flag help text:
  - `--diff`: "Report per-file drift between the local working tree
    and the configured remote's default branch for the tracked
    workflow YAMLs. Runs `git fetch <remote>` by default; pass
    --no-fetch (or set GITHUB_USAGE_SKIP_FETCH=1) to skip the fetch.
    Cannot be combined with --api, --owner, or --repo. With
    --profile NAME, scopes the diff to that profile's workflow
    file only. Requires git on PATH and a git working tree."
  - `--no-fetch`: "Skip `git fetch <remote>` when using --diff. Use
    the local <remote>/<branch> ref as-is. Equivalent to setting
    `GITHUB_USAGE_SKIP_FETCH=1`."
- `CHANGELOG.md`: add a bullet under `[Unreleased] → ### Added`.

### Phase 6 — Tests

New file `tests/test_cli_runs_diff.py` with a `TestDrift` class. All
tests use a `FakeGit` helper (placed in `tests/_fakes.py` alongside
`FakeAPI` if it stays small) that intercepts `subprocess.run` and
returns canned `CompletedProcess` results keyed by argv. The pattern
mirrors the existing `_FakeAPI` class at
`tests/test_cli_runs.py:262-283` and the consolidated `FakeAPI` in
`tests/_fakes.py`. No live network, no live `git`.

Test categories (one test or parametrized set each):

- **Per-file classification:** in-sync, uncommitted, staged, ahead
  (modification), behind (modification), diverged.
- **Deletion regressions:** local committed deletion → `ahead`
  `deleted locally, not pushed`; remote deletion → `behind`
  `deleted on remote, not pulled`.
- **Remote-only:** `git ls-tree -r` enumerates a file not present
  locally → `remote-only`. Untracked local workflow → `untracked`.
  Assert `config.toml` is **never** present in the output (scope
  decision).
- **Combined `git status` states:** `MM`, `AM`, `MD` all classify
  as `uncommitted` (Y column wins over X column).
- **`--profile` + `--diff`:** restricts to one file via
  `workflow_path`; launchd-only profile returns `[]` with a
  stderr notice.
- **Fetch failure:** with cached ref → `using_cached_ref=True`,
  stderr warning, normal classification; without cached ref →
  rows degrade to `unknown`, exit 0.
- **Default-branch verification:** `refs/remotes/origin/HEAD`
  missing; resolver tries `main` (missing) then `master` (verified
  via `git rev-parse --verify`) → returns `master`.
- **Missing `git` binary:** the early check in `main()` catches
  this before any subprocess work, exiting 1 with a clear error.
  The per-subprocess `try/except (FileNotFoundError, ...)` is
  defense-in-depth.
- **Dynamic remote resolution:** `git config
  branch.<current>.remote` returns `upstream`; `fetch_remote` runs
  `git fetch upstream`; resolver reads `refs/remotes/upstream/HEAD`.
  Missing key → `origin`.
- **Detached HEAD:** `git rev-parse --abbrev-ref HEAD` returns
  `HEAD` (not a branch name); the `git config branch.HEAD.remote`
  lookup misses; `resolve_remote_name` falls back to `origin` and
  the rest of the pipeline proceeds normally.
- **Opt-out and shallow clone:** `--no-fetch` with missing ref →
  `unknown` with clear note; `GITHUB_USAGE_SKIP_FETCH=1` →
  `fetch_remote` not called; shallow clone / no upstream /
  detached HEAD → `unknown`, exit 0.
- **Mutually exclusive rejection:** `runs --diff --api` exits
  non-zero with argparse's "not allowed with argument" error;
  runner never reached.
- **Per-file vs per-repo regression:** an unrelated local commit to
  `README.md` does not produce a drift row for an unchanged
  `email-report.yml`.
- **JSON shape:** top-level object with `kind`, `default_branch`,
  `remote`, `fetched`, `using_cached_ref`, `skipped_fetch`, `rows`;
  each row has `path`, `drift`, `summary`.
- **First-run scenario (fetch-before-resolve ordering):** on a
  fresh clone with no `refs/remotes/<remote>/main` or
  `refs/remotes/<remote>/master`, `git fetch <remote>` is called
  first and populates the refs; `resolve_default_branch` then
  returns `main` (or `master`) from the fresh refs. No rows
  degrade to `unknown` due to ordering.
- **`--no-fetch` without `--diff` rejected:** `runs --no-fetch`
  (no `--diff`) exits 1 with `Error: --no-fetch only applies to
  --diff.`
- **Config error handling:** a malformed `config.toml` produces
  the existing user-friendly error (not a stack trace) when
  `--diff --profile NAME` is passed. The `try/except` for
  `tomllib.TOMLDecodeError`/`ValueError`/`KeyError` from the
  existing path is replicated in the diff path.
- **Missing `git` binary:** `shutil.which("git") is None` →
  exit 1 with `Error: git is required for --diff but was not
  found on PATH.` (no row-processing loop runs).
- **Not a git repo:** `(repo_root / ".git").exists()` is False →
  exit 1 with `Error: --diff must be run from within a git
  repository.`
- **Batched `git status`:** `git status --porcelain=v1
  -- .github/workflows/` is called exactly once per
  `classify_drift` invocation, regardless of the number of
  candidate paths. Assert via `FakeGit` call log.
- **Profile validation:** `runs --diff --profile bogus` prints
  `Error: Profile 'bogus' not found in configuration.` and exits
  1, matching regular `runs` behavior. The runner never calls
  `classify_drift`.
- **`default_branch is None` graceful degradation:**
  `resolve_default_branch` returns `None`; `fetch_remote` returns
  `(False, False)` without calling git; `classify_drift` skips the
  remote enumeration; any candidate path that would have required
  a remote check degrades to `unknown` with summary
  `no remote default branch ref available`; command exits 0.
- **Path normalization:** `git ls-tree` returns
  `.github/workflows/email-report.yml` (repo-relative) and
  `Path.glob` returns an absolute path; the union treats them as
  the same path. Assert no `ValueError` is raised.
- **`TimeoutExpired` handling:** `subprocess.run` raises
  `subprocess.TimeoutExpired` on the `git fetch` call; tool
  catches it, falls back to the cached ref (or degrades to
  `unknown` if no cached ref), emits a stderr message, and exits
  0.
- **Staged deletion discovery:** a workflow file is committed in
  HEAD but staged for deletion (`git rm`); neither `git ls-files`
  nor `Path.glob` returns it. With `git ls-tree -r HEAD` in the
  local enumeration, the path is discovered; `git status`
  returns `D `; row is `staged` with summary
  `staged changes in index`.
- **Summary strings:** assert that `uncommitted`, `staged`,
  `untracked`, `remote-only`, `in-sync`, `ahead` (three variants),
  `behind` (two variants), `diverged`, and `unknown` all carry
  the summary strings defined in Phase 2.

Extend `scripts/smoke` with: `--help` greps for `--diff` and
`--no-fetch`; `GITHUB_USAGE_SKIP_FETCH=1 ./start.sh runs-diff
--no-fetch --json` greps for `"kind": "diff"`; `./start.sh
runs-diff --help` succeeds; `./start.sh runs --diff --api` exits
non-zero.

## Out of Scope

- Interactive prompts in `start.sh` (the new shortcut is a
  non-interactive alias).
- Comparing local workflow YAML contents to a copy fetched from the
  GitHub API. The `git diff` already catches any divergence that
  matters.
- Parsing workflow YAMLs to extract cron expressions and comparing
  them to `config.toml`'s `[github_actions].cron`. Would require a
  YAML parser and a re-render; tracked as future work.
- Diffing the `launchd` plist. The plist is local-only and has no
  remote counterpart.
- Adding `--diff` to the `legacy_report` or `email-report` subcommands.
- Diffing `.github-usage/config.toml`. It is purely local (created
  by the setup wizard, never pushed) and has no remote counterpart.
- Generalizing the dynamic remote resolution to the existing
  `--api` path. The new `--diff` code uses
  `git config branch.<current>.remote` with an `origin` fallback;
  the older `--api` path still hardcodes `origin` in
  `_resolve_owner_repo`. Tracked as Future Work.

## Risks

- **Stale cached ref with non-fatal fetch failure.** The
  fetch-failure-with-cached-ref fallback means a long-disconnected
  user can see misleadingly-fresh "in-sync" results based on a stale
  cached ref. The stderr warning is the only signal — if
  `2>/dev/null` swallows it, the user won't know. Call this out in
  the README and help text.
- **Missing `git` binary.** The early `shutil.which("git")` check
  in `main()` catches this and exits 1 with a clear error before
  any subprocess work. The per-subprocess `try/except` is
  defense-in-depth only.
- **Path-normalization edge cases.** Symlinks, case-insensitive
  filesystems, and trailing slashes could cause duplicate or missed
  paths in the union. The plan normalizes via
  `Path(p).relative_to(repo_root).as_posix()`, which handles the
  common cases; pathological setups are out of scope.
- **Three-dot diff with unrelated histories.** When the local
  branch and the remote default branch have no common ancestor
  (e.g. `git remote add` pointing to a different repo), the
  three-dot form `git diff A...B` falls back to two-dot semantics
  on newer git versions, which can produce confusing `diverged`
  results. The plan does not special-case this; the mitigation is
  the cached-ref / `--no-fetch` path, where the resolver sees
  the same refs regardless of how `git diff` interprets them.
- **File size growth.** Phase 2 adds 200-300 lines to a new
  `cli_runs_diff.py` module. `cli_runs.py` (370 lines) stays under
  the 500-line soft limit; the new module is created from the start.

## Future Work

- A `--diff` mode that also parses the workflow YAML and the
  `config.toml` cron and shows a row-level cron-drift view, not just
  a file-level view. Useful for catching "I updated `config.toml`
  locally but forgot to re-render the workflow YAML" scenarios.
- Generalizing the dynamic remote resolution (`git config
  branch.<current>.remote` with `origin` fallback) to the existing
  `--api` path. Today `_resolve_owner_repo` still hardcodes
  `remote.origin.url`; unifying both paths on the new helper would
  benefit users on `upstream`-style remotes.
- Extending the default-branch fallback chain beyond `main` and
  `master` to include other common names (`develop`, `trunk`,
  etc.). The current chain covers the vast majority of repos but
  not, e.g., those using `develop` as the default.
- A `--diff` mode that handles symlinked repo roots, case-insensitive
  filesystems, and other path-normalization edge cases.
- A pre-commit hook that runs `runs --diff --no-fetch` and fails the
  commit if drift is detected (i.e. forces the user to commit the
  local changes before committing).
