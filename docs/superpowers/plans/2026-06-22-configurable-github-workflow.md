# [2026-06-22 00:00] Implementation Plan — Configurable GitHub Actions Workflow Options

> **Status: PLANNED (not started).** Awaiting approval before implementation.

This plan addresses the request to make the scheduled GitHub Actions
email-report workflow configurable via `./setup.sh` instead of having
its cron and report-section defaults hard-coded in
`.github/workflows/email-report.yml`.

> **For agentic workers:** Steps use checkbox (`- [x]`) syntax for tracking.
> Run `scripts/check` after each phase.

---

## Problem Statement

The GitHub Actions workflow at `.github/workflows/email-report.yml:1`
has these values hard-coded:

- `cron: '0 9 * * 1'` (line 5) — every Monday 09:00 UTC, not configurable.
- `workflow_dispatch` inputs (lines 7–35) — defaults for
  `include_consumers`, `include_artifact_storage`,
  `include_release_assets`, and `report_email` are baked into YAML and
  can only be changed by editing the file and pushing a commit.
- The shell block at lines 60–69 hard-codes the arg mapping
  (`--include-consumers`, etc.) and the values the user picks at
  `workflow_dispatch` time cannot be influenced by the local setup
  wizard.

Meanwhile the local `setup.sh` already collects most of the same
options in `.github-usage/config.toml` (`src/github_usage/setup_config.py:20`)
and uses them for the macOS launchd flow. There is no path from that
config to the GitHub Actions workflow file.

The user wants `./setup.sh` to drive the GitHub Actions configuration
the same way it drives the launchd configuration.

---

## Design Decisions

1. **Config-driven workflow file (template render, not API mutation).**
   Move the current `.github/workflows/email-report.yml` to a sibling
   template with `{placeholder}` tokens, and have the wizard render
   it to `.github/workflows/email-report.yml` on each run. Rationale:
   - GitHub's `PUT /repos/{owner}/{repo}/actions/workflows/{id}` API
     can update the schedule on a published workflow, but only for
     the *existing* `main` copy and only with elevated scopes —
     fragile on a fresh clone.
   - Rendering keeps the file reviewable in PRs, which matches how
     everything else in this repo changes.
2. **Add a `[github_actions]` section to `.github-usage/config.toml`.**
   Mirrors the structure of `[email_report]` so the wizard can prompt
   for cron + the same three section toggles used by `workflow_dispatch`.
3. **No Jinja / no new runtime dependencies.** Plain `str.format()` /
   `str.replace()` on a checked-in template is enough and matches the
   project's "avoid unnecessary complexity" rule (`AGENTS.md`).
4. **Wizard does not auto-commit.** It writes the rendered file,
   prints a unified diff against the committed copy, and offers a
   copy-pasteable `git add … && git commit … && git push` line. The
   user stays in control of when the schedule change ships.
5. **Re-runs are idempotent and non-destructive of secrets.** Existing
   `gh secret set` calls in `src/github_usage/setup_ci.py:55` continue
   to run independently; the new step only touches the workflow file.

---

## Phase 1 — Template + Renderer Module

- [ ] **Create the workflow template.**
  Add `.github/workflows/email-report.yml.template` with the exact
  body of the current `email-report.yml` (`.github/workflows/email-report.yml:1-70`),
  replacing the hard-coded values with tokens:
  - `{cron}` — for the `cron:` line
  - `{include_consumers_default}`, `{include_artifact_storage_default}`,
    `{include_release_assets_default}` — for the `default:` fields of
    the `workflow_dispatch` inputs
  - `{arg_consumer}`, `{arg_artifact}`, `{arg_release}` — for the
    conditional arg appends in the `run:` block (empty string when
    the flag is off, e.g. `args+=(--include-consumers)` when on)

  The renderer fills these with the strings `''` (empty, single
  quotes) when the boolean is false, so the resulting YAML is valid
  without further conditional logic.

- [ ] **Add `src/github_usage/setup_workflow.py`.** New module
  (~80–120 lines) containing:
  - `DEFAULT_GITHUB_ACTIONS` — dict with `cron`, `include_consumers`,
    `include_artifact_storage`, `include_release_assets` (mirrors
    `setup_config.py:20` style).
  - `validate_cron(expr: str) -> str` — accepts a 5-field cron
    expression (`m h dom mon dow`), returns the normalized form or
    raises `ValueError` with a clear message. No external
    dependencies; use `croniter`-style field-by-field parsing
    restricted to the values GitHub supports (no `@`-shortcuts, no
    seconds field).
  - `render_workflow(config: dict) -> str` — read the template from
    the repo root, do the substitutions, return the rendered text.
  - `workflow_path(root: Path) -> Path` — `root/.github/workflows/email-report.yml`.
  - `write_workflow(root: Path, text: str) -> None` — write atomically
    (write to `.tmp`, rename) so an interrupted run does not leave a
    half-rendered file.
  - `diff_workflow(root: Path, new_text: str) -> str` — return a
    unified diff (use `difflib.unified_diff`) for display. Returns
    empty string when the file does not exist yet (first-time setup).

- [ ] **Wire the renderer into `setup_config.py`.**
  In `src/github_usage/setup_config.py`:
  - Import `DEFAULT_GITHUB_ACTIONS` from the new module.
  - Extend `load_config` (line 126) to merge a `github_actions` key
    using `DEFAULT_GITHUB_ACTIONS` as the base.
  - Extend `write_config` (line 139) to emit a new `[github_actions]`
    block in the rendered TOML with `cron`, `include_consumers`,
    `include_artifact_storage`, `include_release_assets`.
  - Extend `status_lines` (line 200) to print one line summarizing
    the scheduled cron, e.g.
    `GitHub Actions cron: 0 9 * * 1 (workflow file: present)`.

---

## Phase 2 — Wizard Integration

- [ ] **Add a wizard step `_configure_github_actions(paths)`.**
  In `src/github_usage/setup_wizard.py`:
  - Load or default `[github_actions]` via `load_config`.
  - Prompt:
    - `cron` — default from config, validated via `validate_cron`.
      Re-prompt on `ValueError`. Offer a helper that prints
      `crontab.guru`-style examples in the prompt description.
    - `include_consumers`, `include_artifact_storage`,
      `include_release_assets` — yes/no with current values as
      defaults, mirroring `_configure_email_options` (line 77).
  - Save via `write_config`.

- [ ] **Add a post-config step `_render_and_offer_commit(paths)`.**
  - Call `render_workflow(config)`.
  - Print `diff_workflow(root, rendered)` so the user sees what will
    change.
  - If non-empty and the user agrees, call `write_workflow` and print
    the suggested `git add .github/workflows/email-report.yml && git
    commit -m "chore(workflow): update email-report schedule" && git
    push` (the message is illustrative; wizard does not run git
    itself).
  - If the file would be unchanged, print
    `Workflow file already up to date.` and skip.

- [ ] **Wire into `_full_setup` and the menu.**
  - In `_full_setup` (`setup_wizard.py:234`), call
    `_configure_github_actions(paths)` after `_configure_schedule`
    (so the existing launchd schedule is still configured first) and
    before `_configure_ci_secrets`. This keeps the order: env →
    email options → local schedule → **GitHub Actions options** →
    install launchd → CI secrets → dev hooks.
  - Update the `_full_setup` summary line
    (`setup_wizard.py:253`) to mention the workflow write.
  - Add a new menu entry between the existing schedule and
    LaunchAgent items, e.g.
    ```
    4b) GitHub Actions workflow options
        Configure the scheduled GitHub Actions cron and the
        workflow_dispatch defaults. Writes .github/workflows/
        email-report.yml; you commit and push when ready.
    ```
    Use a single-digit key consistent with the existing scheme
    (likely renumber subsequent items — accept the small doc
    churn).
  - Update the description of menu option 4 (line 332) to remove the
    claim that "The GitHub Actions workflow has its own cron and
    ignores this value." once the new option exists.

---

## Phase 3 — Tests

- [ ] **New file `tests/test_setup_workflow.py`.** Cover:
  - `render_workflow` with default config produces text that
    contains `cron: '0 9 * * 1'` and omits `--include-consumers`
    from the `run:` block.
  - `render_workflow` with all toggles on produces
    `--include-consumers`, `--include-artifact-storage`, and
    `--include-release-assets --yes-include-release-assets`.
  - `validate_cron` accepts `0 9 * * 1`, `*/30 9-17 * * 1-5`,
    `0 0 1 * *`; rejects `9 * * *` (4 fields), `0 9 * * 8`
    (Sunday=0 or 7 only; 8 is invalid), `not a cron`.
  - `diff_workflow` returns empty string when current and new match.
  - `write_workflow` is atomic — simulate an exception during write
    and assert the destination file is not corrupted (or does not
    exist if it did not exist before).

- [ ] **Extend `tests/test_setup_wizard.py`.** Cover:
  - `_configure_github_actions` writes a `[github_actions]` block
    when given a non-interactive `input=` stream.
  - Invalid cron input triggers a re-prompt and eventually accepts
    or aborts (no infinite loop on EOF).
  - `_full_setup` invokes the renderer (mock
    `setup_workflow.write_workflow`) at least once.

- [ ] **Extend `tests/test_setup_config.py`** (create if absent) to
  round-trip `[github_actions]` through `load_config` /
  `write_config`.

---

## Phase 4 — Documentation & Examples

- [ ] **Update `.github-usage/config.example.toml`** to include a
  commented `[github_actions]` block with the same defaults
  shipped by the wizard.

- [ ] **Update `README.md`.** Add a short section under
  "Configuration" explaining:
  - The local launchd schedule vs the GitHub Actions cron are
    independent.
  - Running `./setup.sh` (or the new menu option) regenerates the
    workflow file; the user commits and pushes the change.
  - The four `gh` secrets remain unchanged by this plan.

- [ ] **Run `scripts/docs-check`.** Make sure the README changes pass
  the existing doc-validation script (it checks help text / CLI
  docstrings, but flag if it also references config keys).

---

## Phase 5 — Verification

- [ ] `scripts/check` passes (syntax, unit tests, smoke, sizes).
- [ ] `scripts/smoke` passes.
- [ ] `scripts/docs-check` passes.
- [ ] Manual: run `./setup.sh`, pick the new menu option, change
  cron to `0 8 * * 1`, confirm:
  - `.github/workflows/email-report.yml` now has
    `cron: '0 8 * * 1'`.
  - `git diff .github/workflows/email-report.yml` shows the expected
    one-line change.
  - Re-running the menu option with the same value prints
    `Workflow file already up to date.`
- [ ] Manual: `gh workflow run email-report.yml` from a branch that
  has the new file and confirm the workflow starts and the secrets
  are still wired.

---

## Files Touched

| File | Change |
| --- | --- |
| `src/github_usage/setup_workflow.py` | New module: defaults, cron validation, template render, atomic write, diff. |
| `src/github_usage/setup_config.py` | Add `github_actions` to `load_config` / `write_config` / `status_lines` / `DEFAULT_*` imports. |
| `src/github_usage/setup_wizard.py` | New `_configure_github_actions` + `_render_and_offer_commit`; wire into `_full_setup` and menu. |
| `.github/workflows/email-report.yml.template` | New template with placeholder tokens. |
| `.github/workflows/email-report.yml` | Tracked in repo, regenerated by wizard. Keep current file as the rendered default so fresh clones keep working. |
| `.github-usage/config.example.toml` | Document `[github_actions]` block. |
| `README.md` | New short section. |
| `tests/test_setup_workflow.py` | New tests. |
| `tests/test_setup_wizard.py` | Extended. |
| `tests/test_setup_config.py` | New or extended. |

---

## Open Questions for Approval

1. **Menu key.** Renumbering 4 → "schedule", 4b/new key "GitHub
   Actions", 5 → launchd, 6 → secrets, etc. is the cleanest. Accept
   the small renumber, or keep 4 unchanged and insert the new step
   as 10 (less discoverable)?
2. **Auto-commit.** Should the wizard ever `git add` /
   `git commit` for the user, or always require manual action? Plan
   currently assumes manual. The CI secrets step already calls
   `gh` without committing; the workflow file is in-repo and
   should match the same hand-on-keyboard convention.
3. **Cron syntax.** GitHub Actions cron is restricted (no seconds,
   no `@` shortcuts, weekday `0-7`). The plan validates the 5-field
   form and rejects values GitHub would also reject. OK to keep it
   minimal, or pull in `croniter` for friendlier parsing?
4. **Multiple workflows.** Only one workflow file exists. The plan
   scopes to that one. No need to generalize to "any workflow
   path" yet.
5. **Backwards compatibility for existing setups.** Existing
   `.github-usage/config.toml` files will not have a
   `[github_actions]` block; `load_config` will fill defaults.
   Confirmed safe; nothing to migrate.

Once these are confirmed, this plan is ready to execute in the
phase order above.
