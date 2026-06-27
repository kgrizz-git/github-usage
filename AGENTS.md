# AGENTS.md

## Repository Expectations

- **NEVER MAKE FILE EDITS the user did not explicitly ask for.** Do not preemptively fix circular imports or modify unrelated files unless explicitly requested.
- Active package code lives in `src/github_usage/`.
- `backups/` holds only transient pre-modification backups (`*.bak`), pruned by `scripts/prune-backups`; it is not active implementation.
- Use `scripts/check` as the default verification command before claiming a code change is complete.
- Use `scripts/smoke` after CLI entrypoint changes.
- Use `scripts/docs-check` after README, docs, or CLI help changes.
- Use `./start.sh` as the primary entry point for setup, one-off reports, and email-report configuration.
- The project uses `pyproject.toml` for all dependency declarations. Do not create a `requirements.txt` unless a specific tool requires it.
- Do not print, commit, or store real GitHub tokens, raw private API responses, or generated billing reports.
- Tests should use fake tokens, mocks, and fixtures rather than live GitHub API calls.
- Optional live checks must be gated behind an explicit environment variable.

## Done Criteria

A change is done when relevant tests pass, the CLI still starts, docs are updated for user-visible behavior changes, and no secrets or generated reports were added.

- New or changed public functions should have docstrings and test coverage for the new/changed code path.
- Follow the Documentation Lifecycle below for plan, changelog, and `TO_DO.md` updates.

## Documentation Lifecycle

### Plans

- Create new plans in `docs/superpowers/plans/` with a timestamped filename: `YYYY-MM-DD-<slug>.md`.
- Group related work (e.g., fixes from a bug report) into logical phases within a plan.
- As you implement, mark each task `- [x]` and prepend a `**Done:**` note with the date, a one-line summary, and any deviations from the plan.
- When a plan is complete, set its status banner to the **canonical form** `> **Status:** COMPLETE` — the colon goes *outside* the bold so tooling (`scripts/docs-check`) can detect it — and note the merge commit.
- Move completed, superseded, or archived plans to `docs/superpowers/plans/archived/` so the active plans directory stays uncluttered.

### CHANGELOG.md

- Record completed user-visible changes under the `[Unreleased]` section, in the appropriate subsection: `Added`, `Fixed`, `Changed`, or `Deferred`.
- Keep entries under `[Unreleased]` until a release is tagged — do not create a dated version section for in-progress work.

### TO_DO.md

- When a `TO_DO.md` item is completed, **remove it**. Do not keep completed items marked `- [x]`; the changelog and archived plans are the historical record.

### Releases

- To cut a release: add a dated version section to `CHANGELOG.md`, move the `[Unreleased]` entries into it, and bump the version in **both** `src/github_usage/__init__.py` (`__version__`) and `pyproject.toml` (`version`) so they stay in sync.

## Code Style

- Keep files and functions small. If a file exceeds ~500 lines or a function exceeds ~100 lines, split it.
- Start extracting submodules or helpers when a file approaches 400 lines — do not wait for the 500-line threshold to trigger.
- Favor composition and small, focused modules over monolithic classes or functions.
- Avoid unnecessary complexity: prefer readable, straightforward code over clever or overly generic solutions.
- When adding a feature that touches many areas, extract shared logic into its own module rather than duplicating or inflating existing ones.

## Maintainer References

- Repo harness guidance: `docs/repo-harness-guidance.md`
