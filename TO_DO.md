# To Do

> **Note:** Remove items from this list once they are completed — do not leave completed items marked `[x]`. The `CHANGELOG.md` and the archived plans under `docs/superpowers/plans/archived/` are the historical record.

## Email Report Follow-Ups

- [ ] Add cached or persisted artifact/release storage snapshots so monthly email reports can compare storage details over time.

## Code Health

- [ ] Refactor `src/github_usage/setup_config.py` (507 lines, over the 500-line limit per `scripts/check-sizes`). Extract a focused submodule — e.g. profile schema/loading (`load_report_profiles`, `find_profile`, `ensure_profiles`, `_default_profile`) and/or the TOML writer helpers (`_emit_*_block`, `write_config`) — to bring the file back under the threshold. Also watch `setup_wizard.py` (461 lines) and the `_manage_profiles()`/`_run_email_report()` functions, which are approaching their limits.

## Configuration & Setup

- [ ] Make `start.sh` present users with an interactive options menu instead of requiring CLI flags.
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
