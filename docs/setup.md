# Installation and setup

[Back to README](../README.md)

## Requirements

- Python 3.11 or newer
- A GitHub token authorized for your account's billing endpoints
- Optional: GitHub CLI (`gh`) for token discovery
- Optional for email reports: a Resend API key and verified sending domain

For a classic personal access token, use the `user` scope for user-level billing endpoints and add `repo` when analyzing private repositories; `repo` alone does not grant access to user billing endpoints. For a fine-grained token, select all relevant repositories, grant your user account's **Plan: Read-only** permission, and grant the repository permissions required by the report sections you enable: **Actions: Read-only** for runs and artifacts, and **Contents: Read-only** for release inventory. See [GitHub Actions secrets](email-reports.md#github-actions-secrets) for the scheduled-workflow setup. The core CLI runs wherever Python is available; local automated scheduling uses macOS launchd.

## Installation options

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

## Setup and interfaces

Run the shell commands in this guide from the repository root.

Use one entry point to configure local secrets, named report profiles, report options, macOS launchd schedules, GitHub Actions secrets, and developer hooks:

```sh
./start.sh setup
```

In an interactive terminal, `./start.sh` with no arguments launches the **Textual TUI** (install `pip install -e '.[gui]'` first). Use `./start.sh --cli` for the numbered bash menu, or `./start.sh setup` directly for the setup wizard.

### Interactive interfaces

The TUI and bash menu are separate interfaces; the setup wizard has its own choices. Use the invocation shown for each.

| Interface | Invocation | Purpose |
|-----------|------------|---------|
| **Textual TUI** (default) | `./start.sh` or `github-usage` in a TTY | Top tabs for Setup, Local Full Report, Email Report, Schedules, Runs & Drift. Setup has sub-tabs plus **Start guided setup**. Schedules use day/time pickers. Keys: **1**–**5** switch views, **j**/**k** line scroll, **PgUp**/**PgDn** page scroll, **Ctrl+Home**/**Ctrl+End** top/bottom, **Ctrl+S** save, **Ctrl+R** run/refresh, **Escape** cancel, **q** quit |
| **CLI bash menu** | `./start.sh --cli` | **1** setup · **2** report · **3** email-report · **4** runs · **5** runs-diff · **6** help · **7** exit |
| **Setup wizard** | `./start.sh setup` or bash menu **1** | **1** full setup · **2** secrets · **3** report options · **4** report schedule · **5** GitHub Actions workflow · **6** macOS launchd · **7** GitHub Actions secrets · **8** dev hooks · **9** verify |

Subcommand shortcuts (`./start.sh setup`, `github-usage runs`, etc.) work without `--cli`.

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

Example templates (safe to commit): [`.env.email-report.example`](../.env.email-report.example) and [`.github-usage/config.example.toml`](../.github-usage/config.example.toml). Generated local files under `.github-usage/` and `.env.email-report` are gitignored.

## Authentication

The CLI resolves a token in this order:

1. Command-line argument
2. `GH_USAGE_TOKEN` environment variable
3. `GITHUB_TOKEN` environment variable
4. `gh auth token`
5. `~/.config/github-cli/github.yaml`

The local full report (`./start.sh report`) does not load `.env.email-report`. A token saved by guided setup is used by the scheduled email script, setup verification, and TUI email report; authenticate separately for the local full report using GitHub CLI or `GITHUB_TOKEN`.

Recommended setup for a local full report:

```sh
gh auth login -h github.com -s user
./start.sh report
```

You can also pass a token through the environment:

```sh
GITHUB_TOKEN="<token>" ./start.sh report
```

Passing a token as a command-line argument is supported, but it can expose the token through shell history or process listings. Prefer `gh auth login` or `GITHUB_TOKEN`.

For recurring delivery, continue with [Email reports](email-reports.md).
