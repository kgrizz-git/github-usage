# github-usage

[![CI](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml)
[![Security](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml)

`github-usage` helps individuals and small teams understand GitHub billing before it becomes a surprise. It turns current-month GitHub Actions, Copilot, Git LFS, and storage data into actionable local reports, exportable files, and scheduled email digests.

Run a local full report in the command line or Textual TUI, schedule delivery on a Mac with launchd, or have GitHub Actions and Resend send recurring email reports. The report keeps public Actions usage distinct from private and internal usage, where plan quotas and most costs apply.

## What it helps you answer

- Which private or internal repositories are consuming Actions minutes and storage?
- Is current usage likely to exceed this month's Actions, storage, or Copilot limits?
- Which repositories, workflows, artifacts, or release assets are the biggest contributors?
- Are my scheduled reports active, and do the local workflow files match the remote?

## Features

### Automated reporting

- Recurring scheduled email reports through GitHub Actions and Resend; HTML delivery includes a plain-text fallback
- Local macOS delivery through launchd, plus named report profiles for different audiences or schedules
- Guided setup for credentials, report options, schedules, GitHub Actions secrets, and verification
- Scheduled-run inventory and workflow-drift checks

### Cost and quota visibility

- Account and plan summary, billing history, and current-month net/gross cost estimate
- GitHub Actions minutes, storage, per-SKU costs, and private-first free-tier utilization
- Copilot premium requests by model and Git LFS usage
- End-of-month forecasts, run-out estimates, and configurable warning thresholds

### Actionable repository detail

- Visibility-aware repository tables, private-only rankings, and top resource consumers
- Estimated minutes by workflow for the largest private Actions consumer
- Optional artifact-storage and release-asset inventory, including retention and expiry signals

### Flexible outputs and interfaces

- Command-line reports and an optional Textual TUI for interactive use
- CSV, XLSX, PDF, JSON, and text exports; written exports are redacted
- Cached report data with explicit refresh controls to reduce repeat API calls

## Requirements

- Python 3.11 or newer
- A GitHub token authorized for your account's billing endpoints
- Optional: GitHub CLI (`gh`) for token discovery
- Optional for email reports: a Resend API key and verified sending domain

For a classic personal access token, use the `user` scope for user-level billing endpoints and add `repo` when analyzing private repositories; `repo` alone does not grant access to user billing endpoints. For a fine-grained token, select all relevant repositories, grant your user account's **Plan: Read-only** permission, and grant the repository permissions required by the report sections you enable: **Actions: Read-only** for runs and artifacts, and **Contents: Read-only** for release inventory. See [GitHub Actions secrets](#github-actions-secrets) for the scheduled-workflow setup. The core CLI runs wherever Python is available; local automated scheduling uses macOS launchd.

## Install and first report

For command-line reports from a checkout:

```sh
python3 -m pip install -e .
github-usage --cli --help
```

For the default interactive Textual TUI, install the GUI extra and run the command from an interactive terminal:

```sh
python3 -m pip install -e '.[gui]'
github-usage
```

You can also run without installing:

```sh
PYTHONPATH=src python3 -m github_usage --cli --help
PYTHONPATH=src python3 -m github_usage
```

The root-level `github-usage` file is a compatibility wrapper for the packaged CLI.

## Quick start: scheduled email reports

1. Install the package, then run the guided setup and choose **1** (*full setup*) from its menu:

   ```sh
   python3 -m pip install -e .
   ./start.sh setup
   ```

2. Configure your GitHub token, Resend API key, recipient, and verified sender. Preview each profile's email settings and report options before delivery; GitHub Actions schedule/default settings are configured separately:

   ```sh
   ./start.sh setup --verify
   ```

3. Choose a delivery model:
   - **GitHub Actions:** configure a UTC cron schedule, set the four required secrets, then commit, push, and merge the rendered workflow into the default branch. GitHub runs scheduled workflows only from that branch; on a fork, enable the workflow in the **Actions** tab after pushing. The checked-in workflow runs Mondays at 09:00 UTC and uses HTML with a plain-text fallback; the setup wizard defaults to text, so choose HTML in report options before rendering if you want the same format.
   - **macOS launchd:** choose a local day and time, then install the generated LaunchAgent. Your Mac must be available for the report to run.

Both options can be configured through `./start.sh setup`; they are independent, so you can use either or both.

## Setup and interfaces

Use one entry point to configure local secrets, named report profiles, report options, macOS launchd schedules, GitHub Actions secrets, and developer hooks:

```sh
python3 -m pip install -e '.[dev]'
./start.sh setup
```

In an interactive terminal, `./start.sh` with no arguments launches the **Textual TUI** (install `pip install -e '.[gui]'` first). Use `./start.sh --cli` for the numbered bash menu, or `./start.sh setup` directly for the setup wizard.

### Interactive interfaces

Two interfaces exist. Do not mix their option numbers.

| Interface | Invocation | Purpose |
|-----------|------------|---------|
| **Textual TUI** (default) | `./start.sh` or `github-usage` in a TTY | Top tabs for Setup, Local Full Report, Email Report, Schedules, Runs & Drift. Setup has sub-tabs plus **Start guided setup**. Schedules use day/time pickers. Keys: **1**–**5** switch views, **j**/**k** line scroll, **PgUp**/**PgDn** page scroll, **Ctrl+Home**/**Ctrl+End** top/bottom, **Ctrl+S** save, **Ctrl+R** run/refresh, **Escape** cancel, **q** quit |
| **CLI bash menu** | `./start.sh --cli` | **1** setup · **2** report · **3** email-report · **4** runs · **5** runs-diff · **6** help · **7** exit |
| **Setup wizard** | `./start.sh setup` or bash menu **1** | **1** full setup · **2** secrets · **3** report options · **4** report schedule · **5** GitHub Actions workflow · **6** macOS launchd · **7** GitHub Actions secrets · **8** dev hooks · **9** verify |

Subcommand shortcuts (`./start.sh setup`, `github-usage runs`, etc.) work without `--cli`.

**Convention:** wherever this README refers to a setup-wizard choice, use:

> Run `./start.sh --cli`, choose **1** (Run Guided Setup), then choose **N** (*wizard label*) — or run `./start.sh setup` and choose **N**.

For top-level commands, run `./start.sh --cli` and choose the matching number, use the TUI sidebar, or use `./start.sh <command>` directly.

The guided wizard can:

- Write `.env.email-report` (mode `600`) for `GITHUB_TOKEN`, Resend, and recipient settings
- Write `.github-usage/config.toml` for report flags and schedule defaults
- Verify with `email-report --dry-run`
- Install a Monday 9:00 LaunchAgent on macOS (local timezone)
- Set GitHub Actions secrets with `gh secret set`
- Install pre-commit and pre-push hooks (including Gitleaks)

Non-interactive helpers:

```sh
./start.sh setup --status    # show configured paths (secrets masked)
./start.sh setup --verify    # dry-run using local config
```

Example templates (safe to commit): [`.env.email-report.example`](.env.email-report.example) and [`.github-usage/config.example.toml`](.github-usage/config.example.toml). Generated local files under `.github-usage/` and `.env.email-report` are gitignored.

## Configuration

### GitHub Actions delivery

Run `./start.sh`, choose **1** (Run Guided Setup), then choose **5** (GitHub Actions workflow) — or run `./start.sh setup` and choose **5** — to configure the scheduled
GitHub Actions report and render `.github/workflows/email-report.yml` from a
checked-in template:

- **Cron schedule** — always UTC. Example: `0 9 * * 1` = every Monday at 09:00 UTC.
- **Default report sections** — `include_consumers`, `include_artifact_storage`,
  and `include_release_assets`. These become the fallback values for *scheduled* runs.
- **Email format** — the checked-in workflow uses HTML email with a plain-text fallback. A workflow rendered by setup follows `[email_report].email_format`, which defaults to `"text"`; choose HTML in report options or set `email_format = "html"` before rendering to use HTML delivery.
- **`workflow_dispatch` manual runs** — the GitHub UI dropdowns still work as
  per-run overrides. The configured defaults are only used when the workflow
  fires on schedule (when `inputs.*` are `null`).
- **Commit required** — the wizard writes the file locally and prints a
  `git add … && git commit … && git push` line. Nothing is committed automatically.

The local launchd schedule (setup wizard option **4**, *Report schedule only*) is independent of the GitHub Actions
cron (setup wizard option **5**, *GitHub Actions workflow*) and the LaunchAgent install/remove flow (setup wizard option **6**, *macOS launchd schedule*). These options are stored in separate sections (`[schedule]`, `[github_actions]`, and launchd plist generation)
of `.github-usage/config.toml` and drive separate scheduling systems.

The four `gh` secrets (`GH_USAGE_TOKEN`, `RESEND_API_KEY`, `REPORT_EMAIL`,
`RESEND_FROM`) are not touched by the workflow renderer; use setup wizard option **7**
(*GitHub Actions secrets*) to push them.

## Authentication

The CLI resolves a token in this order:

1. Command-line argument
2. `GITHUB_TOKEN` environment variable
3. `gh auth token`
4. `~/.config/github-cli/github.yaml`

Recommended setup:

```sh
gh auth login -h github.com -s user
github-usage
```

You can also pass a token through the environment:

```sh
GITHUB_TOKEN="<token>" github-usage
```

Passing a token as a command-line argument is supported, but it can expose the token through shell history or process listings. Prefer `gh auth login` or `GITHUB_TOKEN`.

## Scheduled Email Reports

Use `./start.sh setup` to configure recurring delivery, or configure the command manually. The report can run on a GitHub Actions cron schedule or through a local macOS LaunchAgent. GitHub Actions workflows always read the recipient from the `REPORT_EMAIL` secret, including manual runs; the renderer never copies a profile's `target_email` into YAML. Named profiles support separate subjects, report options, and schedules. Profile `target_email` values apply to local reports only; all generated Actions workflows use the same repository secret.

The manual `workflow_dispatch` input `report_email` has been removed. Remove `-f report_email=...` from dispatch commands. For a one-off recipient, run `github-usage email-report --to you@example.com` locally; Actions always uses the repository secret.

After upgrading, regenerate and review any previously rendered workflows before committing them. Older renderers could embed a non-empty profile `target_email` literally. Removing an address from a workflow does not remove it from existing Git history.

`github-usage email-report` collects current-month billing data and renders plain text by default. Pass `--email-format html` to render HTML; Resend then receives both HTML and a plain-text fallback. Use `--dry-run` first to preview the message without requiring email settings:

```sh
GITHUB_TOKEN="<token>" github-usage email-report --dry-run
```

To send an email, set:

```sh
export GITHUB_TOKEN="<token>"
export RESEND_API_KEY="<resend-api-key>"
export REPORT_EMAIL="you@example.com"
export RESEND_FROM="reports@your-verified-domain.example"
github-usage email-report
```

`RESEND_FROM` must be an address on a verified Resend sending domain. The placeholder `noreply@github-usage.example` will not work.

The email command supports:

```sh
github-usage email-report \
  [--include-consumers] \
  [--include-artifact-storage] \
  [--include-release-assets --yes-include-release-assets] \
  [--include-forecast] [--no-include-forecast] \
  [--premium-requests-limit N] \
  [--max-repos 100] \
  [--warn-over 25] \
  [--warn-over 80%] \
  [--skip-actions] [--skip-copilot] [--skip-lfs] \
  [--only-public | --only-private] \
  [--dry-run] \
  [--export csv|xlsx|pdf|json|text|none] \
  [--output PATH] \
  [--email-format text|html]
```

### API impact and detailed analysis

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

## Viewing Configured Runs

`github-usage runs` prints a consolidated, read-only summary of every currently
configured scheduled run — both local launchd schedules and GitHub Actions
workflow cron expressions — without needing an interactive terminal. The
listing reflects local state: it reads every `config.toml` profile plus any
`email-report*.yml` files present in `.github/workflows/`, so it shows only
what is on disk in this checkout:

```sh
github-usage runs
# or: ./start.sh runs
# or: ./start.sh and choose 4 (View Scheduled Runs)
```

Each row shows the profile (a report configuration name from `config.toml`),
the source (`launchd` or `github_actions`), and the schedule. The profile name
`default` is the primary report configuration (workflow file
`.github/workflows/email-report.yml`); additional names come from `[[reports]]`
entries. GitHub Actions cron lines are shown in plain language plus the raw
expression — for example `0 9 * * 1` means Mondays at 09:00 UTC. launchd
times use your Mac's local timezone.

- `active` — launchd plist installed in `~/Library/LaunchAgents/`, or the
  workflow file present in `.github/workflows/`.
- `inactive` — configured but the plist/workflow file is not present.
- `unsupported` — launchd schedules on a non-macOS host.

On-disk `email-report*.yml` workflows that do not match a configured profile are
listed as `<unconfigured>` so drifted or externally added workflows are visible.

Options:

```sh
github-usage runs \
  [--profile NAME] \   # show only one profile (skips stray-workflow detection)
  [--json] \           # structured JSON instead of human-readable text
  [--api] \            # also query the GitHub API for each workflow's latest run
  [--owner OWNER] \    # owner override for --api (default: parsed from git remote)
  [--repo REPO]        # repo override for --api (default: parsed from git remote)
```

`--api` requires a GitHub token (resolved from `GITHUB_TOKEN`, the `gh` CLI, or
the GitHub CLI config) and annotates each GitHub Actions row with the latest
run's timestamp and conclusion. The offline view never makes network requests.
With or without `--api`, the listing reflects local state only — `--api`
enriches the local rows with each workflow's latest run but does not enumerate
workflows that exist on GitHub but not in this checkout. The view matches what
is configured on GitHub only when every local `email-report*.yml` and
`config.toml` profile has been pushed and no workflows have been added through
the GitHub UI without being checked out locally.

## Checking for Drift

`github-usage runs --diff` answers a different question than `--api`:
"is what I have locally what GitHub has?" It compares each
`.github/workflows/email-report*.yml` against the configured remote's default
branch and reports per-file drift — no GitHub token required.

```sh
github-usage runs --diff
# or: ./start.sh runs-diff
# or: ./start.sh and choose 5 (Check Scheduled Runs Drift)
```

Each row reports one of nine categories with a summary:

- `in-sync` — local and remote blob hashes match.
- `uncommitted` — local has working-tree changes vs. HEAD.
- `staged` — local has staged index changes vs. HEAD.
- `untracked` — file on disk but not in the git index.
- `ahead` — local has changes not on the remote (or the file was
  added/deleted locally and not pushed).
- `behind` — remote has changes the local working tree lacks.
- `remote-only` — file is on the remote but wholly missing locally.
- `diverged` — local and remote have both moved past the merge base.
- `unknown` — a required piece of state could not be determined.

The remote name is read from `git config branch.<current>.remote` (with
`origin` as a fallback) and the default branch is resolved as
`git symbolic-ref refs/remotes/<remote>/HEAD`, falling back to `main` then
`master`. The view reflects local state plus what the local git refs
report for the remote — `.github-usage/config.toml` is intentionally not
in scope (it is created by the setup wizard and is not pushed).

Options:

```sh
github-usage runs --diff \
  [--profile NAME] \     # scope to one profile's workflow file only
  [--json] \             # structured JSON instead of human-readable text
  [--no-fetch] \         # skip `git fetch <remote>`; equivalent to GITHUB_USAGE_SKIP_FETCH=1
  [--owner OWNER] \      # (rejected with --diff; only applies to --api)
  [--repo REPO]          # (rejected with --diff; only applies to --api)
```

`--diff` and `--api` are mutually exclusive at parse time. A failed
`git fetch` falls back to the cached `<remote>/<default-branch>` ref and
emits a `warning: fetch of <remote> failed; falling back to cached
refs (...)` line to stderr; rows only degrade to `unknown` when no cached
ref is available.

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
**deferred**. API discovery (see [`docs/api-discovery-month.md`](docs/api-discovery-month.md))
confirmed that GitHub's billing endpoints ignore the `since`/`until`
parameters and return the same shape with or without them, so historical
queries are not feasible with the current GitHub API.

### GitHub Actions secrets

This repo includes [`.github/workflows/email-report.yml`](.github/workflows/email-report.yml) as a workflow template. Run `./start.sh`, choose **1** (Run Guided Setup), then choose **7** (GitHub Actions secrets) — or run `./start.sh setup` and choose **7** — to set these with `gh secret set`:

- `GH_USAGE_TOKEN`: a personal access token that can read your personal repos
  and your user-level billing data
  - Classic PAT: select the `user` scope for the `/users/{username}/settings/billing/*`
    endpoints, plus `repo` when analyzing private repositories. `repo` alone does not
    grant the billing endpoints.
  - Fine-grained PAT: create it with your user as the resource owner and
    "All repositories" access. Grant `Metadata: Read-only` (for `/user/repos` and
    `/repos/{owner}/{repo}/...`), the account permission `Plan: Read-only` (for
    billing), `Actions: Read-only` (for runs and artifacts), and `Contents: Read-only`
    when using release-asset inventory. `read:user` alone is not enough.
- `RESEND_API_KEY`: your Resend API key
- `REPORT_EMAIL`: the recipient address
- `RESEND_FROM`: a sender address on your verified Resend domain

Do not use the automatic GitHub Actions `${{ github.token }}` for this report.
The Actions-provided `GITHUB_TOKEN` is scoped to the repository's installation
and cannot reach the user-billing endpoints that this report needs. The
`GITHUB_` secret prefix is reserved by Actions, so the workflow stores the
personal token as `GH_USAGE_TOKEN` and exposes it to the CLI as `GITHUB_TOKEN`.

After secrets are set, test with `gh workflow run email-report.yml`.

### Local macOS launchd scheduling

Run `./start.sh`, choose **1** (Run Guided Setup), then choose **6** (macOS launchd schedule) — or run `./start.sh setup` and choose **6** (or **1** for recommended full setup). The wizard writes `.github-usage/config.toml`, generates a LaunchAgent plist, and can install it for Monday 9:00 in your local timezone.

To change only the report schedule after initial setup, run `./start.sh setup` and choose **4** (*Report schedule only*). It updates `[schedule]` in `config.toml` and regenerates the LaunchAgent plist. If a LaunchAgent is already installed, the wizard reminds you to rerun setup wizard option **6** (*macOS launchd schedule*) and choose install to apply the new schedule.

Scheduled runs invoke [`scripts/send-email-report.sh`](scripts/send-email-report.sh), which loads `.env.email-report`, applies config options, and logs to `reports/`. Override the env file with `GITHUB_USAGE_ENV_FILE` or the log directory with `GITHUB_USAGE_LOG_DIR` if needed.

The committed template at [`launchd/com.github.github-usage.email-report.plist`](launchd/com.github.github-usage.email-report.plist) is reference-only; prefer the wizard-generated plist under `.github-usage/launchd/`.

### Email Troubleshooting

- Missing GitHub `user` scope: billing endpoints may return 404. Fix GitHub CLI auth with `gh auth refresh -h github.com -s user`, or use a PAT with the `user` scope.
- GitHub Actions token confusion: use `GH_USAGE_TOKEN`, not the automatic `GITHUB_TOKEN`.
- Resend domain unverified: set `RESEND_FROM` to an address on a verified Resend domain.
- Rate limiting: reduce frequency, lower `--max-repos`, avoid repo-level options, or use skip flags.
- Consumer breakdown truncation: increase `--max-repos` cautiously.
- Artifact storage request cost: `--include-artifact-storage` can add roughly one REST API request per scanned repository.
- Release asset inventory: `--include-release-assets` can add roughly one REST API request per scanned repository and requires explicit confirmation.
- No data for a product: use `--skip-copilot`, `--skip-actions`, or `--skip-lfs` when the account does not use that feature.

## Privacy

This tool prints account, repository, billing, and usage details to stdout. Treat generated output as sensitive unless you have reviewed and redacted it. Do not commit tokens, raw private API responses, generated billing reports, or local environment files.

Exported files go through a redaction layer that masks usernames, repository
names, email addresses, and dollar amounts before writing. The redaction is
applied only to the file content; interactive terminal output and the email
body are not redacted. See `src/github_usage/redact.py` for the exact
patterns.

## Development

Run the main verification script:

```sh
scripts/check
```

Run CLI smoke checks:

```sh
scripts/smoke
```

Install optional development tools:

```sh
python3 -m pip install -e '.[dev]'
pre-commit install
pre-commit install --hook-type pre-push
```

Or run `./start.sh`, choose **1** (Run Guided Setup), then choose **8** (Developer security hooks) — or run `./start.sh setup` and choose **8** — to install commit and push hooks (including Gitleaks).

Run local security checks:

```sh
scripts/security
```

The public GitHub repository also uses GitHub code scanning with CodeQL default setup. The local `Security` workflow covers repository-level checks that can run without uploading SARIF: Gitleaks, `pip-audit`, Bandit, and a zizmor check that fails on GitHub Actions references with known security advisories (including SHA-pinned actions, which Dependabot alerts do not cover).

`scripts/security` audits the full locked dependency set from `uv.lock` (all extras) when `uv` is installed; without `uv` it audits the current Python environment instead.

Run documentation checks:

```sh
scripts/docs-check
```

## Repository Layout

- `src/github_usage/`: active package source
- `tests/`: unit tests and future fixtures
- `scripts/`: canonical local automation commands
- `docs/`: maintainer guidance
- `backups/`: transient pre-modification backups (`*.bak`), pruned by `scripts/prune-backups`; not active code

## Roadmap

See [TO_DO.md](TO_DO.md) for planned work, including historical email reports, deeper Actions analysis, and platform-specific setup improvements. Export formats (CSV, XLSX, PDF, JSON, text) are implemented.
