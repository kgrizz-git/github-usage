# Scheduled Email Usage Reports Implementation Plan

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
| `src/github_usage/report_data.py` | Report collection functions that return dicts. No stdout/stderr output and no filesystem writes. GitHub API calls happen through the injected API client. |
| `src/github_usage/email_report.py` | Resend API client and plain-text email body formatting. |
| `.github/workflows/email-report.yml` | Workflow template users copy into their repos. |

### Modified files

| File | Change |
|------|--------|
| `src/github_usage/cli.py` | Add `email-report` subcommand |
| `src/github_usage/legacy.py` | Reuse existing API client and collectors where practical; only extract shared data helpers after command routing and tests are in place |
| `src/github_usage/__main__.py` | Ensure `email-report` subcommand is reachable via `python -m github_usage email-report` |
| `pyproject.toml` | No new dependencies planned — Resend is called via raw `http.client` (same as existing code) |
| `README.md` | Document the email report feature and GitHub Actions setup |
| `TO_DO.md` | Update roadmap status after implementation rather than adding duplicate stale work |

---

## Architecture

```
cli.py
  └── email-report subcommand
        ├── report_data.py   (collects enabled sections: actions minutes/storage, copilot requests, LFS, per-repo breakdown, per-SKU costs)
        ├── email_report.py  (formats -> plain text body, calls Resend API)
```

### `report_data.py`

Functions return dicts and avoid stdout/stderr, filesystem writes, and process exits. They are not mathematically pure because they call GitHub through the injected API client, but tests can use fake API clients and fixture responses.

Start with narrow wrappers around the existing `legacy.py` collectors, with signatures adapted to return dicts instead of printing or returning tuples. Broader `legacy.py` decomposition belongs in a follow-up after this feature has focused test coverage.

- `get_actions_usage(api, username) -> dict` — aggregates minutes, storage_gb_hours, sku_breakdown, limits. Wraps `get_user_actions_billing()` initially. Skip when `--skip-actions` is set.
- `get_copilot_usage(api, username) -> dict` — total requests, by-model breakdown, costs. Wraps `get_billing_summary(..., "Copilot")` and `get_premium_request_usage()`. Skip when `--skip-copilot` is set.
- `get_gitlfs_usage(api, username) -> dict` — storage, costs. Wraps `get_billing_summary(..., "git_lfs")`. Skip when `--skip-lfs` is set.
- `get_repo_consumers(api, repos, limit=5) -> list[dict]` — top repos by minutes and cost. Use only when `--include-consumers` is set.
- `get_monthly_costs(api, username) -> dict` — gross, discount, net by category.
- `get_key_insights(report_data) -> dict` — top 3 findings + recommendations. Add only when the source data is already collected.
- `get_warning_state(report_data, warn_over) -> dict` — evaluates optional spend thresholds and returns warning copy for the email header.

### CLI command routing

The current CLI treats the first positional argument as a token before handing off to `legacy.main()`. The first implementation task must add real command routing so `github-usage email-report` is not interpreted as a GitHub token.

Use `argparse` or a small equivalent parser with these behaviors:

- `github-usage`, `github-usage <token>`, and `github-usage-v3 <token>` preserve current report behavior.
- `github-usage --help` prints top-level help without resolving a token.
- `github-usage email-report --help` prints email-report help without resolving a token.
- `github-usage email-report --dry-run` resolves only `GITHUB_TOKEN`; it does not require `RESEND_API_KEY`, `REPORT_EMAIL`, or `RESEND_FROM`.
- `github-usage email-report` resolves `GITHUB_TOKEN`, `RESEND_API_KEY`, `REPORT_EMAIL`, and `RESEND_FROM`, then exits with a clear nonzero error if any required value is missing.
- `python -m github_usage email-report` follows the same path through `src/github_usage/__main__.py`.
- `github-usage email-report --skip-actions --skip-copilot --skip-lfs` exits with a clear error because every report section has been disabled.

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
8. **Key Insights** — top 3 findings + recommendations

Sections 6-8 are optional, controlled by a `--include-consumers` flag on the CLI. Actions, Copilot, and Git LFS sections can be disabled with section-specific skip flags.

---

## CLI Interface

```
github-usage email-report [--include-consumers] [--dry-run] [--warn-over VALUE] [--skip-actions] [--skip-copilot] [--skip-lfs]

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
- `--dry-run` — print the formatted email body to stdout without sending. Useful for local testing.
- `--warn-over VALUE` — add a warning banner when the current monthly net cost exceeds a threshold. Accept dollar thresholds like `25` or `$25`, and percentage thresholds like `80%` for Actions free-tier usage.
- `--skip-actions` — omit Actions API calls and Actions sections.
- `--skip-copilot` — omit Copilot API calls and Copilot sections.
- `--skip-lfs` — omit Git LFS API calls and Git LFS sections.

`--month YYYY-MM` is intentionally deferred from the first implementation. Current helpers assume the current calendar month, and this plan should not promise historical reports until the exact GitHub billing API parameters or response filtering rules are defined and tested.

**Partial failure handling:** If one optional billing endpoint fails after account authentication succeeds (e.g., Copilot is unavailable), the email includes a placeholder note (`"[Copilot data unavailable - token may lack billing scope]"`) and the command continues. Authentication failures, missing required environment variables, invalid email configuration, and Resend send failures should abort with a nonzero exit.

**Rate limit warning:** The report queries `/user/repos` then billing per repo. For users with many repos, this can approach the 5000/hour GitHub API limit. The plan notes this in the docs and recommends the workflow run on a low-frequency schedule.

### Troubleshooting docs

README updates should include a troubleshooting section with these cases:

- Missing GitHub `user` scope: billing endpoints may return 404; fix with `gh auth refresh -h github.com -s user` or a PAT with the right scope.
- GitHub Actions token confusion: use `GH_USAGE_TOKEN`, not the automatic `GITHUB_TOKEN`.
- Resend domain unverified: set `RESEND_FROM` to an address on a verified domain.
- Rate limiting: reduce frequency, avoid `--include-consumers`, or use skip flags to reduce API calls.
- No data for a product: use `--skip-copilot`, `--skip-actions`, or `--skip-lfs` when the account does not use that feature.

---

## Testing

- Unit tests for `report_data.py` functions with mock API responses
- Unit tests for `email_report.format_report_email()` with fixture data
- Unit tests for `email_report.send_email()` with mocked `http.client`
- Unit tests that `send_email()` closes the connection and includes the sanitized response body on non-2xx errors
- Unit tests for partial API failure (one endpoint returns None, others succeed)
- CLI tests for top-level help, `email-report --help`, `email-report --dry-run`, `email-report --dry-run --include-consumers`, missing Resend env vars, and the legacy positional token path
- CLI tests for `--warn-over` dollar and percentage thresholds
- CLI tests for each skip flag and for the error case where all product sections are skipped
- Workflow-template docs test to ensure the example uses `GH_USAGE_TOKEN` instead of `${{ secrets.GITHUB_TOKEN }}`
- Workflow-template docs test to ensure the example includes `concurrency` and `workflow_dispatch` inputs
- No live Resend calls in tests
- Follows existing test conventions (unittest, mocks, fixtures)
- One optional live test path gated behind `GITHUB_USAGE_LIVE_TESTS=1`

---

## Implementation Order

- [ ] Add CLI parser tests for preserving current behavior and recognizing `email-report` as a subcommand before token resolution.
- [ ] Implement command routing in `src/github_usage/cli.py`; keep `src/github_usage/__main__.py` as the shared entrypoint.
- [ ] Add `src/github_usage/email_report.py` with `format_report_email()` and `send_email()`, including non-2xx response handling and connection closing.
- [ ] Add focused tests for `email_report.py` formatting, sending, and error paths.
- [ ] Add `src/github_usage/report_data.py` as a narrow wrapper around existing collectors, with fake API-client tests.
- [ ] Add `email-report` CLI orchestration with `--include-consumers`, `--dry-run`, `--warn-over`, `--skip-actions`, `--skip-copilot`, and `--skip-lfs`; do not add `--month` in the first pass.
- [ ] Add CLI tests for missing environment variables, dry-run behavior, dry-run with consumers, warning thresholds, skip flags, partial data failures, and send failures.
- [ ] Add `.github/workflows/email-report.yml` workflow template using `GH_USAGE_TOKEN`, `concurrency`, and manual dispatch inputs for `include_consumers` and `report_email`.
- [ ] Update README with setup instructions, token-scope warning, dry-run example, Resend verified-domain requirement, skip flags, warning thresholds, and troubleshooting.
- [ ] Update `TO_DO.md` only to remove or revise roadmap items made obsolete by this feature; keep the separate historical `--month YYYY-MM` item unless implemented.
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

---

## Open Questions

1. **Reusable workflow vs copy-paste**: The workflow in `.github/workflows/email-report.yml` is a standalone template users copy into their own repos. This is simpler for first-time users. A reusable workflow (`uses: kgrizz-git/github-usage/.github/workflows/email-report.yml@vX`) could be added later once the interface stabilizes.

2. **Local execution**: The `email-report` command works anywhere with `GITHUB_TOKEN` and `RESEND_API_KEY` set — not just in CI. This lets users test it locally before wiring up the schedule.

3. **Email body completeness**: The email body is the complete report. The full interactive report is still available via the existing `github-usage` command for deep dives.

4. **Email provider extensibility**: The email client abstraction in `email_report.py` can be extended later for SendGrid, Postmark, AWS SES, etc. by adding a new provider module and a `--provider` flag.

5. **Report period**: The email report uses the current calendar month by default. Historical reports remain a separate roadmap item until the exact GitHub billing API query/filter behavior is specified and tested.
