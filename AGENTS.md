# AGENTS.md

## Repository Expectations

- Active package code lives in `src/github_usage/`.
- Historical scripts live in `backups/` and should not be treated as active implementation.
- Use `scripts/check` as the default verification command before claiming a code change is complete.
- Use `scripts/smoke` after CLI entrypoint changes.
- Use `scripts/docs-check` after README, docs, or CLI help changes.
- Do not print, commit, or store real GitHub tokens, raw private API responses, or generated billing reports.
- Tests should use fake tokens, mocks, and fixtures rather than live GitHub API calls.
- Optional live checks must be gated behind an explicit environment variable.

## Done Criteria

A change is done when relevant tests pass, the CLI still starts, docs are updated for user-visible behavior changes, and no secrets or generated reports were added.

## Maintainer References

- Repo harness guidance: `docs/repo-harness-guidance.md`
