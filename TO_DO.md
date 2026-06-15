# To Do

## Core Reporting

- [ ] Add report export support. Let the user create a CSV, XLSX, PDF, or similar report artifact. The CLI should support an explicit flag, for example `--export csv`, `--export xlsx`, `--export pdf`, or `--export none`; if no export option is provided in an interactive terminal, prompt the user whether they want an export file.
- [ ] Split `src/github_usage/legacy.py` into focused modules such as `auth.py`, `api.py`, `billing.py`, `report.py`, and `cli.py`.
- [ ] Add `--json` output for machine-readable reporting.
- [ ] Add `--output PATH` alongside `--export FORMAT`.
- [ ] Add `--no-interactive` so scripts and CI never hang on prompts.
- [ ] Add fixture-based tests for report rendering.
- [ ] Add a `--month YYYY-MM` flag so users can query a specific billing period.
- [ ] Add a redaction layer before writing export files, especially for usernames, repository names, and billing details.

## Email Report Follow-Ups

- [ ] Add historical email reports with `github-usage email-report --month YYYY-MM` after GitHub billing API period/filter behavior is specified and tested.
- [ ] Add month-over-month and year-over-year comparison sections once historical report data is available.
- [ ] Add clearly labeled end-of-month spend projections based on elapsed days in the billing period.
- [ ] Support saving the rendered email report through the shared `--output PATH` / export path instead of adding an email-only attachment flag.
- [ ] Add `--format text|html` after the plain-text formatter is stable.
- [ ] Add optional CC/BCC delivery fields for team and finance distribution.
- [ ] Add default GitHub API and Resend timeout/retry behavior, then consider `--timeout SECONDS` and `--max-retries N` flags if users need control.
- [ ] Evaluate report retention destinations such as GitHub Releases, S3, or shared drives after export/output support exists.
