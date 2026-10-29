# Scheduled runs and workflow drift

[Back to README](../README.md)

## Viewing Configured Runs

`./start.sh runs` prints a consolidated, read-only summary of every currently
configured scheduled run — both local launchd schedules and GitHub Actions
workflow cron expressions — without needing an interactive terminal. The
listing reflects local state: it reads every `config.toml` profile plus any
`email-report*.yml` files present in `.github/workflows/`, so it shows only
what is on disk in this checkout:

```sh
./start.sh runs
# or: ./start.sh --cli and choose 4 (View Scheduled Runs)
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

| Option | Purpose |
| --- | --- |
| `--profile NAME` | Show one profile; skips stray-workflow detection |
| `--json` | Structured JSON output |
| `--api` | Add each local workflow’s latest GitHub run |
| `--owner OWNER`, `--repo REPO` | Override the remote-derived owner/repository for `--api` |

`--api` requires a GitHub token (resolved from `GH_USAGE_TOKEN`, then `GITHUB_TOKEN`, the `gh` CLI, or
the GitHub CLI config) and annotates each GitHub Actions row with the latest
run's timestamp and conclusion. The offline view never makes network requests.
With or without `--api`, the listing reflects local state only — `--api`
enriches the local rows with each workflow's latest run but does not enumerate
workflows that exist on GitHub but not in this checkout. The view matches what
is configured on GitHub only when every local `email-report*.yml` has been pushed, each local profile has a corresponding workflow on GitHub, and remote workflows are present in this checkout. `config.toml` itself stays local and is never pushed or compared by `--diff`.

## Checking for Drift

`./start.sh runs --diff` answers a different question than `--api`:
"is what I have locally what GitHub has?" It compares each
`.github/workflows/email-report*.yml` against the configured remote's default
branch and reports per-file drift — no GitHub token required.

```sh
./start.sh runs --diff
# or: ./start.sh runs-diff
# or: ./start.sh --cli and choose 5 (Check Scheduled Runs Drift)
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

| Option | Purpose |
| --- | --- |
| `--profile NAME` | Compare only that profile’s workflow |
| `--json` | Structured JSON output |
| `--no-fetch` | Skip fetching; equivalent to `GITHUB_USAGE_SKIP_FETCH=1` |

`--owner` and `--repo` apply only to `--api` and are rejected with `--diff`.

`--diff` and `--api` are mutually exclusive at parse time. A failed
`git fetch` falls back to the cached `<remote>/<default-branch>` ref and
emits a `warning: fetch of <remote> failed; falling back to cached
refs (...)` line to stderr; rows only degrade to `unknown` when no cached
ref is available.

For delivery configuration and required secrets, see [Email reports](email-reports.md).
