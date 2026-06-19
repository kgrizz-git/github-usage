# Changelog

All notable changes to this project will be documented in this file.

This project follows the structure from Keep a Changelog and intends to use Semantic Versioning once the CLI contract stabilizes.

## [Unreleased]

### Added

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
- **`--email-format text|html` flag** on `email-report` (HTML rendering deferred).
- **Redaction layer** (`src/github_usage/redact.py`): masks usernames, repository names, email addresses, and dollar amounts in file exports. Interactive terminal output and the email body are not redacted.
- **XLSX writer** (`openpyxl`): one sheet per major section; sheet names truncated to 31 chars; values starting with `=`, `+`, `-`, `@` are prefixed to prevent Excel formula injection.
- **PDF writer** (`fpdf2>=2.7`): cover page plus one page per section; sections over 30 rows are truncated with a note; uses `XPos`/`YPos` enums.
- **CSV writer**: section-based layout with `### Section ###` headers; UTF-8 BOM for Excel-on-Windows compatibility.
- **Optional dependency extras**: `pip install github-usage[export-xlsx]` and `[export-pdf]`. PEP 621 does not support nested extras, so users install one at a time.
- **API discovery script** (`src/github_usage/scripts/api_discovery_month.py`): gated by `GITHUB_USAGE_API_DISCOVERY=1`; tests whether billing endpoints honor `since`/`until` parameters and writes a sanitized report to `docs/api-discovery-month.md`.

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
