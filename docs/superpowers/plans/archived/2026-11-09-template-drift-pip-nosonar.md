> **Status:** COMPLETE

> Line numbers cited below are accurate as of 2026-11-09; relocate by anchor (comment text / step name) if they drift.
>
> **Terminology:** user-facing name is **local full report** (CLI/TUI). Code modules still use `legacy_*` until the rename tracked in `TO_DO.md`.
>
> **Implementation log:** 2026-11-11 — corrected block applied to the template
> and the committed workflow identically; 3 pinning tests added
> (render assertion, block-agreement, render-vs-committed byte-parity);
> deepseek review APPROVE (no blockers/majors; stale Scope bullet fixed,
> test import hoisted, new test moved after the forecast group).

# Port Manual pip-install Comment + NOSONAR into email-report Template

## Problem

The committed workflow `.github/workflows/email-report.yml:72-75` carries a
hand-added 3-line explanatory comment plus a `# NOSONAR` suppression on the
`pip install -e .` step:

```yaml
      # Editable install of this repo's own package. pip does not read uv.lock;
      # the core package currently declares no runtime dependencies, so nothing
      # else is resolved here.
      - run: pip install -e .  # NOSONAR
```

The generator template `.github/workflows/email-report.yml.template:72` emits
only the bare step:

```yaml
      - run: pip install -e .
```

`render_workflow()` (`setup_workflow.py:109-147`) passes static template text
through unchanged, so the next setup regeneration (option 5 / wizard /
`write_workflow`) silently drops both the comment and the suppression. The
suppression loss is the real risk: it currently silences
`githubactions:S8541`/`S8544` (unpinned package versions / dependencies —
see `CHANGELOG.md` and commit `d7f143f5`), which would fire again on the next
regenerated workflow.

One correction before porting: the comment's last line ("nothing else is
resolved here") overclaims. `pyproject.toml:2` (`[build-system] requires`)
pins only `setuptools>=77.0.3` — a range, not a pin — and pip resolves that
build backend in an isolated env, not from `uv.lock`. The suppression remains
appropriate (the only unpinned resolution is the setuptools build backend for
this repo's own package install in CI; no third-party runtime code is installed
unpinned — `dependencies` is empty), but the comment must say so honestly. The
corrected wording below replaces the third line; it goes into the template
**and** the committed workflow identically so parity holds.

Tracked in `TO_DO.md` (Code Health): remove that item when this plan is
complete (per repo rule, completed items are removed, not checked off).

## Scope

- Single edit to `email-report.yml.template`: expand the single line 72 into
  the 4-line block below (corrected third line — see Problem). Apply the
  identical block to the committed `email-report.yml:72-75` so the two files
  stay byte-identical outside the generator placeholders:

  ```yaml
        # Editable install of this repo's own package. It declares no runtime
        # dependencies, but pip still resolves the setuptools>=77.0.3 build
        # backend in an isolated env (not from uv.lock).
        - run: pip install -e .  # NOSONAR
  ```

  Bare `# NOSONAR` is the repo standard; parameterized forms like
  `# NOSONAR(rule)` are invalid and rejected by `python:S7632` (commit
  `d7f143f5`). The suppression guards the *regenerated workflow output*,
  not the template file itself.
- No change to `render_workflow()` — static text passes through; no new
  placeholder needed.
- The corrected block also replaces the old wording in the committed `email-report.yml` (it already had a block, but with the overclaiming third line) so both files stay identical.
- Verify there is no *other* committed-vs-template drift while here (last
  verified 2026-11-09: the pip-install block was the only delta).

## Out of scope

- Changing install behavior or the suppression itself.
- Other workflow/template drift (none known).
- The API-call-tracking plan and the `--max-repos` cap raise (same branch,
  separate commits).

## Done criteria

- Template and committed workflow contain the corrected comment block and the
  `# NOSONAR` suffix verbatim (identical in both files).
- `render_workflow()` output from an in-memory test config matching the
  committed workflow's parameters (`include_consumers=True`,
  `include_artifact_storage=True`, `email_format="html"`, `max_repos=100`,
  `warn_over=["25", "80%"]`) equals the committed `email-report.yml`
  byte-for-byte (zero drift across all static template lines). Do NOT verify
  against the local gitignored `.github-usage/config.toml`: it varies per
  machine, so a local-config parity check passes only by coincidence.
- New/updated tests pin the block in both files (see Test plan).
- `scripts/check` and `scripts/docs-check` pass.
- SonarCloud PR check stays green, confirming the regenerated workflow keeps
  its `S8541`/`S8544` suppression. If Sonar flags anything new, stop and
  reassess rather than forcing it through.
- No `CHANGELOG.md` entry: template-only change, not user-visible behavior
  (per `AGENTS.md` done criteria, docs/changelog updates are for user-visible
  changes).
- Remove the `TO_DO.md` item and move this plan to
  `docs/superpowers/plans/archived/` in the same change set, before
  commit/merge (per `AGENTS.md` documentation lifecycle), with the status
  banner set to the canonical `> **Status:** COMPLETE` form.

## Test plan

- `tests/test_setup_workflow.py`: extend with an assertion that
  `render_workflow()` output contains the comment text and the
  `pip install -e .  # NOSONAR` line (guards the template, the generator's
  only input for this block).
- `tests/test_workflow_templates.py`: assert the committed workflow and the
  template agree on the pip-install block (same corrected comment + same
  `# NOSONAR`), guarding drift in both directions.
- Parity check as a test (not a manual local-config diff): render from an
  in-memory config matching the committed workflow's parameters
  (`include_consumers=True`, `include_artifact_storage=True`,
  `email_format="html"`, `max_repos=100`, `warn_over=["25", "80%"]`) and
  assert byte-equality with the committed `email-report.yml`, so the check is
  machine-independent (the local gitignored `config.toml` varies per
  workstation and must not be the reference).
- Keep assertions to `assertIn` on the distinctive strings (comment first
  line, `# NOSONAR` on the pip-install line) rather than full-file compares,
  so unrelated profile-arg changes do not break them.

## Task breakdown

- [x] Port the comment + `# NOSONAR` into `email-report.yml.template`.
  **Done:** 2026-11-11 — corrected 4-line block in the template; identical
  block replaces the old wording in the committed workflow.
- [x] Add the `test_setup_workflow.py` render assertion and the
  `test_workflow_templates.py` parity assertion.
  **Done:** 2026-11-11 — render assertion, block-agreement test, and
  render-vs-committed byte-parity test (in-memory config, machine-independent).
- [x] Verify static parity via the updated unit tests (in-memory config
  matching the committed workflow's parameters, not the local gitignored
  config); run `scripts/check` and `scripts/docs-check`.
  **Done:** 2026-11-11 — byte-parity confirmed (3253 == 3253 bytes); tests,
  typecheck, docs-check, and ruff (repo-pinned 0.9.6) green.
- [x] Confirm SonarCloud check green on the PR; remove the `TO_DO.md` item;
  archive this plan.
  **Done:** 2026-11-11 — `TO_DO.md` item removed; plan archived in the same
  change set. SonarCloud green to be confirmed on the PR.
