# Reports and exports

[Back to README](../README.md)

After [authenticating](setup.md#authentication), run a local full report with `./start.sh report` or preview an email report with `./start.sh email-report --dry-run`. For all command options, use `github-usage --cli --help` and `github-usage email-report --help`.

## API impact and billing interpretation

`--include-consumers`, `--include-artifact-storage`, and `--include-release-assets` add repo-level API calls. They consume GitHub REST API request quota, not Actions minutes, Actions storage, Copilot requests, Git LFS quota, or billable GitHub usage. Use monthly schedules and conservative `--max-repos` values for accounts with many repositories.

With `--include-consumers` (local full report and email), the **repo consumers** sections rank repositories by Actions usage alongside the existing combined top-by-minutes and top-by-cost lists:

- **Overall top-by-storage** — billed Actions storage ranked by average MB (`storage_avg_mb` from the billing API).
- **Private-only top lists** — separate rankings for Actions minutes and billed storage among private and internal repos only (the quota-relevant slice). Shown only when they add signal beyond the combined list (for example, when public repos dominate the overall minutes ranking).
- **Minutes by workflow** — for the top private-repo minutes consumer, an estimated per-workflow breakdown from completed run wall-clock time (start→end). This is **not billable** GitHub data: it uses fractional run elapsed time, not per-job rounding or OS multipliers, so the estimated total **will not match** the billed repo minutes figure. The section is labeled accordingly in terminal and email output (not the TUI summary view).

The same consumer keys appear in JSON exports; dedicated CSV/XLSX/PDF columns for private rankings and workflow breakdown are planned (see `TO_DO.md`).

Repo-level sections annotate non-public repositories with `[private]` or `[internal]` tags. The local full report's per-repo Actions table groups rows by visibility with subtotals. `--only-public` and `--only-private` (mutually exclusive) filter which repositories are included in repo-level sections; filtering applies after the `--max-repos` limit. Set `only_public` / `only_private` in `[email_report]` in `config.toml` for scheduled runs.

**Free-tier quota is private-first.** Limits Summary, utilization, forecasts, TUI rows, and exports measure Actions minutes and artifact storage against the free tier for **private** (and internal) repos only. Public standard-runner usage is shown separately and labeled free. Larger-runner SKUs are marked `*` (always billed). Artifact storage frames the 500 MB private allowance as GB-hours accrual (0.5 GB flat all month ≈ 360 GB-hrs for a 30-day month), splits Actions artifacts from release assets (releases are not quota-billed), and flags soon-to-expire / expired artifacts (default retention 90 days). Repos beyond `--max-repos` may appear as unattributed remainder vs the account billing total. Reports include a Sources footer linking GitHub’s Actions billing, runner pricing, and release-storage docs.

Visibility matters for billing: GitHub Actions minutes and storage are **free for public repositories** but consume your plan's monthly quota for private and internal repositories. See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) for included amounts and overage rates.

Release assets are optional inventory, not a billing/quota report. The CLI asks for confirmation in interactive terminals, and CI must pass `--yes-include-release-assets`.

## Exporting Reports

Both the local full report and email-report commands can write the report to a file in
CSV, XLSX, PDF, JSON, or plain text format. The local full report fetches data once
and uses it for both terminal output and export (lower GitHub API usage when
exporting). Exported files go through a
redaction layer that masks usernames, repository names, email addresses, and
dollar amounts before writing; interactive terminal output and the email body
are not redacted.

```sh
# Local full report
github-usage --export csv --no-interactive --output report.csv
github-usage --export xlsx --no-interactive --output report.xlsx
github-usage --export pdf --no-interactive --output report.pdf
github-usage --json --no-interactive          # JSON to stdout
github-usage --json --no-interactive --output report.json

# Email report
github-usage email-report --dry-run --export text --output report.txt
github-usage email-report --export csv --output report.csv
```

In an interactive terminal without `--export` and without `--no-interactive`,
the local full report prompts for a format (or `None` to skip).

### Format-specific notes

- **CSV** writes a UTF-8 BOM at the start of the file for Excel-on-Windows
  compatibility.
- **JSON** preserves the full `ReportData` dict, including the `api_estimate`
  metadata. Datetime values are emitted as ISO-8601 strings.
- **XLSX** uses one sheet per major report section. Sheet names are truncated
  to 31 characters (Excel limit). Values starting with `=`, `+`, `-`, or `@`
  are prefixed with a single quote to prevent Excel formula injection.
- **PDF** generates a multi-page document with a cover page and one page per
  section. Sections exceeding 30 rows are truncated with a note.
- **Text** delegates to the existing email-report formatter.

### Optional dependencies

`csv`, `json`, and `text` use the standard library. `xlsx` and `pdf` require
optional dependencies:

```sh
pip install 'github-usage[export-xlsx]'   # adds openpyxl
pip install 'github-usage[export-pdf]'    # adds fpdf2
```

`--export xlsx` and `--export pdf` produce a clear error with the install
hint when the dependency is missing. PEP 621 does not support a combined
`export` extra.

### Historical month queries

A `--month YYYY-MM` flag for fetching historical billing data is planned but
**deferred**. API discovery (see [`docs/api-discovery-month.md`](api-discovery-month.md))
confirmed that GitHub's billing endpoints ignore the `since`/`until`
parameters and return the same shape with or without them, so historical
queries are not feasible with the current GitHub API.

## Privacy

This tool prints account, repository, billing, and usage details to stdout. Treat generated output as sensitive unless you have reviewed and redacted it. Do not commit tokens, raw private API responses, generated billing reports, or local environment files.

Exported files go through a redaction layer that masks usernames, repository
names, email addresses, and dollar amounts before writing. The redaction is
applied only to the file content; interactive terminal output and the email
body are not redacted. See `src/github_usage/redact.py` for the exact
patterns.
