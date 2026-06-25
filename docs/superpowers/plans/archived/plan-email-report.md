# Scheduled Email Usage Reports Implementation Plan

> **Status:** COMPLETE
>
> **Done (2026-06-25):** Implemented — `src/github_usage/email_report.py` exists and the `github-usage email-report` CLI subcommand works (Resend delivery, scheduled runner, GitHub Actions template). Archived from `docs/plan-email-report.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scheduled plain-text GitHub billing email report that can run locally or from GitHub Actions without exposing tokens or generated reports.

**Architecture:** Add a real CLI command router first so `email-report` is parsed as a subcommand instead of a token. Keep report collection separate from report rendering and email delivery, with GitHub API and Resend clients injected or mocked in tests.

**Tech Stack:** Python 3.11+, stdlib `argparse`/`http.client`/`json`, existing `legacy.GitHubAPI`, GitHub Actions, Resend email API.

---

## Overview

Add a CLI subcommand (`github-usage email-report`) that collects billing data, formats it as a plain-text email body, optionally adds warning banners for high spend, and sends it via Resend.dev. Package this as a GitHub Actions workflow users can copy into their own repos to run on a configurable schedule.

---

## User Setup

The user needs to configure four things:

1. **GitHub token** → a personal access token with the `user` scope, stored as `GH_USAGE_TOKEN` in GitHub Actions secrets and mapped to `GITHUB_TOKEN` at runtime
2. **Resend.dev API key** → stored in `RESEND_API_KEY` secret or env var
3. **Recipient email** → stored in `REPORT_EMAIL` secret or env var
4. **Schedule** → weekly, monthly, or custom cron expression (configurable in the workflow file)

A note in the docs will mention that other email providers (SendGrid, Postmark, AWS SES, etc.) can be added later by swapping the email client module.

**Important:** Resend requires a verified sending domain. The docs will instruct users to add a domain in the Resend dashboard and set `RESEND_FROM` to an address on that domain (e.g., `reports@myverifieddomain.com`). The default `noreply@github-usage.example` will not work with Resend.

**Important:** The GitHub Actions-provided `${{ github.token }}` / `${{ secrets.GITHUB_TOKEN }}` cannot be used for this report because billing endpoints require a user-scoped token. GitHub also reserves the `GITHUB_` secret prefix for Actions internals, so users should create a repository secret named `GH_USAGE_TOKEN` and the workflow should expose it to the CLI as `GITHUB_TOKEN`.

### Configuration Matrix

| Variable | Local execution | GitHub Actions | Required for `--dry-run` | Required for send |
|----------|-----------------|----------------|---------------------------|-------------------|
| `GITHUB_TOKEN` | Set directly, resolved by `gh auth token`, or config file fallback | Set from `${{ secrets.GH_USAGE_TOKEN }}` | Yes | Yes |
| `RESEND_API_KEY` | Set directly | `${{ secrets.RESEND_API_KEY }}` | No | Yes |
| `REPORT_EMAIL` | Set directly | `${{ secrets.REPORT_EMAIL }}` | No | Yes |
| `RESEND_FROM` | Set directly | `${{ secrets.RESEND_FROM }}` | No | Yes |
| `REPORT_SUBJECT` | Optional | Optional secret or env var | No | No |

---

## File Changes

### New files

| File | Purpose |
|------|---------|
| `src/github_usage/report_helpers.py` | Shared formatting and month helpers extracted from `legacy.py`: `hours_in_month()`, `gb_hours_to_avg_mb()`, and `fmt_price()`. |
| `src/github_usage/report_data.py` | Report collection functions that return dicts. No stdout/stderr output and no filesystem writes. GitHub API calls happen through the injected API client. |
| `src/github_usage/email_report.py` | Resend API client and plain-text email body formatting. |
| `.github/workflows/email-report.yml` | Workflow template users copy into their repos. |
| `tests/fixtures/` | Sanitized sample API responses for Actions, Copilot, Git LFS, premium requests, `/user`, and `/user/repos`. |

### Modified files

| File | Change |
|------|--------|
| `src/github_usage/cli.py` | Add `email-report` subcommand |
| `src/github_usage/legacy.py` | Import shared helpers from `report_helpers.py`; reuse existing API client and collectors where practical |
| `src/github_usage/__main__.py` | Ensure `email-report` subcommand is reachable via `python -m github_usage email-report` |
| `pyproject.toml` | No new dependencies planned — Resend is called via raw `http.client` (same as existing code) |
| `README.md` | Document the email report feature and GitHub Actions setup |
| `TO_DO.md` | Update roadmap status after implementation rather than adding duplicate stale work |
| `CHANGELOG.md` | Add an `Added` entry for the email report command and workflow template |

---

## Architecture

```
cli.py
  └── email-report subcommand
        ├── report_helpers.py (shared date, storage, and money formatting helpers)
        ├── report_data.py    (collects enabled sections: actions minutes/storage, copilot requests, LFS, per-repo breakdown, storage analysis, per-SKU costs)
        ├── email_report.py   (formats -> plain text body, calls Resend API)
```

### API client contract

Use a small `typing.Protocol` in `report_data.py` instead of depending directly on the concrete `legacy.GitHubAPI` type:

```python
class GitHubAPIClient(Protocol):
    def request(self, method: str, path: str, params: dict[str, object] | None = None) -> object: ...
    def get_all_pages(self, path: str, params: dict[str, object] | None = None) -> list[dict[str, object]]: ...
```

Production code passes `legacy.GitHubAPI(token)`. Tests pass fakes that implement only these two methods.

### `report_helpers.py`

Extract these helpers from `legacy.py` so `legacy.py`, `report_data.py`, and `email_report.py` share behavior instead of duplicating formatting logic:

- `hours_in_month(reference_date: date | None = None) -> int`
- `gb_hours_to_avg_mb(gb_hours: float, reference_date: date | None = None) -> float`
- `fmt_price(value: float) -> str`

`legacy.hours_in_current_month()` can either become a thin compatibility wrapper around `hours_in_month()` or be replaced internally where practical.

### `report_data.py`

Functions return dicts and avoid stdout/stderr, filesystem writes, and process exits. They are not mathematically pure because they call GitHub through the injected API client, but tests can use fake API clients and fixture responses.

The CLI resolves `/user` once, stores `username = user["login"]`, calls `legacy.check_user_scope(api)` before any billing requests, and passes `username` into report-data functions. `report_data.py` should not resolve the username itself.

Start with narrow wrappers around the existing `legacy.py` collectors, with signatures adapted to return dicts instead of printing or returning tuples. Broader `legacy.py` decomposition belongs in a follow-up after this feature has focused test coverage.

- `get_actions_usage(api, username) -> dict` — aggregates minutes, storage_gb_hours, sku_breakdown, limits. Wraps `get_user_actions_billing()` initially. Skip when `--skip-actions` is set.
- `get_copilot_usage(api, username) -> dict` — total requests, by-model breakdown, costs. Wraps `get_billing_summary(..., "Copilot")` and `get_premium_request_usage()`. Skip when `--skip-copilot` is set.
- `get_gitlfs_usage(api, username) -> dict` — storage, costs. Wraps `get_billing_summary(..., "git_lfs")`. Skip when `--skip-lfs` is set.
- `get_repo_consumers(api, repos, limit=5, max_repos=100) -> list[dict]` — top repos by minutes and cost. Use only when `--include-consumers` is set. Inspect at most `max_repos` repositories to limit API calls.
- `get_artifact_storage_details(api, repos, max_repos=100) -> dict` — optional Actions artifact storage breakdown. Wraps the artifact half of `legacy.get_storage_analysis()` behavior, but only runs when `--include-artifact-storage` is set. Inspect at most `max_repos` repositories.
- `get_release_asset_details(api, repos, max_repos=100) -> dict` — optional release asset inventory. Wraps the release half of `legacy.get_storage_analysis()` behavior, but only runs when `--include-release-assets` is set and the user has explicitly confirmed it. Inspect at most `max_repos` repositories.
- `get_monthly_costs(api, username) -> dict` — gross, discount, net by category.
- `get_key_insights(report_data) -> dict` — top 3 findings + recommendations. Add only when the source data is already collected.
- `get_warning_state(report_data, warn_over) -> dict` — evaluates optional spend thresholds and returns warning copy for the email header.
- `estimate_api_request_count(repo_count, include_consumers, include_artifact_storage, include_release_assets, max_repos) -> dict` — estimates incremental REST API calls before expensive optional sections run.

Actions artifact details and release-asset inventory are optional because they add separate per-repository API calls. Include them behind explicit `--include-artifact-storage` and `--include-release-assets` flags, warn when estimated calls are high, and document that this consumes GitHub REST API request quota only. It does not consume GitHub Actions minutes, Actions storage quota, Copilot requests, Git LFS quota, or other billable GitHub usage.

Release assets are not part of the default storage report because they are not a quota/billing pressure point in the same way Actions storage or Git LFS are. GitHub's releases docs currently say a release can have up to 1000 assets, each asset must be under 2 GiB, and there is no total size or bandwidth limit for a release. Listing release assets still consumes REST API quota, so this report should describe release assets as optional inventory and ask the user to confirm that they actually want it.

### Report data schemas

Use these exact top-level keys so `format_report_email()` and tests have a stable contract:

```python
ReportData = {
    "username": str,
    "period": "current_month",
    "generated_at": str,  # UTC ISO-8601 timestamp
    "warnings": list[str],
    "errors": dict[str, str],
    "actions": ActionsUsage | None,
    "copilot": CopilotUsage | None,
    "git_lfs": GitLfsUsage | None,
    "monthly_costs": MonthlyCosts,
    "repo_consumers": RepoConsumers | None,
    "artifact_storage": ArtifactStorageDetails | None,
    "release_assets": ReleaseAssetDetails | None,
    "api_estimate": ApiEstimate,
    "insights": list[str],
}
```

`ActionsUsage`:

```python
{
    "minutes": float,
    "minutes_limit": 2000,
    "minutes_percent": float,
    "storage_gb_hours": float,
    "storage_avg_mb": float,
    "storage_limit_mb": 500,
    "storage_percent": float,
    "sku_breakdown": dict[str, dict[str, object]],
}
```

`CopilotUsage`:

```python
{
    "total_requests": float,
    "total_gross": float,
    "total_discount": float,
    "total_net": float,
    "by_model": dict[str, dict[str, float]],
}
```

`GitLfsUsage`:

```python
{
    "total_gross": float,
    "total_discount": float,
    "total_net": float,
    "items": dict[str, dict[str, object]],
}
```

`MonthlyCosts`:

```python
{
    "actions": {"gross": float, "discount": float, "net": float},
    "copilot": {"gross": float, "discount": float, "net": float},
    "git_lfs": {"gross": float, "discount": float, "net": float},
    "total": {"gross": float, "discount": float, "net": float},
}
```

`RepoConsumers`:

```python
{
    "scanned_repo_count": int,
    "max_repos": int,
    "truncated": bool,
    "by_minutes": list[{"repo": str, "minutes": float, "gross": float, "storage_avg_mb": float}],
    "by_cost": list[{"repo": str, "minutes": float, "gross": float, "storage_avg_mb": float}],
}
```

`ArtifactStorageDetails`:

```python
{
    "scanned_repo_count": int,
    "max_repos": int,
    "truncated": bool,
    "top_repos": list[{"repo": str, "artifact_bytes": int}],
}
```

`ReleaseAssetDetails`:

```python
{
    "scanned_repo_count": int,
    "max_repos": int,
    "truncated": bool,
    "top_repos": list[{"repo": str, "release_asset_bytes": int}],
}
```

`ApiEstimate`:

```python
{
    "core_limit": int | None,
    "core_remaining": int | None,
    "estimated_incremental_requests": int,
    "estimated_percent_of_remaining": float | None,
    "repos_considered": int,
    "notes": list[str],
}
```

Section failures are captured in `errors` using stable keys such as `"actions"`, `"copilot"`, `"git_lfs"`, `"repo_consumers"`, and `"send"`.

### CLI command routing

The current CLI treats the first positional argument as a token before handing off to `legacy.main()`. The first implementation task must add real command routing so `github-usage email-report` is not interpreted as a GitHub token.

Use `argparse` or a small equivalent parser with these behaviors:

- `github-usage` and `github-usage <token>` preserve current report behavior.
- `github-usage --help` prints top-level help without resolving a token.
- `github-usage email-report --help` prints email-report help without resolving a token.
- `github-usage email-report --dry-run` resolves only `GITHUB_TOKEN`; it does not require `RESEND_API_KEY`, `REPORT_EMAIL`, or `RESEND_FROM`.
- `github-usage email-report` resolves `GITHUB_TOKEN`, `RESEND_API_KEY`, `REPORT_EMAIL`, and `RESEND_FROM`, then exits with a clear nonzero error if any required value is missing.
- `python -m github_usage email-report` follows the same path through `src/github_usage/__main__.py`.
- `github-usage email-report --skip-actions --skip-copilot --skip-lfs` exits with a clear error unless `--include-artifact-storage` is set, because every default report section has been disabled. `--include-release-assets` alone is not enough because release assets are inventory, not a billing/quota report.
- `github-usage email-report --include-release-assets` in an interactive terminal prints a short explanation that release assets do not have a documented total release size/bandwidth quota and asks the user to confirm before continuing. In CI/non-interactive runs, require `--yes-include-release-assets`; otherwise exit with a clear message.
- Before billing collection, the command calls `legacy.check_user_scope(api)` and exits with the existing scope guidance if the token lacks `user`.

### `email_report.py`

Two responsibilities:

1. **`format_report_email(data: dict) -> str`** — formats the report dict into a plain-text email body with sections for each metric
2. **`send_email(api_key: str, from_addr: str, to_addr: str, subject: str, body: str) -> None`** — POST to `https://api.resend.com/emails`

Resend API call (no external dependency — uses stdlib `http.client`, consistent with `legacy.py`):

```python
import http.client
import json

def send_email(api_key: str, from_addr: str, to_addr: str, subject: str, body: str) -> None:
    payload = json.dumps({
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    })
    conn = http.client.HTTPSConnection("api.resend.com")
    conn.request("POST", "/emails", body=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    try:
        resp = conn.getresponse()
        response_body = resp.read().decode("utf-8", errors="replace")
    finally:
        conn.close()
    if resp.status not in (200, 201):
        raise RuntimeError(f"Resend API error {resp.status}: {response_body[:300]}")
```

Default subject when `REPORT_SUBJECT` is unset:

```text
GitHub Usage Report for {username} - {YYYY-MM-DD}
```

### `email-report.yml`

A workflow with:

- `on: schedule` with a cron expression (user-configurable)
- Steps: checkout, set up Python, install deps, run `github-usage email-report`
- Secrets: `GH_USAGE_TOKEN`, `RESEND_API_KEY`, `REPORT_EMAIL`, `RESEND_FROM`

```yaml
name: GitHub Usage Report

on:
  schedule:
    # Every Monday at 9am UTC (user-configurable)
    - cron: '0 9 * * 1'
  workflow_dispatch:
    inputs:
      include_consumers:
        description: Include top repository breakdowns and key insights
        required: false
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'
      include_artifact_storage:
        description: Include Actions artifact storage details; this may use many REST API requests
        required: false
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'
      include_release_assets:
        description: Include release asset inventory; this is not a billing/quota report and may use many REST API requests
        required: false
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'
      report_email:
        description: Override the REPORT_EMAIL secret for this manual run
        required: false
        type: string

concurrency:
  group: github-usage-email-report
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e .
      - name: Send email report
        env:
          GITHUB_TOKEN: ${{ secrets.GH_USAGE_TOKEN }}
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          REPORT_EMAIL: ${{ inputs.report_email || secrets.REPORT_EMAIL }}
          RESEND_FROM: ${{ secrets.RESEND_FROM }}
        run: |
          args=()
          if [ "${{ inputs.include_consumers }}" = "true" ]; then
            args+=(--include-consumers)
          fi
          if [ "${{ inputs.include_artifact_storage }}" = "true" ]; then
            args+=(--include-artifact-storage)
          fi
          if [ "${{ inputs.include_release_assets }}" = "true" ]; then
            args+=(--include-release-assets --yes-include-release-assets)
          fi
          python -m github_usage email-report "${args[@]}"
```

---

## Report Content in Email

The email body will be plain text (no HTML) and include:

1. **Warning Banner** — optional, shown only when `--warn-over` threshold is exceeded
1. **Actions Minutes** — used / limit, percentage of free tier
2. **Actions Storage** — avg MB used / 500 MB limit, percentage
3. **Copilot Premium Requests** — total, by model
4. **Git LFS** — usage and cost
5. **Monthly Cost Estimate** — gross, discount, net by category
6. **Top 5 Repos by Actions Minutes** (optional)
7. **Top 5 Repos by Actions Cost** (optional)
8. **Actions Artifact Storage** (optional)
9. **Release Asset Inventory** (optional)
10. **Key Insights** — top 3 findings + recommendations

Sections 6-7 are optional, controlled by a `--include-consumers` flag on the CLI. Section 8 is optional, controlled by `--include-artifact-storage`. Section 9 is optional inventory, controlled by `--include-release-assets` plus confirmation. Actions, Copilot, and Git LFS sections can be disabled with section-specific skip flags.

### Plain-text email template

Use this as the formatter target shape. Omit skipped sections, and replace failed optional sections with the corresponding unavailable note.

```text
GitHub Usage Report for octocat
Generated: 2026-06-15 14:30 UTC
Period: current month

WARNING
- Current monthly net cost is $31.42, above the $25.00 threshold.

Actions
- Minutes: 1,250.0 / 2,000 (62.5%)
- Storage: 220.4 MB / 500 MB (44.1%)
- Net cost: $4.2100

Copilot Premium Requests
- Total requests: 42.0
- Net cost: $0.0000
- By model:
  - gpt-4.1: 30.0 requests
  - claude-sonnet-4: 12.0 requests

Git LFS
- Net cost: $0.0000

Monthly Cost Estimate
- Actions: gross $6.1000, discount $1.8900, net $4.2100
- Copilot: gross $0.0000, discount $0.0000, net $0.0000
- Git LFS: gross $0.0000, discount $0.0000, net $0.0000
- Total: gross $6.1000, discount $1.8900, net $4.2100

Top Repositories by Actions Minutes
- octocat/api: 900.0 min, $3.4000, 180.0 MB avg storage
- octocat/web: 350.0 min, $0.8100, 40.4 MB avg storage

Top Repositories by Actions Cost
- octocat/api: $3.4000, 900.0 min, 180.0 MB avg storage
- octocat/web: $0.8100, 350.0 min, 40.4 MB avg storage

Actions Artifact Storage
- octocat/api: 900.0 MB artifacts
- octocat/web: 100.0 MB artifacts

Release Asset Inventory
- octocat/api: 300.0 MB release assets
- octocat/web: 20.0 MB release assets

Key Insights
- octocat/api accounts for 72% of Actions minutes.
- Actions storage is below the free-tier limit.

Unavailable Data
- Copilot data unavailable - token may lack billing scope.
```

---

## CLI Interface

```
github-usage email-report [--include-consumers] [--include-artifact-storage] [--include-release-assets] [--yes-include-release-assets] [--max-repos N] [--dry-run] [--warn-over VALUE] [--skip-actions] [--skip-copilot] [--skip-lfs]

Environment variables:
  GITHUB_TOKEN    GitHub token (same resolution as existing CLI)
  RESEND_API_KEY  Resend.dev API key
  REPORT_EMAIL    Recipient email address
  RESEND_FROM     Sender address (must be on a verified Resend domain; required)
  REPORT_SUBJECT  Optional subject override
```

The `email-report` subcommand checks for the required env vars and exits with a clear error if any are missing.

Flags:

- `--include-consumers` — include top-repo breakdowns and key insights (sections 6-8 above). Default is off for shorter emails.
- `--include-artifact-storage` — include per-repository Actions artifact storage details. This is opt-in because it may use roughly one additional REST API request per scanned repository, plus pagination for repos with many artifacts.
- `--include-release-assets` — include per-repository release asset inventory. This is not a billing/quota report; it is opt-in because it may use roughly one additional REST API request per scanned repository, plus pagination for repos with many releases/assets. Release assets have per-release/per-asset limits, but GitHub currently documents no total release size or bandwidth limit.
- `--yes-include-release-assets` — required with `--include-release-assets` in non-interactive contexts. Interactive runs should prompt instead of requiring this flag.
- `--max-repos N` — when `--include-consumers`, `--include-artifact-storage`, or `--include-release-assets` is set, inspect at most `N` repositories from `/user/repos`; default `100`, minimum `1`.
- `--dry-run` — print the formatted email body to stdout without sending. Useful for local testing.
- `--warn-over VALUE` — add a warning banner when the current monthly net cost exceeds a threshold. Accept dollar thresholds like `25` or `$25`, and percentage thresholds like `80%` for Actions free-tier usage.
- `--skip-actions` — omit Actions API calls and Actions sections.
- `--skip-copilot` — omit Copilot API calls and Copilot sections.
- `--skip-lfs` — omit Git LFS API calls and Git LFS sections.

`--month YYYY-MM` is intentionally deferred from the first implementation. Current helpers assume the current calendar month, and this plan should not promise historical reports until the exact GitHub billing API parameters or response filtering rules are defined and tested.

**Warning threshold logic:** Dollar thresholds compare against `report_data["monthly_costs"]["total"]["net"]`. Percentage thresholds compare against Actions minutes free-tier usage when Actions data is enabled. If Actions is skipped or unavailable and a percentage threshold is supplied, exit with a clear error explaining that percentage thresholds require Actions data.

**Partial failure handling:** If one optional billing endpoint fails after account authentication succeeds (e.g., Copilot is unavailable), the command records the exception message in `report_data["errors"]`, renders an inline unavailable note for that section, adds the section to the `Unavailable Data` footer, and continues. Authentication failures, missing required environment variables, invalid email configuration, invalid flag combinations, and Resend send failures should abort with a nonzero exit.

**REST API quota guidance:** Optional repo-level sections consume GitHub REST API request quota. Current GitHub docs say authenticated user/PAT requests generally count against a 5,000 requests/hour personal REST API limit, while the built-in Actions `GITHUB_TOKEN` has a 1,000 requests/hour/repository limit. Most REST `GET` requests cost one secondary-rate-limit point. The report should call `/rate_limit` during dry-run/configuration or before optional repo-heavy sections, show the current core limit/remaining count when available, and estimate incremental calls:

- Base email report: low request count; no per-repo artifact/release calls.
- `--include-consumers`: approximately one billing summary request per scanned repository, plus paginated `/user/repos`.
- `--include-artifact-storage`: approximately one additional request per scanned repository (`actions/artifacts`), plus pagination within that endpoint for repos with many artifacts.
- `--include-release-assets`: approximately one additional request per scanned repository (`releases`), plus pagination within that endpoint for repos with many releases/assets. This is inventory only and should not be presented as limited/billable storage usage.
- All three repo-level options with `--max-repos 100`: roughly 300 extra requests plus repository-list pagination in the common case.

This quota usage does not draw down GitHub Actions minutes, Actions storage, Git LFS quota, Copilot quota, or paid billing resources. It can temporarily exhaust REST API quota for the token and disrupt other automation using the same token until the rate-limit window resets. Docs should recommend monthly schedules for reports with repo-level details, especially for accounts with many repositories.

**Rate limit warning behavior:** Cap scanning with `--max-repos` and include a footer note when the repo list was truncated. If the estimated incremental requests exceed 50% of remaining core quota, print a warning before sending in local runs and include a warning in the email. In non-interactive CI, do not prompt; continue unless remaining quota is already below the estimated incremental request count, in which case fail with a clear message recommending lower `--max-repos`, monthly scheduling, or disabling repo-level sections.

### Troubleshooting docs

README updates should include a troubleshooting section with these cases:

- Missing GitHub `user` scope: billing endpoints may return 404; fix with `gh auth refresh -h github.com -s user` or a PAT with the right scope.
- GitHub Actions token confusion: use `GH_USAGE_TOKEN`, not the automatic `GITHUB_TOKEN`.
- Resend domain unverified: set `RESEND_FROM` to an address on a verified domain.
- Rate limiting: reduce frequency, avoid `--include-consumers`, or use skip flags to reduce API calls.
- Consumer breakdown truncation: increase `--max-repos` cautiously if the account has many repositories.
- Artifact storage request cost: `--include-artifact-storage` can add roughly one REST API request per scanned repository and should normally be used in monthly reports.
- Release asset inventory: `--include-release-assets` can add roughly one REST API request per scanned repository. Release assets do not have a documented total release storage/bandwidth quota, so the CLI asks for explicit confirmation before including them.
- No data for a product: use `--skip-copilot`, `--skip-actions`, or `--skip-lfs` when the account does not use that feature.

---

## Testing

Create or update these test files:

- `tests/test_cli.py` — top-level help, `email-report --help`, `email-report --dry-run`, `email-report --dry-run --include-consumers`, `email-report --dry-run --include-artifact-storage`, `email-report --dry-run --include-release-assets`, release-asset confirmation behavior, missing Resend env vars, legacy positional token path, scope-check failure, skip flags, `--max-repos`, and invalid flag combinations.
- `tests/test_report_data.py` — report schemas, username-required collectors, fake API-client behavior, partial endpoint failures, warning threshold evaluation, repo-consumer truncation, artifact/release truncation, and API-request estimates.
- `tests/test_email_report.py` — plain-text formatter output from fixture data, default subject generation, Resend send success, connection closing, and non-2xx error body handling.
- `tests/test_docs.py` or `tests/test_workflow_templates.py` — workflow template assertions for `GH_USAGE_TOKEN`, `concurrency`, and `workflow_dispatch` inputs.

Create `tests/fixtures/` with sanitized JSON fixtures:

- `user.json`
- `repos.json`
- `billing_actions_summary.json`
- `billing_copilot_summary.json`
- `premium_request_usage.json`
- `billing_git_lfs_summary.json`
- `artifacts.json`
- `releases.json`
- `rate_limit.json`
- `email_report_data.json`

Coverage requirements:

- Unit tests for `report_data.py` functions with fixture-backed fake API responses
- Unit tests for `email_report.format_report_email()` with fixture data
- Unit tests for `email_report.send_email()` with mocked `http.client`
- Unit tests that `send_email()` closes the connection and includes the sanitized response body on non-2xx errors
- Unit tests for partial API failure (one endpoint returns None, others succeed)
- CLI tests for `--warn-over` dollar and percentage thresholds
- CLI tests for each skip flag and for the error case where all product sections are skipped
- CLI tests that `--max-repos` caps per-repository billing calls
- CLI tests that `--include-artifact-storage` and `--include-release-assets` estimate request usage independently and respect `--max-repos`
- CLI tests that `--include-release-assets` prompts in interactive mode and requires `--yes-include-release-assets` in non-interactive mode
- CLI tests for the low-remaining-quota failure path before optional repo-heavy sections run
- Workflow-template docs test to ensure the example uses `GH_USAGE_TOKEN` instead of `${{ secrets.GITHUB_TOKEN }}`
- Workflow-template docs test to ensure the example includes `concurrency` and `workflow_dispatch` inputs
- No live Resend calls in tests
- Follows existing test conventions (unittest, mocks, fixtures)
- One optional live test path gated behind `GITHUB_USAGE_LIVE_TESTS=1`

---

## Implementation Order

- [ ] Create `tests/fixtures/` with sanitized sample GitHub billing, premium request, user, repo, artifact, release, rate-limit, and rendered report data.
- [ ] Add CLI parser tests for preserving current behavior and recognizing `email-report` as a subcommand before token resolution.
- [ ] Add `src/github_usage/report_helpers.py`; update `legacy.py` to reuse shared helpers without changing legacy report output.
- [ ] Implement command routing in `src/github_usage/cli.py`; keep `src/github_usage/__main__.py` as the shared entrypoint.
- [ ] Add `src/github_usage/email_report.py` with `format_report_email()` and `send_email()`, including non-2xx response handling and connection closing.
- [ ] Add focused tests for `email_report.py` formatting, sending, and error paths.
- [ ] Add `src/github_usage/report_data.py` as a narrow wrapper around existing collectors, with the schemas defined in this plan and fake API-client tests.
- [ ] Add username resolution and early `legacy.check_user_scope(api)` handling for `email-report`.
- [ ] Add optional artifact storage collection and release-asset inventory with `--include-artifact-storage`, `--include-release-assets`, release-asset confirmation, request estimates, rate-limit checks, and `--max-repos` truncation.
- [ ] Add `email-report` CLI orchestration with `--include-consumers`, `--include-artifact-storage`, `--include-release-assets`, `--yes-include-release-assets`, `--max-repos`, `--dry-run`, `--warn-over`, `--skip-actions`, `--skip-copilot`, and `--skip-lfs`; do not add `--month` in the first pass.
- [ ] Add CLI tests for missing environment variables, dry-run behavior, dry-run with consumers, dry-run with artifact storage, dry-run with release assets, warning thresholds, skip flags, max-repo truncation, low-quota failure, partial data failures, and send failures.
- [ ] Add `.github/workflows/email-report.yml` workflow template using `GH_USAGE_TOKEN`, `concurrency`, and manual dispatch inputs for `include_consumers`, `include_artifact_storage`, `include_release_assets`, and `report_email`.
- [ ] Update README with setup instructions, token-scope warning, REST API quota guidance, monthly repo-detail scheduling recommendation, release-asset inventory explanation/confirmation, dry-run example, Resend verified-domain requirement, skip flags, warning thresholds, and troubleshooting.
- [ ] Update `TO_DO.md` only to remove or revise roadmap items made obsolete by this feature; keep the separate historical `--month YYYY-MM` item unless implemented.
- [ ] Update `CHANGELOG.md` with an `Added` entry for `github-usage email-report` and the workflow template.
- [ ] Run `scripts/check` to verify.
- [ ] Run `scripts/smoke` after CLI entrypoint changes.
- [ ] Run `scripts/docs-check` after README/docs/workflow changes.

---

## Deferred Enhancements

These are intentionally out of scope for the first email-report implementation and should be tracked in `TO_DO.md`:

- `--month YYYY-MM` after the GitHub billing API period/filter behavior is specified and tested.
- Month-over-month and year-over-year comparisons after historical report data is available.
- End-of-month spend projection after date/period handling is reliable.
- `--output PATH` and export support for saving text reports, instead of adding a separate email-only attachment option.
- `--format text|html` after the plain-text formatter is stable.
- CC/BCC email delivery fields.
- Default API timeout and retry behavior, then optional `--timeout SECONDS` and `--max-retries N` flags if user control is still needed.
- Report retention to GitHub Releases, S3, or shared drives.
- Caching or persisting artifact/release snapshots so monthly reports can compare optional repo-level storage details over time.

---

## Open Questions

1. **Reusable workflow vs copy-paste**: The workflow in `.github/workflows/email-report.yml` is a standalone template users copy into their own repos. This is simpler for first-time users. A reusable workflow (`uses: kgrizz-git/github-usage/.github/workflows/email-report.yml@vX`) could be added later once the interface stabilizes.

2. **Local execution**: The `email-report` command works anywhere with `GITHUB_TOKEN` and `RESEND_API_KEY` set — not just in CI. This lets users test it locally before wiring up the schedule.

3. **Email body completeness**: The email body is the complete report. The full interactive report is still available via the existing `github-usage` command for deep dives.

4. **Email provider extensibility**: The email client abstraction in `email_report.py` can be extended later for SendGrid, Postmark, AWS SES, etc. by adding a new provider module and a `--provider` flag.

5. **Report period**: The email report uses the current calendar month by default. Historical reports remain a separate roadmap item until the exact GitHub billing API query/filter behavior is specified and tested.
