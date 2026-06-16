# github-usage

[![CI](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml)
[![Security](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml)

`github-usage` is a Python command-line tool for reviewing GitHub billing and usage data from your account. It reports GitHub Actions minutes and storage, repository-level Actions usage, Copilot premium requests, Git LFS usage, billing history, limits, and the largest current-month resource consumers.

The project started as a personal reporting script and is being shaped into a reusable Python package. The packaged CLI currently preserves the v3 report behavior while the internals are split into smaller, testable modules.

## Features

- Account and plan summary
- GitHub Actions minutes, storage, and per-SKU cost breakdown
- Per-repository Actions usage
- Copilot premium request usage by model
- Git LFS usage
- Current-month net/gross cost estimate
- Full billing history summary from the GitHub billing API
- Scheduled plain-text email reports through Resend
- Local smoke, security, and documentation checks for maintainers

## Requirements

- Python 3.11 or newer
- A GitHub token with the `user` scope for billing endpoints
- Optional: GitHub CLI (`gh`) for token discovery
- Optional for email reports: a Resend API key and verified sending domain

## Install

From a checkout:

```sh
python3 -m pip install -e .
```

Then run:

```sh
github-usage --help
github-usage
```

You can also run without installing:

```sh
PYTHONPATH=src python3 -m github_usage --help
PYTHONPATH=src python3 -m github_usage
```

The root-level `github-usage` file is a compatibility wrapper for the packaged CLI.

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

`github-usage email-report` collects the current-month billing data, renders a plain-text email body, and sends it with Resend. Use `--dry-run` first to preview the message without requiring email settings:

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
  [--max-repos 100] \
  [--warn-over 25] \
  [--warn-over 80%] \
  [--skip-actions] [--skip-copilot] [--skip-lfs] \
  [--dry-run]
```

`--include-consumers`, `--include-artifact-storage`, and `--include-release-assets` add repo-level API calls. They consume GitHub REST API request quota, not Actions minutes, Actions storage, Copilot requests, Git LFS quota, or billable GitHub usage. Use monthly schedules and conservative `--max-repos` values for accounts with many repositories.

Release assets are optional inventory, not a billing/quota report. The CLI asks for confirmation in interactive terminals, and CI must pass `--yes-include-release-assets`.

### GitHub Actions Setup

This repo includes `.github/workflows/email-report.yml` as a workflow template. Copy it into the repository where you want the scheduled report to run, then create these repository secrets:

- `GH_USAGE_TOKEN`: a personal access token with the `user` scope
- `RESEND_API_KEY`: your Resend API key
- `REPORT_EMAIL`: the recipient address
- `RESEND_FROM`: a sender address on your verified Resend domain

Do not use the automatic GitHub Actions `${{ github.token }}` for this report. Billing endpoints require a user-scoped token, and Actions reserves the `GITHUB_` secret prefix, so the workflow stores the personal token as `GH_USAGE_TOKEN` and exposes it to the CLI as `GITHUB_TOKEN`.

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
```

Run local security checks:

```sh
scripts/security
```

The public GitHub repository also uses GitHub code scanning with CodeQL default setup. The local `Security` workflow covers repository-level checks that can run without uploading SARIF: Gitleaks, `pip-audit`, and Bandit.

Run documentation checks:

```sh
scripts/docs-check
```

## Repository Layout

- `src/github_usage/`: active package source
- `tests/`: unit tests and future fixtures
- `scripts/`: canonical local automation commands
- `docs/`: maintainer guidance
- `backups/`: historical script versions, not active code

## Roadmap

See [TO_DO.md](TO_DO.md) for planned work, including export formats, JSON output, historical email reports, and modularizing the current legacy implementation.
