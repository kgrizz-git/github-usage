# AGENTS.md

## Repository Expectations

- Active package code lives in `src/github_usage/`.
- Historical scripts live in `backups/` and should not be treated as active implementation.
- Use `scripts/check` as the default verification command before claiming a code change is complete.
- Use `scripts/smoke` after CLI entrypoint changes.
- Use `scripts/docs-check` after README, docs, or CLI help changes.
- Use `scripts/setup` as the single entry point for guided local/CI email-report configuration.
- Do not print, commit, or store real GitHub tokens, raw private API responses, or generated billing reports.
- Tests should use fake tokens, mocks, and fixtures rather than live GitHub API calls.
- Optional live checks must be gated behind an explicit environment variable.

## Done Criteria

A change is done when relevant tests pass, the CLI still starts, docs are updated for user-visible behavior changes, and no secrets or generated reports were added.

## Code Style

- Keep files and functions small. If a file exceeds ~300 lines or a function exceeds ~50 lines, split it.
- Favor composition and small, focused modules over monolithic classes or functions.
- Avoid unnecessary complexity: prefer readable, straightforward code over clever or overly generic solutions.
- When adding a feature that touches many areas, extract shared logic into its own module rather than duplicating or inflating existing ones.

## Maintainer References

- Repo harness guidance: `docs/repo-harness-guidance.md`
