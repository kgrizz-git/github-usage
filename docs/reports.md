# Reports and exports

[Back to README](../README.md)

After [authenticating](setup.md#authentication), run a local full report with `./start.sh report` or preview an email report with `./start.sh email-report --dry-run`. For all command options, use `./start.sh report --help` and `./start.sh email-report --help`.

## API impact and billing interpretation

`--include-consumers`, `--include-artifact-storage`, and `--include-release-assets` add repo-level API calls. They consume GitHub REST API request quota, not Actions minutes, Actions storage, Copilot requests, Git LFS quota, or billable GitHub usage. Use monthly schedules and conservative `--max-repos` values for accounts with many repositories.

With `--include-consumers` (local full report and email), the **repo consumers** sections rank repositories by Actions usage alongside the existing combined top-by-minutes and top-by-cost lists:

- **Overall top-by-storage** — billed Actions storage ranked by average MB (`storage_avg_mb` from the billing API).
- **Private-only top lists** — separate rankings for Actions minutes and billed storage among private and internal repos only (the quota-relevant slice). Shown only when they add signal beyond the combined list (for example, when public repos dominate the overall minutes ranking).
- **Minutes by workflow** — for the top private-repo minutes consumer, an estimated per-workflow breakdown from completed run wall-clock time (start→end). This is **not billable** GitHub data: it uses fractional run elapsed time, not per-job rounding or OS multipliers, so the estimated total **will not match** the billed repo minutes figure. The section is labeled accordingly in terminal and email output (not the TUI summary view).

The same consumer keys appear in JSON exports; dedicated CSV/XLSX/PDF columns for private rankings and workflow breakdown are planned (see `TO_DO.md`).

Repo-level sections annotate non-public repositories with `[private]` or `[internal]` tags. The local full report's per-repo Actions table groups rows by visibility with subtotals. `--only-public` and `--only-private` (mutually exclusive) filter which repositories are included in repo-level sections; filtering applies after the `--max-repos` limit. Set `only_public` / `only_private` in `[email_report]` (or `[reports.email_report]` for named profiles) in `config.toml` for scheduled runs.

**Free-tier quota is private-first.** Limits Summary, utilization, forecasts, TUI rows, and exports measure Actions minutes and artifact storage against the free tier for **private** (and internal) repos only. Public standard-runner usage is shown separately and labeled free. Larger-runner SKUs are marked `*` (always billed). Artifact storage frames the 500 MB private allowance as GB-hours accrual (0.5 GB flat all month ≈ 360 GB-hrs for a 30-day month), splits Actions artifacts from release assets (releases are not quota-billed), and flags soon-to-expire / expired artifacts (default retention 90 days). Repos beyond `--max-repos` may appear as unattributed remainder vs the account billing total. Reports include a Sources footer linking GitHub’s Actions billing, runner pricing, and release-storage docs.

Visibility matters for billing: GitHub Actions minutes and storage are **free for public repositories** but consume your plan's monthly quota for private and internal repositories. See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) for included amounts and overage rates.

Release assets are optional inventory, not a billing/quota report. The CLI asks for confirmation in interactive terminals, and CI must pass `--yes-include-release-assets`.

## Cached data and refresh

Local full reports and email reports can reuse snapshots in `.github-usage/cache/` (gitignored). The default cache lifetime is one hour, so a repeated report may show older data. To fetch fresh data:

```sh
./start.sh report --refresh
./start.sh email-report --dry-run --refresh
```

Set `GITHUB_USAGE_DISABLE_CACHE=1` to disable report caching. An optional `[cache]` section in local `config.toml` supports `max_age_seconds` (default `3600`, `0` disables caching). Setup rewrites the configuration without preserving `[cache]`, so reapply a custom setting after using setup or use the environment variable. Cached snapshots contain sensitive report data; keep them local.

## Exporting Reports

Both the local full report and email-report commands can write the report to a file in
CSV, XLSX, PDF, JSON, or plain text format. The local full report fetches data once
and uses it for both terminal output and export (lower GitHub API usage when
exporting). Export redaction is partial; see [Privacy](#privacy) before sharing files. Interactive terminal output and email bodies are not redacted.

```sh
# Local full report
./start.sh report --export csv --no-interactive --output report.csv
./start.sh report --export xlsx --no-interactive --output report.xlsx
./start.sh report --export pdf --no-interactive --output report.pdf
./start.sh report --json --no-interactive          # JSON to stdout
./start.sh report --json --no-interactive --output report.json

# Email report
./start.sh email-report --dry-run --export text --output report.txt
./start.sh email-report --export csv --output report.csv
```

`./start.sh report` (or `github-usage --cli`) enters the local full report flow. In an interactive terminal without `--export` or `--no-interactive`, this flow prompts for a format (or `None` to skip). Bare `github-usage` in a terminal opens the TUI, so use the explicit report/CLI invocation for exports.

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
scripts/python -m pip install -e '.[export-xlsx]'   # adds openpyxl
scripts/python -m pip install -e '.[export-pdf]'    # adds fpdf2
```

`--export xlsx` and `--export pdf` produce a clear error with the install
hint when the dependency is missing. This project provides separate extras; install both with `scripts/python -m pip install -e '.[export-xlsx,export-pdf]'` if needed.

### Historical month queries

A `--month YYYY-MM` flag for fetching historical billing data is planned but
**deferred**. API discovery (see [`docs/api-discovery-month.md`](api-discovery-month.md))
confirmed that GitHub's billing endpoints ignore the `since`/`until`
parameters and return the same shape with or without them, so historical
queries are not feasible with the current GitHub API.

## Privacy

This tool prints account, repository, billing, and usage details to stdout. Treat generated output as sensitive unless you have reviewed and redacted it. Do not commit tokens, raw private API responses, generated billing reports, or local environment files.

Redaction depends on the data passed to the exporter:

| Export path | What is masked | What can remain |
| --- | --- | --- |
| Structured report data (CSV, XLSX, PDF, JSON, and local full report text exports) | Top-level `username`, string values under `repo` keys, and dollar-formatted strings | Email addresses, names in other fields/free text, numeric cost values, and other usage details |
| Email report `--export text` (an already formatted body) | Email addresses and dollar-formatted amounts | Usernames, repository names, and other report details |

This is not anonymization. Review and redact the entire output before sharing. Redaction applies to content only; default filenames can include the username (`reports/github-usage-<username>-<date>.<ext>`). Use an explicit neutral `--output` path when needed. Terminal output and delivered email bodies remain unredacted. See [redaction implementation](../src/github_usage/redact.py) for the exact patterns.
