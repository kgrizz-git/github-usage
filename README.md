# github-usage

[![CI](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml)
[![Security](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml)

Understand your current-month GitHub billing and get scheduled reports before costs become a surprise. `github-usage` covers GitHub Actions, Copilot, Git LFS, and storage for individuals and small teams.

- Track usage, cost estimates, quotas, and end-of-month forecasts.
- Find repositories and workflows contributing the most to Actions usage.
- Read reports in the terminal or optional Textual TUI, or export CSV, XLSX, PDF, JSON, and text.
- Schedule email digests through GitHub Actions and Resend, or locally with macOS launchd.

Reports distinguish public standard-runner Actions usage from private and internal usage, where plan quotas apply. See [report details and limitations](docs/reports.md#api-impact-and-billing-interpretation).

## Get started

Requires **Python 3.11+** and a GitHub token with access to your account's billing data. For a classic token, use the `user` scope and add `repo` for private repositories. See [authentication and token permissions](docs/setup.md#requirements) for fine-grained tokens and other options.

From a checkout:

```sh
scripts/python -m pip install -e .
./start.sh setup
```

Choose **1** for guided setup. For email delivery, you will also need a Resend API key and an address on a verified sending domain.

To run a local full report, authenticate with GitHub CLI first (or [set `GH_USAGE_TOKEN` / `GITHUB_TOKEN`](docs/setup.md#authentication)):

```sh
gh auth login -h github.com -s user
./start.sh report
```

The local full report does not load the token saved by setup in `.env.email-report`.

Prefer an interactive interface? Install `scripts/python -m pip install -e '.[gui]'`, then run `./start.sh` in a terminal. `./start.sh` uses the repository’s `.venv`, managed by `scripts/python`. The core CLI works wherever Python is available; local scheduling requires macOS.

## Schedule email reports

Use `./start.sh setup` to configure either delivery path:

| Delivery | What to configure |
| --- | --- |
| **GitHub Actions** | UTC schedule and the four repository secrets: `GH_USAGE_TOKEN`, `RESEND_API_KEY`, `REPORT_EMAIL`, `RESEND_FROM`. Merge the rendered workflow into the default branch; on a fork, enable it in the **Actions** tab. |
| **macOS launchd** | Local day and time, local Resend credentials, then install the generated LaunchAgent. Your Mac must be available when the report runs. |

Preview your local profile's email settings and report options before sending:

```sh
./start.sh setup --verify
```

This preview does not verify the separate GitHub Actions defaults or remote secrets. Actions recipients always come from the repository `REPORT_EMAIL` secret; profile recipient overrides apply to local delivery only. The checked-in workflow uses HTML with a plain-text fallback; newly configured reports default to text.

See the [email setup guide](docs/email-reports.md) for secrets, schedules, named profiles, migration notes, and troubleshooting.

## Guides

| I want to… | Guide |
| --- | --- |
| Install, authenticate, or choose an interface | [Installation and setup](docs/setup.md) |
| Configure email delivery or troubleshoot it | [Email reports and scheduling](docs/email-reports.md) |
| Understand billing details, API costs, or exports | [Reports and exports](docs/reports.md) |
| List schedules or compare workflows with GitHub | [Scheduled runs and workflow drift](docs/scheduled-runs.md) |
| Contribute or run checks | [Development](docs/development.md) |

For command options, run `./start.sh report --help` or `./start.sh email-report --help`. Planned work is tracked in [TO_DO.md](TO_DO.md).

## Privacy

Terminal output and email bodies contain account, repository, and billing details. Export redaction is partial and depends on the format; review file contents and filenames before sharing. Do not commit tokens, local environment files, or generated reports. See [privacy details](docs/reports.md#privacy).
