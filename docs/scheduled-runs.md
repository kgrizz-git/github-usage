# Scheduled runs and workflow drift

[Back to README](../README.md)

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

For delivery configuration and required secrets, see [Email reports](email-reports.md).
