> **Status:** IN PROGRESS

> Line numbers cited below are accurate as of 2026-11-09; relocate by anchor (comment text / step name) if they drift.
>
> **Terminology:** user-facing name is **local full report** (CLI/TUI). Code modules still use `legacy_*` until the rename tracked in `TO_DO.md`.
>
> **Implementation log:** (none yet)

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
editable install of this repo's own package, versions pinned via
`pyproject`/`uv.lock`; see `CHANGELOG.md` and commit `d7f143f5`), which would
fire again on the next regenerated workflow.

Tracked in `TO_DO.md` (Code Health): remove that item when this plan is
complete (per repo rule, completed items are removed, not checked off).

## Scope

- Single edit to `email-report.yml.template`: expand the single line 72 into
  the exact 4-line block from the committed workflow (lines 72-75) — the
  3-line comment plus `  # NOSONAR` on the `- run: pip install -e .` step.
  Bare `# NOSONAR` is the repo standard; parameterized forms like
  `# NOSONAR(rule)` are invalid and rejected by `python:S7632` (commit
  `d7f143f5`). The suppression guards the *regenerated workflow output*,
  not the template file itself.
- No change to `render_workflow()` — static text passes through; no new
  placeholder needed.
- No change to the committed `email-report.yml` — it already has the block.
- Verify there is no *other* committed-vs-template drift while here (last
  verified 2026-11-09: the pip-install block was the only delta).

## Out of scope

- Rewording the comment or changing install behavior.
- Other workflow/template drift (none known).
- The API-call-tracking plan and the `--max-repos` cap raise (same branch,
  separate commits).

## Done criteria

- Template contains the comment block and the `# NOSONAR` suffix verbatim.
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
  template agree on the pip-install block (same comment + same `# NOSONAR`),
  guarding drift in both directions.
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

- [ ] Port the comment + `# NOSONAR` into `email-report.yml.template`.
- [ ] Add the `test_setup_workflow.py` render assertion and the
  `test_workflow_templates.py` parity assertion.
- [ ] Verify static parity via the updated unit tests (in-memory config
  matching the committed workflow's parameters, not the local gitignored
  config); run `scripts/check` and `scripts/docs-check`.
- [ ] Confirm SonarCloud check green on the PR; remove the `TO_DO.md` item;
  archive this plan.
