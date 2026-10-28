# Email reports and scheduling

[Back to README](../README.md)

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

## GitHub Actions secrets

This repo includes [`.github/workflows/email-report.yml`](../.github/workflows/email-report.yml) as a workflow template. Run `./start.sh setup` and choose **7** (GitHub Actions secrets) to set these with `gh secret set`:

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

## GitHub Actions delivery

Run `./start.sh setup` and choose **5** (GitHub Actions workflow) to configure the scheduled
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

GitHub runs scheduled workflows from the default branch only. Commit, push, and merge the rendered workflow into that branch. On a fork, enable the workflow in the **Actions** tab after pushing. The checked-in workflow runs Mondays at 09:00 UTC.

## Local macOS launchd scheduling

Run `./start.sh setup` and choose **6** (macOS launchd schedule) (or **1** for recommended full setup). The wizard writes `.github-usage/config.toml`, generates a LaunchAgent plist, and can install it for Monday 9:00 in your local timezone.

To change only the report schedule after initial setup, run `./start.sh setup` and choose **4** (*Report schedule only*). It updates `[schedule]` in `config.toml` and regenerates the LaunchAgent plist. If a LaunchAgent is already installed, the wizard reminds you to rerun setup wizard option **6** (*macOS launchd schedule*) and choose install to apply the new schedule.

Scheduled runs invoke [`scripts/send-email-report.sh`](../scripts/send-email-report.sh), which loads `.env.email-report`, applies config options, and logs to `reports/`. Override the env file with `GITHUB_USAGE_ENV_FILE` or the log directory with `GITHUB_USAGE_LOG_DIR` if needed.

The committed template at [`launchd/com.github.github-usage.email-report.plist`](../launchd/com.github.github-usage.email-report.plist) is reference-only; prefer the wizard-generated plist under `.github-usage/launchd/`.

Your Mac must be available for a local scheduled report to run.

## Email command reference

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

## Troubleshooting

- Missing GitHub `user` scope: billing endpoints may return 404. Fix GitHub CLI auth with `gh auth refresh -h github.com -s user`, or use a PAT with the `user` scope.
- GitHub Actions token confusion: use `GH_USAGE_TOKEN`, not the automatic `GITHUB_TOKEN`.
- Resend domain unverified: set `RESEND_FROM` to an address on a verified Resend domain.
- Rate limiting: reduce frequency, lower `--max-repos`, avoid repo-level options, or use skip flags.
- Consumer breakdown truncation: increase `--max-repos` cautiously.
- Artifact storage request cost: `--include-artifact-storage` can add roughly one REST API request per scanned repository.
- Release asset inventory: `--include-release-assets` can add roughly one REST API request per scanned repository and requires explicit confirmation.
- No data for a product: use `--skip-copilot`, `--skip-actions`, or `--skip-lfs` when the account does not use that feature.

For API request costs, billing interpretation, and exports, see [Reports and exports](reports.md). To inspect schedules and workflow drift, see [Scheduled runs](scheduled-runs.md).
