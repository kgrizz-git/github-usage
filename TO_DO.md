# To Do

## Core Reporting

- [x] Add report export support. Let the user create a CSV, XLSX, PDF, or similar report artifact. The CLI should support an explicit flag, for example `--export csv`, `--export xlsx`, `--export pdf`, or `--export none`; if no export option is provided in an interactive terminal, prompt the user whether they want an export file.
- [x] Add `--json` output for machine-readable reporting.
- [x] Add `--output PATH` alongside `--export FORMAT`.
- [x] Add `--no-interactive` so scripts and CI never hang on prompts.
- [x] Add fixture-based tests for report rendering.
- [x] Add a redaction layer before writing export files, especially for usernames, repository names, and billing details.
- [x] Continue reducing long legacy report-section functions after the first `legacy.py` module split (Completed refactoring of `report_summary.py`).

## Email Report Follow-Ups

- [x] Support saving the rendered email report through the shared `--output PATH` / export path instead of adding an email-only attachment flag.
- [ ] Add `--email-format text|html` after the plain-text formatter is stable. (Flag added in this PR; HTML rendering deferred.)
- [x] Add default GitHub API and Resend timeout/retry behavior...
- [ ] Add cached or persisted artifact/release storage snapshots so monthly email reports can compare storage details over time.

## Remaining Bug Fixes (from bug-report-20260616-143630.md)

- [x] Fix #18: `sys.argv` mutation is process-global — `_resolve_email_token` and `_run_legacy_report` still mutate `sys.argv` without serialization. Pass argv explicitly or isolate mutations. **Done in 2026-06-19-bug-fixes plan:** `resolve_token` now takes an explicit `argv` parameter; the `_resolve_email_token` wrapper was deleted; `_run_legacy_report` builds an explicit `legacy_argv` slice and passes it to both `resolve_token` calls. `sys.argv` is no longer mutated.
- [x] Fix #20: `_generated_line` can print `Generated: None` — when `generated_at` is falsy, fall back to today's date directly instead of stringifying None. **Done in 2026-06-19-bug-fixes plan:** `_generated_line` now takes `str | None`, short-circuits on falsy input, and the `except ValueError` branch also falls back to today's date. The `str(...)` wrapper at the call site was removed.
- [x] Fix #8 (complete): `check_user_scope` still uses deprecated `X-OAuth-Scopes` header and does not support fine-grained PATs or GitHub Apps. **Done in 2026-06-19-bug-fixes plan:** replaced the `X-OAuth-Scopes` parse with a 200-only check on `GET /user`. Misleading "missing 'user' scope" messages updated at `cli.py`, `legacy_report.py`, and `api.py`. The duplicate "Current token scopes" diagnostic block in `legacy_report.py` was deleted.
- [x] Fix #12 (complete): `legacy_main` is still wrapped in `try/except SystemExit`. **Done in 2026-06-19-bug-fixes plan:** the inner `try/except SystemExit` around `legacy_main` was removed; the entire `main()` body is now wrapped in a single `try/except SystemExit` that converts exits to return codes. The two `parse_args` call sites still use `_safe_exit_code`.
- [x] Fix #16 (complete): `int()` on malformed sizes still raises for non-numeric string/float values. **Done in 2026-06-19-bug-fixes plan:** added a private `_safe_int_size(value)` helper in `report_optional.py` that returns `None` on `ValueError`/`TypeError`; `get_artifact_storage_details` and `get_release_asset_details` filter out `None` values from the per-repo sum.

## Test Coverage Gaps

- [ ] Add unit tests for uncovered modules: `report_account.py`, `report_products.py`, `report_summary.py` (remaining helpers), `billing.get_actions_from_runs`, `billing.get_full_billing`, `report_optional.get_repo_consumers`, `report_optional.get_artifact_storage_details`, `report_optional.get_release_asset_details`, `report_data.get_key_insights`, `auth.check_user_scope`. — Partial in 2026-06-19-bug-fixes plan: added `tests/test_report_optional.py` covering `get_repo_consumers`, `get_artifact_storage_details`, `get_release_asset_details`, and `_safe_int_size`; added 4 tests for `report_data.get_key_insights`; added 3 tests for `auth.check_user_scope` in `tests/test_auth.py`. Remaining: `report_account.py` deeper coverage, `report_summary.py` remaining helpers, `billing.get_actions_from_runs`, `billing.get_full_billing`.
- [x] Add tests for untested branches: `cli._run_email_report` (`--max-repos < 1`, `--warn-over` parsing, `_confirm_release_assets` non-tty failure, actual `send_email` path), `api.GitHubAPI.request` (403 retry, JSON-decode-failure, pagination termination), `email_report._generated_line` edge cases, `auth.resolve_token` `gh auth token` success branch. — Partial in 2026-06-19-bug-fixes plan: added `_generated_line` edge case tests (`None`, `""`, unparseable, valid ISO), argparse-error SystemExit test, main-level SystemExit tests, new `resolve_token` tests. Many of the listed branches already have coverage in the existing test files.
- [x] Remove or wire up unused fixture files in `tests/fixtures/`. **Done in 2026-06-19-bug-fixes plan:** deleted 9 unreferenced fixtures (`artifacts.json`, `billing_actions_summary.json`, `billing_copilot_summary.json`, `billing_git_lfs_summary.json`, `premium_request_usage.json`, `rate_limit.json`, `releases.json`, `repos.json`, `user.json`); only `email_report_data.json` and `export_report_data.json` remain (both in active use).

## Repo Engineering & Hygiene

- [x] Add advisory size warnings: add a `scripts/check-sizes` script (and optional pre-commit hook) that warns when any source file exceeds 400 lines or any function exceeds 80 lines. Thresholds revised to 500-line / 100-line soft limits — warnings only, no hard failures. **Done 2026-06-19:** `scripts/check-sizes` written (AST-based, exit 0 always); wired into `scripts/check`. **[Plan](docs/superpowers/plans/archived/plan-repo-hygiene.md#1-enforce-file-size-limits)**
- [x] Instruct agents (via `AGENTS.md`) to keep files under 800 lines whenever possible, splitting large modules proactively rather than waiting for the lint threshold to trigger. **Done 2026-06-19:** Added "start extracting when approaching 200 lines" guidance to `AGENTS.md` Code Style (threshold revised from 800 to 200 — see plan). **[Plan](docs/superpowers/plans/archived/plan-repo-hygiene.md#2-agent-guidance-keep-files-under-800-lines)**
- [x] Improve overall repo hygiene: ensure `.gitignore` is complete, `pyproject.toml` / `requirements.txt` are in sync, and no stale artifacts (`.pyc`, `__pycache__`, `.env` files) are tracked. **Done 2026-06-19:** Added `pyproject.toml` dependency declaration note to `AGENTS.md`; no other changes needed (all hygiene checks passed). **[Plan](docs/superpowers/plans/archived/plan-repo-hygiene.md#3-improve-overall-repo-hygiene)**
- [x] Add a doc hygiene check: verify that public modules/functions have docstrings, and that `AGENTS.md` / `README.md` / CLI `--help` text are consistent. **Done 2026-06-19:** Added ruff `D100`/`D103`/`D104` (Google convention) to `pyproject.toml`; added docstrings to all 27 previously uncovered public functions and modules; 0 violations. CLI/README consistency already covered by `scripts/docs-check`. **[Plan](docs/superpowers/plans/archived/plan-repo-hygiene.md#4-add-doc-hygiene-check)**
- [x] Review and update `AGENTS.md` instructions to agents: clarify the staleness comment pattern, the done criteria, the test coverage expectations from the bug report, and the file-size guidance. **Done 2026-06-19:** Done criteria expanded with docstring/test/checkbox/archiving guidance; Code Style updated with 200-line proactive split signal; Repository Expectations updated with `pyproject.toml` dependency note.
- [x] Add a stale-documentation reminder: scripts or CI should flag assessment files (e.g. `docs/assessments/`) older than 30 days for review, since the current bug report already has a staleness notice. **Done 2026-06-19:** Extended `scripts/docs-check` to `find docs/assessments -name "*.md" -mtime +30` and print a warning listing stale files.
- [x] Add a repo harness maintenance checklist: periodic re-runs of `scripts/check`, `scripts/smoke`, `scripts/docs-check`, and `scripts/security` with updated results in assessment docs. **Done 2026-06-19:** Added "Periodic Maintenance Checklist" section to `docs/repo-harness-guidance.md`.
- [x] Instruct agents (via `AGENTS.md`) to move complete, superseded, or archived plans to `superpowers/plans/archived/` to keep the active plans directory uncluttered. **Done 2026-06-19:** Added archiving instruction to `AGENTS.md` Done Criteria; created `docs/superpowers/plans/archived/` directory.

## Process & Workflow

- [x] Instruct agents (via `AGENTS.md`) to mark plan items completed (check boxes) as they are implemented, rather than leaving them open or deleting them, so the plan file remains an accurate record of progress. **Done:** the 2026-06-19-bug-fixes plan was updated with `- [x]` checkboxes, `**Status:** COMPLETED` lines, and a `> **Status: COMPLETED 2026-06-19.**` banner at the top documenting verification results and implementation deviations.

## Configuration & Setup

- [x] Make the GitHub Actions `email-report.yml` workflow configurable via `./setup.sh` — cron schedule and report-section defaults. **Done 2026-06-22:** Added `setup_workflow.py`, `email-report.yml.template`, `[github_actions]` config section, and wizard menu option 5. **[Plan](docs/superpowers/plans/archived/2026-06-22-configurable-github-workflow.md)**
- [ ] Add support for configuring multiple reports with different run frequencies, targets, and options.
- [ ] Add support for viewing currently configured runs in the GitHub config (e.g., GitHub Actions schedules).
- [x] Move the `setup` entrypoint to the root repo directory for easier discovery (or add a wrapper entrypoint). **Done:** 2026-06-20 — promoted to `./setup.sh` with `scripts/setup` retained as a backward-compat shim (plan 2026-06-20-move-setup-entrypoint).
- [ ] Add Windows/PowerShell support for the setup script.
- [ ] Add single entrypoint for guiding user through running report locally or to email once, as well as through guided setup.

## Remaining Bug Fixes (from bug-report-20260621-000000.md)

- [ ] Fix bugs found in the 2026-06-21 codebase audit: broken token pre-check, double API calls on legacy export, `get_all_pages` no early termination, zero-values from failed API calls indistinguishable from actual zero, progress bar overflow when usage >100%, CSV column order fragility, redundant fallback `/user` call. **[Plan](docs/superpowers/plans/2026-06-21-bug-fixes.md)**

## DEFERRED

- [ ] Add clearly labeled end-of-month spend projections based on elapsed days in the billing period.
- [ ] Add optional CC/BCC delivery fields for team and finance distribution.
- [ ] Evaluate report retention destinations such as GitHub Releases, S3, or shared drives after export/output support exists.

## BLOCKED, INDEFINITELY DEFERRED

- [ ] Add a `--month YYYY-MM` flag so users can query a specific billing period. **Deferred** — see `docs/api-discovery-month.md`; GitHub's billing endpoints ignore `since`/`until` parameters.
- [ ] Add historical email reports with `github-usage email-report --month YYYY-MM` after GitHub billing API period/filter behavior is specified and tested. **Blocked** by the same API gap as the legacy `--month` flag.
- [ ] Add month-over-month and year-over-year comparison sections once historical report data is available.
