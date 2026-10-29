# Installation and setup

[Back to README](../README.md)

## Requirements

- Python 3.11 or newer
- A GitHub token authorized for your account's billing endpoints
- Optional: GitHub CLI (`gh`) for token discovery
- Optional for email reports: a Resend API key and verified sending domain

For a classic personal access token, use the `user` scope for user-level billing endpoints and add `repo` when analyzing private repositories; `repo` alone does not grant access to user billing endpoints. For a fine-grained token, select all relevant repositories, grant your user account's **Plan: Read-only** permission, and grant the repository permissions required by the report sections you enable: **Actions: Read-only** for runs and artifacts, and **Contents: Read-only** for release inventory. See [GitHub Actions secrets](email-reports.md#github-actions-secrets) for the scheduled-workflow setup. The core CLI runs wherever Python is available; local automated scheduling uses macOS launchd.

## Installation options

Run checkout commands from the repository root. `./start.sh`, setup, and the check scripts use `.venv/bin/python`; `scripts/python` creates this environment if necessary. Install extras with that interpreter:

```sh
scripts/python -m pip install -e .
./start.sh report --help
```

For the interactive Textual TUI:

```sh
scripts/python -m pip install -e '.[gui]'
./start.sh
```

Alternatively, install into your own active Python environment with `python3 -m pip install -e .`, then run `python3 -m github_usage --cli --help` with that same interpreter for CLI help. That installation does not populate the separate `.venv` used by `./start.sh`. Install extras into whichever environment runs the command.

For source-only CLI help without installing:

```sh
PYTHONPATH=src python3 -m github_usage --cli --help
```

The root-level `github-usage` file is a compatibility wrapper for the packaged CLI. Checkout commands here use `./start.sh` or `scripts/python -m github_usage` and do not require `.venv/bin` on PATH.

### Windows shells

The core Python CLI can run on Windows; checkout shell scripts such as `./start.sh` require Bash. Use your installation interpreter to run the `github_usage` module in a native Windows shell. Help and dependency errors show separately labeled **cmd.exe** and **PowerShell** installation commands on Windows. Copy only the command for your shell, without its label. PowerShell uses `&` to invoke the quoted interpreter path; cmd.exe uses double quotes around paths and requirement constraints. For argument characters that cmd.exe expands even inside quotes (`%` or `!`), the guidance offers only the PowerShell form.

## Setup and interfaces

Run the shell commands in this guide from the repository root.

Use one entry point to configure local secrets, named report profiles, report options, macOS launchd schedules, GitHub Actions secrets, and developer hooks:

```sh
./start.sh setup
```

In an interactive terminal, `./start.sh` with no arguments launches the **Textual TUI** (install `scripts/python -m pip install -e '.[gui]'` first). Use `./start.sh --cli` for the numbered bash menu, or `./start.sh setup` directly for the setup wizard.

### Interactive interfaces

The TUI and bash menu are separate interfaces; the setup wizard has its own choices. Use the invocation shown for each.

| Interface | Invocation | Purpose |
|-----------|------------|---------|
| **Textual TUI** (default) | `./start.sh` or `scripts/python -m github_usage` in a TTY | Top tabs for Setup, Local Full Report, Email Report, Schedules, Runs & Drift. Setup has sub-tabs plus **Start guided setup**. Schedules use day/time pickers. Keys: **1**–**5** switch views, **j**/**k** line scroll, **PgUp**/**PgDn** page scroll, **Ctrl+Home**/**Ctrl+End** top/bottom, **Ctrl+S** save / **Ctrl+R** run/refresh (view-specific), **Escape** cancel, **q** quit |
| **CLI bash menu** | `./start.sh --cli` | **1** setup · **2** report · **3** email-report · **4** runs · **5** runs-diff · **6** help · **7** exit |
| **Setup wizard** | `./start.sh setup` or bash menu **1** | **1** full setup · **2** secrets · **3** report options · **4** report schedule · **5** GitHub Actions workflow · **6** macOS launchd · **7** GitHub Actions secrets · **8** dev hooks · **9** verify · **m** manage profiles · **0** status |

Subcommand shortcuts (`./start.sh setup`, `scripts/python -m github_usage runs`, etc.) work without `--cli`.

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

The local full report (`./start.sh report`) does not load `.env.email-report`. A token saved by guided setup is used by the scheduled email script, setup verification, and TUI email report; authenticate separately for the local full report using GitHub CLI, `GH_USAGE_TOKEN`, or `GITHUB_TOKEN`.

Recommended setup for a local full report:

```sh
gh auth login -h github.com -s user
./start.sh report
```

You can also pass a token through the environment:

```sh
GITHUB_TOKEN="<token>" ./start.sh report
```

Passing a token as a command-line argument is supported, but it can expose the token through shell history or process listings. Prefer `gh auth login` or an environment variable (`GH_USAGE_TOKEN` takes precedence over `GITHUB_TOKEN`).

For recurring delivery, continue with [Email reports](email-reports.md).
