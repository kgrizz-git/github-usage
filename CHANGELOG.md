# Changelog

All notable changes to this project will be documented in this file.

This project follows the structure from Keep a Changelog and intends to use Semantic Versioning once the CLI contract stabilizes.

## [Unreleased]

### Added

- `github-usage email-report` subcommand for plain-text scheduled billing reports.
- Resend email delivery support using stdlib HTTP calls.
- GitHub Actions workflow template for scheduled email reports using `GH_USAGE_TOKEN`.
- Fixture-backed tests for email formatting, report data shaping, and workflow template safety.

## [0.1.0] - 2026-06-14

### Added

- Package skeleton around the v3 GitHub usage report.
- CLI wrapper with `--help` and `--version`.
- Unit tests for token resolution and CLI no-token behavior.
- Local harness scripts for checks, smoke testing, formatting, security, and docs checks.
- Repository guidance for CI, hooks, security scanning, documentation, and hygiene.
