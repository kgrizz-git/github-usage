# To Do

> **Note:** Remove items from this list once they are completed — do not leave completed items marked `[x]`. The `CHANGELOG.md` and the archived plans under `docs/superpowers/plans/archived/` are the historical record.

## Email Report Follow-Ups

- [ ] Add `--email-format text|html` HTML rendering. **[Plan](docs/superpowers/plans/2026-06-26-html-email-rendering.md)**
- [ ] Add cached or persisted artifact/release storage snapshots so monthly email reports can compare storage details over time.

## Test Coverage Gaps

- [ ] Add unit tests for remaining uncovered code: `report_account.py` (deeper coverage), `report_summary.py` (remaining helpers), `billing.get_actions_from_runs`, and `billing.get_full_billing`. (Other previously listed modules — `report_optional.*`, `report_data.get_key_insights`, `auth.check_user_scope` — now have coverage.)

## Code Health

- [ ] Refactor large Python modules/functions flagged by `scripts/check-sizes`: split `setup_wizard.py` (~534 lines, over the 500-line soft limit) into focused submodules, and trim the functions approaching the 100-line limit — `cli._run_email_report` (~97), `legacy_report.main` (~96), `scripts/api_discovery_month.main` (~82), and `report_data.build_report_data` (~81).

## Configuration & Setup

- [ ] Add support for configuring multiple reports with different run frequencies, targets, and options.
- [ ] Add support for viewing currently configured runs in the GitHub config (e.g., GitHub Actions schedules).
- [ ] Write Windows-compatible PowerShell versions of all scripts (setup, check, smoke, docs-check, etc.).
- [ ] Create a `start.ps1` PowerShell entrypoint script for Windows.

## Deferred

- [ ] Refactor to eliminate double API calls on legacy export (Fix #2, deferred from the 2026-06-21 bug fixes — the most architecturally invasive change; needs a dedicated refactor plan). **[Plan](docs/superpowers/plans/archived/2026-06-21-bug-fixes.md)**
- [ ] Add clearly labeled end-of-month spend projections based on elapsed days in the billing period.
- [ ] Add optional CC/BCC delivery fields for team and finance distribution.
- [ ] Evaluate report retention destinations such as GitHub Releases, S3, or shared drives after export/output support exists.

## Blocked, Indefinitely Deferred

- [ ] Add a `--month YYYY-MM` flag so users can query a specific billing period. **Deferred** — see `docs/api-discovery-month.md`; GitHub's billing endpoints ignore `since`/`until` parameters.
- [ ] Add historical email reports with `github-usage email-report --month YYYY-MM` after GitHub billing API period/filter behavior is specified and tested. **Blocked** by the same API gap as the legacy `--month` flag.
- [ ] Add month-over-month and year-over-year comparison sections once historical report data is available.
