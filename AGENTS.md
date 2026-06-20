# AGENTS.md

## Repository Expectations

- Active package code lives in `src/github_usage/`.
- Historical scripts live in `backups/` and should not be treated as active implementation.
- Use `scripts/check` as the default verification command before claiming a code change is complete.
- Use `scripts/smoke` after CLI entrypoint changes.
- Use `scripts/docs-check` after README, docs, or CLI help changes.
- Use `./setup.sh` as the single entry point for guided local/CI email-report configuration.
- The project uses `pyproject.toml` for all dependency declarations. Do not create a `requirements.txt` unless a specific tool requires it.
- Do not print, commit, or store real GitHub tokens, raw private API responses, or generated billing reports.
- Tests should use fake tokens, mocks, and fixtures rather than live GitHub API calls.
- Optional live checks must be gated behind an explicit environment variable.

## Done Criteria

A change is done when relevant tests pass, the CLI still starts, docs are updated for user-visible behavior changes, and no secrets or generated reports were added.

- New or changed public functions should have docstrings and test coverage for the new/changed code path.
- When completing a planned item, mark its checkbox `- [x]` in the plan file and prepend a `**Done:**` note with the date and a one-line summary of what was implemented and any deviations from the plan.
- Completed, superseded, or archived plan files should be moved to `docs/superpowers/plans/archived/` so the active plans directory stays uncluttered.

## Code Style

- Keep files and functions small. If a file exceeds ~500 lines or a function exceeds ~100 lines, split it.
- Start extracting submodules or helpers when a file approaches 400 lines — do not wait for the 500-line threshold to trigger.
- Favor composition and small, focused modules over monolithic classes or functions.
- Avoid unnecessary complexity: prefer readable, straightforward code over clever or overly generic solutions.
- When adding a feature that touches many areas, extract shared logic into its own module rather than duplicating or inflating existing ones.

## Maintainer References

- Repo harness guidance: `docs/repo-harness-guidance.md`
