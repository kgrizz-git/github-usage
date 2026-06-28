# Changelog

All notable changes to this project will be documented in this file.

This project follows the structure from Keep a Changelog and intends to use Semantic Versioning once the CLI contract stabilizes.

**Format:** In-progress changes stay under `[Unreleased]` until a release is tagged. Allowed subsections are `Added`, `Fixed`, `Changed`, and `Deferred` (for planned work intentionally not shipped, with a rationale).

## [Unreleased]

### Fixed

- **Backup-file harness:** `backups/*.bak` is now gitignored, `scripts/check-backups` rejects staged backup additions with a clear policy message, and `scripts/check`/pre-commit enforce that `backups/` contains no non-`.bak` files. `scripts/prune-backups` now skips staged additions so stale-backup pruning does not surface a low-level `git rm` failure.
- **None / null-tolerance hardening in `report_account.py`, `report_summary.py`, `billing.py`, and `report_data.py`** ([plan](docs/superpowers/plans/2026-06-27-unit-tests-coverage.md)): many `report_*` and `billing.*` functions called `.get()` on API responses without checking they were dicts, used `r.get(key, default)` patterns that didn't handle explicit `None` (only missing keys), and accumulated per-item totals using `+=` against fields that could be `None` (causing `TypeError`). Affected sites now coerce to `{}` or `0`/`0.0` defensively. `report_helpers.sanitize_item_amounts` is the single source-sanitization helper that runs at every storage site for billing-item dicts (`billing.get_billing_summary`, `billing.get_premium_request_usage`, `billing.get_actions_per_repo`, `report_data._billing_summary`, `report_data.get_copilot_usage`); downstream consumers (`legacy_report`, `report_actions`, `report_products`, `report_summary`) need no changes. Adds 60+ new unit tests across `tests/test_report_account.py`, `tests/test_report_summary.py`, `tests/test_billing.py`, `tests/test_report_data.py`, and `tests/test_report_optional.py`.
- **Storage formatting bug in `report_summary.py`:** raw storage (GB) was being printed using `fmt_price`, producing output like `$0.5000` for a 0.5 GB repo. Replaced with `f"{val:.2f} GB"` in `_print_storage_breakdown` (top-10 list, top-consumer total, item-level) and `_print_recommendations` (release assets), and removed a redundant `fmt_price(...)` substring from the "Biggest storage consumer" finding in `_print_impactful_findings` (the `size_str` already printed the size). User-visible change in the legacy interactive report.
- **`billing.get_actions_from_runs` defensive empty-list default:** now returns the default `(0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {})` if `api.get_all_pages(...)` returns `None` (previously crashed with `TypeError: 'NoneType' object is not iterable`). Also handles `billable` keys mapped to `None` (e.g. `{"UBUNTU": None}`) without crashing.
- **Stale "BUG" comment in `tests/test_billing.py`** removed: the test asserted `wf_min["CI"] == 3.0` (the correct value) while the comment claimed the code was buggy. The bug was fixed in a prior PR (CHANGELOG "Workflow Over-counting" under `### Fixed`); the comment was a stale remnant.

### Changed

- **Consolidated four duplicated `FakeAPI` classes** into a single class in `tests/_fakes.py`. The unified class supports `request` and `get_all_pages` independently, with sensible empty defaults, and includes an `Exception` injection feature (already used by `test_report_data.py`). `tests/test_billing.py`, `tests/test_report_data.py`, `tests/test_storage.py`, and `tests/test_report_optional.py` all import from the new location.

- **Module refactor for size compliance** ([plan](docs/superpowers/plans/archived/2026-06-26-module-refactor.md)): split `setup_wizard.py` (545 → 325 lines) into six focused submodules (`setup_email_config`, `setup_secrets`, plus additions to `setup_workflow`, `setup_config`, `setup_ci`, `setup_launchd`); extracted `cli_email_report` sub-module for the `_run_email_report` helpers; trimmed `legacy_report.main`, `api_discovery_month.main`, and `report_data.build_report_data` to bring all targets under the `scripts/check-sizes` warn thresholds. Test mocks updated to follow the new module paths. No behavioral changes.
- **`email_report.py` split for size compliance** ([plan](docs/superpowers/plans/archived/2026-06-26-email-report-split.md)): the 511-line file is now a 12-line re-export facade over four focused sub-modules — `email_report_text` (plain-text formatters), `email_report_html` (HTML formatters), `email_report_send` (Resend delivery), and `_email_report_common` (shared helpers). Public API preserved: `format_report_email`, `format_html_report`, `default_subject`, and `send_email` still resolve via `from github_usage.email_report import …` (the facade re-exports use the `name as name` alias form to survive `ruff --fix`; no `__all__` was added — the project does not use it elsewhere). Direct test imports of `_generated_line` and the section-formatter tuples were updated to point at the new sub-modules. No behavioral changes.

### Added

- **`github-usage runs` subcommand** ([plan](docs/superpowers/plans/archived/2026-06-28-view-configured-runs.md)): a read-only, non-interactive view of all currently configured scheduled runs — launchd schedules and GitHub Actions workflow cron expressions — across every `config.toml` profile. Reports an `active`/`inactive`/`unsupported` state per row, surfaces on-disk `email-report*.yml` workflows that don't match a configured profile as `<unconfigured>`, and supports `--profile`, `--json`, and an optional `--api` flag (with `--owner`/`--repo` overrides) that annotates each workflow with its latest GitHub Actions run timestamp and conclusion. Routed through both `cli.py` and `start.sh`. Each row also carries a `workflow_file` field (repo-relative path) in JSON output to support API matching — a minor addition beyond the original plan schema.
- **Multi-report profiles:** Configure named report profiles in `config.toml` (`[[reports]]`) with per-profile schedules, recipients, subjects, section toggles, and GitHub Actions cron settings. The CLI accepts `--profile`, `--to`, and `--subject`; `setup --print-args --profile NAME` expands a profile's flags; launchd installs one plist per profile; GitHub Actions renders one workflow per profile with options baked at render time (no runtime `config.toml` read in CI). Setup wizard adds **Manage report profiles** (`m`). Legacy single-profile configs round-trip unchanged.
- **`start.sh` entrypoint script:** Root-level unified CLI for setup, one-off legacy reports, and email-report runs.
- **`scripts/prune-backups` + pre-commit hook:** prunes tracked `backups/*.bak` files whose last commit is older than the most recent 5 commits (non-`.bak` files and untracked/new backups are preserved). Supports `PRUNE_BACKUPS_DRYRUN=1` and `PRUNE_BACKUPS_KEEP=N`.
- **`scripts/docs-check` plan-hygiene warning:** warns (without failing) when a plan whose status banner reads `COMPLETE`/`COMPLETED` is still in the active `docs/superpowers/plans/` directory instead of `archived/`.
- **`QWEN.md`** pointer file directing agents to `AGENTS.md`.
- `github-usage email-report` subcommand for plain-text scheduled billing reports.
- Resend email delivery support using stdlib HTTP calls.
- GitHub Actions workflow template for scheduled email reports using `GH_USAGE_TOKEN`.
- **`scripts/setup` guided wizard** for local secrets, report options, macOS launchd, GitHub Actions secrets, and pre-commit/pre-push hooks.
- `scripts/send-email-report.sh` scheduled runner and launchd template for local macOS schedules (Mondays at 9:00).
- **`.gitleaks.toml`** allowlist for example configs, fixtures, and test tokens.
- Fixture-backed tests for email formatting, report data shaping, and workflow template safety.
- New unit tests for `storage.py`, `report_summary.py`, `report_actions.py`, `report_account.py`, and `report_products.py` (39 tests total).
- **Report export:** `--export csv|xlsx|pdf|json|text|none` flag on both the legacy and email-report commands, with atomic write and an auto-generated default filename.
- **File output path:** `--output PATH` flag for specifying the export file path.
- **`--json` shorthand:** prints JSON to stdout (or to `--output` if set); mutually exclusive with `--export`.
- **`--no-interactive` flag:** skips interactive export-format prompts in CI/script contexts.
- **`--email-format text|html` flag** on `email-report`: now fully implemented. Renders a self-contained HTML email body via `email_report.format_html_report` (one section per plain-text section, with `html.escape` on all user-supplied and untrusted data), and sends both `text` and `html` fields through Resend so clients render the rich version with a plain-text fallback. Surfaced through the guided setup wizard (`scripts/setup` / `./start.sh setup`) as an `email_format` key in `[email_report]` config; defaults to `"text"`. `[Unreleased]`.
- **Redaction layer** (`src/github_usage/redact.py`): masks usernames, repository names, email addresses, and dollar amounts in file exports. Interactive terminal output and the email body are not redacted.
- **XLSX writer** (`openpyxl`): one sheet per major section; sheet names truncated to 31 chars; values starting with `=`, `+`, `-`, `@` are prefixed to prevent Excel formula injection.
- **PDF writer** (`fpdf2>=2.7`): cover page plus one page per section; sections over 30 rows are truncated with a note; uses `XPos`/`YPos` enums.
- **CSV writer**: section-based layout with `### Section ###` headers; UTF-8 BOM for Excel-on-Windows compatibility.
- **Optional dependency extras**: `pip install github-usage[export-xlsx]` and `[export-pdf]`. PEP 621 does not support nested extras, so users install one at a time.
- **API discovery script** (`src/github_usage/scripts/api_discovery_month.py`): gated by `GITHUB_USAGE_API_DISCOVERY=1`; tests whether billing endpoints honor `since`/`until` parameters and writes a sanitized report to `docs/api-discovery-month.md`.
- **Schedule-only menu option:** Configure the report schedule (weekday, hour, minute) from the setup menu without running the full wizard; regenerates the LaunchAgent plist and reminds the user to reinstall it when a LaunchAgent is already installed.
- **Full-setup plist sync:** Recommended full setup now regenerates the LaunchAgent plist after schedule prompts, even when launchd install is skipped.
- **Configurable GitHub Actions workflow (`setup_workflow.py`):** `./setup.sh` option 5 now configures the GitHub Actions email-report schedule and report-section defaults. Adds `src/github_usage/setup_workflow.py` (cron validation, template renderer, atomic write, unified diff), a checked-in `.github/workflows/email-report.yml.template` with `__TOKEN__` placeholders, a `[github_actions]` section in `.github-usage/config.toml`, and a new wizard flow that renders the workflow file and prints a `git add/commit/push` suggestion. The local launchd schedule (`[schedule]`) and the GitHub Actions cron (`[github_actions]`) are stored and configured independently.

### Deferred

- **`--month YYYY-MM` flag for historical billing queries.** API discovery (see `docs/api-discovery-month.md`) confirmed that all four tested billing endpoints ignore the `since`/`until` parameters and return the same shape with or without them. Historical month queries are not feasible with the current GitHub API. The flag is not added to the CLI in this PR; the discovery script can be re-run if GitHub adds date-range support.

### Fixed

- **Security workflow Gitleaks scan:** Fetch full git history in CI so push-range secret scans can resolve the parent commit.
- **CLI token positional argument:** Restored `github-usage <token>` support after the argparse refactor peeled flags but rejected the token.
- **Email-report structured export:** `email-report --export csv|xlsx|pdf|json` now passes structured report data instead of the formatted email body.
- **Email-report auto filename:** `email-report --export` without `--output` now auto-generates an output path, matching the legacy export behavior.
- **`--email-format html`:** Returns a clear error instead of silently ignoring the deferred flag.
- **TypeError in OS breakdown:** Corrected indexing error in `report_actions.py`.
- **Workflow Over-counting:** Fixed quadratic accumulation bug in `billing.py`.
- **Rate-Limit Retries:** Fixed `api.py` to use `Retry-After` HTTP headers and added recursion bounds.
- **Connection Leaks:** Ensured all `HTTPSConnection` instances are properly closed across the codebase.
- **NoneType Crashes:** Added guards for missing `monthly_costs` in `report_data.py`.
- **Safe Parsing:** Implemented robust URL encoding, path joining, and safe integer conversion for API data.
- **Pagination:** Improved `get_all_pages` to use the `Link` header and handle non-list error responses.
- **Ternary Precedence:** Fixed logic ambiguity in `report_summary.py`.
- **Division by Zero:** Added safeguards for cost calculations in `report_summary.py`.

### Changed

- **Unified entrypoint via `start.sh`:** Added a root-level `start.sh` wrapper that dispatches to `setup`, `report`, and `email-report` modes, and moved the guided setup script from `./setup.sh` to `scripts/setup.sh` (reached via `start.sh setup`). The previous root entrypoint remains as a thin `scripts/setup` shim.
- **Removed legacy backup scripts:** deleted the original `backups/github-usage`, `backups/github-usage-v2`, and `backups/github-usage.sh` (still recoverable via git history). `backups/` now holds only transient `*.bak` modification backups; `AGENTS.md`, `README.md`, and `docs/repo-harness-guidance.md` updated to match.
- **Documentation lifecycle standardized:** `AGENTS.md` now defines a single plan → complete → archive workflow plus changelog, `TO_DO.md`, and release conventions (mirrored in `docs/repo-harness-guidance.md`). `GEMINI.md` slimmed to point at `AGENTS.md`. `CHANGELOG.md` gained a format note sanctioning the `Deferred` subsection.
- **Plan housekeeping:** archived all completed plans into `docs/superpowers/plans/archived/`, normalized their status banners to the canonical `> **Status:** COMPLETE` form, and gave the two previously untimestamped archived plans timestamped filenames. `TO_DO.md` trimmed to open items only.
- **Setup entrypoint moved to `./setup.sh`:** The guided setup entry point now lives at the repo root as `setup.sh` for easier discovery. The previous `scripts/setup` path is preserved as a thin wrapper that forwards to the new root script.
- **Refactored `report_summary.py`:** Split large `show_final_summary` function into smaller, testable sub-functions.
- **Unified Error Messaging:** Shared `print_missing_token_error` helper for consistent CLI feedback.
- **Safe Exit Codes:** Added helper to handle non-numeric `SystemExit` codes gracefully.
- Split the legacy interactive report implementation into focused auth, API, billing, storage, and report-section modules while preserving `github_usage.legacy` compatibility imports.
- **`legacy_report.main()`** now accepts keyword-only parameters (`export`, `output`, `no_interactive`, `month`, `dry_run`) with defaults that preserve existing behavior, and returns the resolved username. The CLI is responsible for calling `build_report_data()` and `export_report.export()` to avoid duplicating API calls.

## [0.1.0] - 2026-06-14

### Added

- Package skeleton around the v3 GitHub usage report.
- CLI wrapper with `--help` and `--version`.
- Unit tests for token resolution and CLI no-token behavior.
- Local harness scripts for checks, smoke testing, formatting, security, and docs checks.
- Repository guidance for CI, hooks, security scanning, documentation, and hygiene.
