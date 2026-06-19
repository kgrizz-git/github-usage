# To Do

## Core Reporting

- [x] Add report export support. Let the user create a CSV, XLSX, PDF, or similar report artifact. The CLI should support an explicit flag, for example `--export csv`, `--export xlsx`, `--export pdf`, or `--export none`; if no export option is provided in an interactive terminal, prompt the user whether they want an export file.
- [x] Add `--json` output for machine-readable reporting.
- [x] Add `--output PATH` alongside `--export FORMAT`.
- [x] Add `--no-interactive` so scripts and CI never hang on prompts.
- [x] Add fixture-based tests for report rendering.
- [ ] Add a `--month YYYY-MM` flag so users can query a specific billing period. **Deferred** — see `docs/api-discovery-month.md`; GitHub's billing endpoints ignore `since`/`until` parameters.
- [x] Add a redaction layer before writing export files, especially for usernames, repository names, and billing details.
- [x] Continue reducing long legacy report-section functions after the first `legacy.py` module split (Completed refactoring of `report_summary.py`).

## Email Report Follow-Ups

- [ ] Add historical email reports with `github-usage email-report --month YYYY-MM` after GitHub billing API period/filter behavior is specified and tested. **Blocked** by the same API gap as the legacy `--month` flag.
- [ ] Add month-over-month and year-over-year comparison sections once historical report data is available.
- [ ] Add clearly labeled end-of-month spend projections based on elapsed days in the billing period.
- [x] Support saving the rendered email report through the shared `--output PATH` / export path instead of adding an email-only attachment flag.
- [ ] Add `--email-format text|html` after the plain-text formatter is stable. (Flag added in this PR; HTML rendering deferred.)
- [ ] Add optional CC/BCC delivery fields for team and finance distribution.
- [ ] Add default GitHub API and Resend timeout/retry behavior, then consider `--timeout SECONDS` and `--max-retries N` flags if users need control.
- [ ] Evaluate report retention destinations such as GitHub Releases, S3, or shared drives after export/output support exists.
- [ ] Add cached or persisted artifact/release storage snapshots so monthly email reports can compare storage details over time.

## Remaining Bug Fixes (from bug-report-20260616-143630.md)

- [ ] Fix #18: `sys.argv` mutation is process-global — `_resolve_email_token` and `_run_legacy_report` still mutate `sys.argv` without serialization. Pass argv explicitly or isolate mutations. (`cli.py:175-189`, `_resolve_email_token:117-122`)
- [ ] Fix #20: `_generated_line` can print `Generated: None` — when `generated_at` is falsy, fall back to today's date directly instead of stringifying None. (`email_report.py:14, 19-25`)
- [ ] Fix #8 (complete): `check_user_scope` still uses deprecated `X-OAuth-Scopes` header and does not support fine-grained PATs or GitHub Apps. Consider scope-agnostic alternatives like `GET /user/installations` or rate-limit response headers. (`auth.py:40-50`)
- [ ] Fix #12 (complete): `legacy_main` is still wrapped in `try/except SystemExit`. Let `parser.parse_args` propagate `SystemExit` and only catch it for the `--help` case if translation is needed; otherwise remove the wrapper. (`cli.py:79-82, 184-188`)
- [ ] Fix #16 (complete): `int()` on malformed sizes still raises for non-numeric string/float values. Add `or 0` fallback or skip items where conversion fails. (`report_optional.py:44, 65`)

## Test Coverage Gaps

- [ ] Add unit tests for uncovered modules: `report_account.py`, `report_products.py`, `report_summary.py` (remaining helpers), `billing.get_actions_from_runs`, `billing.get_full_billing`, `report_optional.get_repo_consumers`, `report_optional.get_artifact_storage_details`, `report_optional.get_release_asset_details`, `report_data.get_key_insights`, `auth.check_user_scope`.
- [ ] Add tests for untested branches: `cli._run_email_report` (`--max-repos < 1`, `--warn-over` parsing, `_confirm_release_assets` non-tty failure, actual `send_email` path), `api.GitHubAPI.request` (403 retry, JSON-decode-failure, pagination termination), `email_report._generated_line` edge cases, `auth.resolve_token` `gh auth token` success branch.
- [ ] Remove or wire up unused fixture files in `tests/fixtures/` (`artifacts.json`, `billing_actions_summary.json`, `billing_copilot_summary.json`, `billing_git_lfs_summary.json`, `premium_request_usage.json`, `rate_limit.json`, `releases.json`, `repos.json`).

## Repo Engineering & Hygiene

- [ ] Enforce file size limits: add a lint step (or pre-commit hook) that fails if any source file exceeds 300 lines or any function exceeds 50 lines, per `AGENTS.md` style rule.
- [ ] Add a doc hygiene check: verify that public modules/functions have docstrings, and that `AGENTS.md` / `README.md` / CLI `--help` text are consistent.
- [ ] Review and update `AGENTS.md` instructions to agents: clarify the staleness comment pattern, the done criteria, and the test coverage expectations from the bug report.
- [ ] Add a stale-documentation reminder: scripts or CI should flag assessment files (e.g. `docs/assessments/`) older than 30 days for review, since the current bug report already has a staleness notice.
- [ ] Add a repo harness maintenance checklist: periodic re-runs of `scripts/check`, `scripts/smoke`, `scripts/docs-check`, and `scripts/security` with updated results in assessment docs.
- [ ] Instruct agents (via `AGENTS.md`) to move complete, superseded, or archived plans to `superpowers/plans/archived/` to keep the active plans directory uncluttered.
