# Monthly Dependabot version updates

> **Status:** COMPLETE

- [x] Confirm current GitHub configuration and security-update settings.
- [x] Schedule uv and GitHub Actions version checks for the 10th at 15:00 America/New_York, preserving cooldown and groups.
- [x] Run repository and documentation checks.

**Done:** 2026-10-20 — Implemented the requested cron schedule; scripts/check, scripts/docs-check, and git diff --check passed. No security settings changed.

Security settings checked on 2026-10-20 via read-only GitHub API calls: the vulnerability-alerts endpoint returned success (alerts enabled), and automated-security-fixes returned `enabled: true`, `paused: false`. No repository security settings were changed.

Review: OpenCode DeepSeek V4.1 Flash Free confirmed the cron/timezone, DST behavior, no ignore rules, and preserved cooldown/groups. Addressed its two minor documentation findings by matching the changelog list spacing and recording the security-setting results here.

**Deviation:** The pre-push gate exposed inherited Git hook variables redirecting backup-policy fixture commands into the worktree index. Isolated and restored repository-local Git environment variables in the temporary-repository fixture, with a regression test. No verification gates were bypassed.

Post-fix verification: `scripts/check` passed (745 tests, typecheck 0 errors, coverage 76%, complexity passed); `scripts/docs-check` and `git diff --check` also passed. DeepSeek's follow-up review verified the hook-environment reproduction and identified minor cleanup/coverage improvements: replaced manual context-manager cleanup with nested context managers and expanded assertions to every repository-local Git variable.
