# To Do

> **Note:** Remove items from this list once they are completed — do not leave completed items marked `[x]`. The `CHANGELOG.md` and the archived plans under `docs/superpowers/plans/archived/` are the historical record.

## Security & Content Checks (top priority)

- [ ] Broaden generated-content guardrails beyond the current filename-only `forbid-generated-reports` hook (matches `github-usage-*.json`) into a content-aware check in `scripts/security` + the `Security` CI workflow that flags committed files containing:
  - absolute local paths (e.g. `/Users/`, `C:\`, `/tmp/`, `/var/`)
  - unredacted report output in **email bodies (plain-text + HTML)**, **text**, and **PDF** exports — email is the main gap today (`redact.py` covers file exports only, not email bodies; PDF output needs verification), plus generated report artifacts in any format (`.json`, `.txt`, `.pdf`, `.xlsx`, `.csv`)
- [ ] Add a dependency/vulnerability CI step: run `pip-audit` (already a `[dev]` dep, currently only invoked implicitly via `scripts/security`) as an explicit always-failing job in `.github/workflows/security.yml`.
- [ ] Add a code-complexity pre-commit hook (e.g. `xenon`/`radon` or ruff `C901`/`mccabe`) with a project-appropriate threshold, and fail CI on violations (watch `cli_runs.py` at 534 lines and `setup_config.py` at 507).
- [ ] Add a coverage CI job: a new `scripts/coverage` (or extend `scripts/check`) using `coverage.py`, enforce a baseline threshold that ratchets up, and gate PRs on it.
- [ ] Add tests for the above: content-check unit tests with absolute-path/report-artifact fixtures, redaction coverage for email/PDF output, and the dependency/complexity/coverage gates' behavior.
- [ ] Add an inventoried `scripts/sonarqube` helper that runs a local SonarQube scan (Docker `sonarqube` container + `sonar-scanner`, token via env var, output under `tmp/` or `reports/`), documented in the README scripts section and `docs/repo-harness-guidance.md` alongside `scripts/security`.

## Email Report Follow-Ups

- [ ] Add cached or persisted artifact/release storage snapshots so monthly email reports can compare storage details over time.

## Actions / Local Full Report

- [ ] Private-only top consumers + wall-clock workflow breakdown — see [plan](docs/superpowers/plans/2026-07-31-private-top-consumers.md).
- [ ] Retire dead Actions OS-from-runs path (honesty) — see [plan](docs/superpowers/plans/2026-07-31-actions-os-from-runs-honesty.md).
- [ ] Opt-in monthly deep run analysis (top private repo by gross cost; job-level approx + calendar-month cache) — see [plan](docs/superpowers/plans/2026-07-31-opt-in-deep-run-analysis.md) (depends on private-top-consumers Phase 0 / ideally Phase 4).
- [ ] After private-top-consumers: add `TODO` comments at `repo_consumers` readers in `export_csv.py`, `export_xlsx.py`, and `export_pdf.py` for private ranking / workflow-breakdown columns or sheets.
- [ ] Private-only **artifact-scan** ranking (artifact section already groups by visibility; billed storage ranking is in private-top-consumers).
- [ ] Workflow breakdown for more than the single top private repo (extend beyond Phase 4’s one-repo wall-clock section).
- [ ] Deep-analysis follow-ons (email section, top-N repos, export columns, auto-enable without flag) — deferred items in [opt-in deep-run plan](docs/superpowers/plans/2026-07-31-opt-in-deep-run-analysis.md) Phase 6.

## Code Health

- [ ] Refactor `src/github_usage/setup_config.py` (507 lines, over the 500-line limit per `scripts/check-sizes`). Extract a focused submodule — e.g. profile schema/loading (`load_report_profiles`, `find_profile`, `ensure_profiles`, `_default_profile`) and/or the TOML writer helpers (`_emit_*_block`, `write_config`) — to bring the file back under the threshold. Also watch `setup_wizard.py` (461 lines) and the `_manage_profiles()`/`_run_email_report()` functions, which are approaching their limits.
- [ ] Rename internal `legacy_*` modules/symbols to “local full report” naming (`legacy_report_data` → e.g. `local_report_data`, cache `kind="legacy"`, CLI/TUI internals, tests). User-facing copy already says “local full report”; this is the code rename. Keep a thin `legacy` compatibility shim if external imports still need it.

## Configuration & Setup

- [ ] Write Windows-compatible PowerShell versions of all scripts (setup, check, smoke, docs-check, etc.).
- [ ] Create a `start.ps1` PowerShell entrypoint script for Windows.

## Deferred

- [ ] Add optional CC/BCC delivery fields for team and finance distribution.
- [ ] Evaluate report retention destinations such as GitHub Releases, S3, or shared drives after export/output support exists.

## Blocked, Indefinitely Deferred

- [ ] Add a `--month YYYY-MM` flag so users can query a specific billing period. **Deferred** — see `docs/api-discovery-month.md`; GitHub's billing endpoints ignore `since`/`until` parameters.
- [ ] Add historical email reports with `github-usage email-report --month YYYY-MM` after GitHub billing API period/filter behavior is specified and tested. **Blocked** by the same API gap as the local full report `--month` flag.
- [ ] Add month-over-month and year-over-year comparison sections once historical report data is available.
