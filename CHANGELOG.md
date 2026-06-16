# Changelog

All notable changes to this project will be documented in this file.

This project follows the structure from Keep a Changelog and intends to use Semantic Versioning once the CLI contract stabilizes.

## [Unreleased]

### Added

- `github-usage email-report` subcommand for plain-text scheduled billing reports.
- Resend email delivery support using stdlib HTTP calls.
- GitHub Actions workflow template for scheduled email reports using `GH_USAGE_TOKEN`.
- Fixture-backed tests for email formatting, report data shaping, and workflow template safety.
- New unit tests for `storage.py`, `report_summary.py`, `report_actions.py`, `report_account.py`, and `report_products.py` (39 tests total).

### Fixed

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

## [0.1.0] - 2026-06-14

### Added

- Package skeleton around the v3 GitHub usage report.
- CLI wrapper with `--help` and `--version`.
- Unit tests for token resolution and CLI no-token behavior.
- Local harness scripts for checks, smoke testing, formatting, security, and docs checks.
- Repository guidance for CI, hooks, security scanning, documentation, and hygiene.
