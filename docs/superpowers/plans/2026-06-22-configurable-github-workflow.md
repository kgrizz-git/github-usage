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

The GitHub Actions workflow at `.github/workflows/email-report.yml`
has these values hard-coded:

- `cron: '0 9 * * 1'` (line 5) — every Monday 09:00 UTC, not configurable.
- `workflow_dispatch` inputs (lines 8–35) — defaults for
  `include_consumers` (line 11), `include_artifact_storage` (line 19),
  `include_release_assets` (line 27), and `report_email` are baked into
  YAML and can only be changed by editing the file and pushing a commit.
- The shell block at lines 60–70 hard-codes the arg mapping
  (`--include-consumers`, etc.) and the values the user picks at
  `workflow_dispatch` time cannot be influenced by the local setup
  wizard.

Meanwhile the local `setup.sh` already collects most of the same
options in `.github-usage/config.toml` (`setup_config.py`, `DEFAULT_EMAIL_REPORT`)
and uses them for the macOS launchd flow. There is no path from that
config to the GitHub Actions workflow file.

The user wants `./setup.sh` to drive the GitHub Actions configuration
the same way it drives the launchd configuration.

---

## Design Decisions

1. **Config-driven workflow file (template render, not API mutation).**
   Move the current `.github/workflows/email-report.yml` to a sibling
   template with `__TOKEN__` placeholders, and have the wizard render
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
   The existing `[schedule]` section is **not touched by this plan** —
   it continues to drive only the launchd job and is independent of the
   GitHub Actions cron.
3. **No Jinja / no new runtime dependencies.** `str.replace()` on a
   checked-in template is enough and matches the project's "avoid
   unnecessary complexity" rule (`AGENTS.md`). `str.format()` cannot
   be used here because the workflow file contains `${{ }}` GitHub
   Actions expression syntax, which Python's format strings interpret
   as escaped braces and would mangle every `${{ secrets.* }}` and
   `${{ inputs.* }}` reference in the file. Tokens use `__UPPER__`
   double-underscore delimiters which cannot appear in valid YAML.
4. **Wizard does not auto-commit.** It writes the rendered file,
   prints a unified diff against the on-disk copy (not the committed
   copy — the user may have manual edits), and offers a copy-pasteable
   `git add … && git commit … && git push` line. The user stays in
   control of when the schedule change ships.
5. **Re-runs are idempotent and non-destructive of secrets.** Existing
   `gh secret set` calls in `setup_ci.py` continue to run independently;
   the new step only touches the workflow file.
6. **GitHub Actions cron is always UTC.** The cron expression in
   `email-report.yml` has no timezone field — GitHub Actions runs all
   cron schedules in UTC and does not support timezone suffixes. The
   wizard should document this prominently when prompting for the cron.
7. **`report_email` is intentionally not configurable via `[github_actions]`.**
   It is a per-run override for manual `workflow_dispatch` runs, not a
   default; users set it in the `workflow_dispatch` UI. It is not a
   persisted setting.

---

## Phase 1 — Template + Renderer Module

- [ ] **Create the workflow template** (tracked in git, not gitignored).
  **First step:** copy the current `email-report.yml` to
  `.github/workflows/email-report.yml.template`, then apply token
  replacements in-place. Do not create the template from scratch —
  copying ensures no lines are accidentally omitted from the 70-line file.
  Replace hard-coded values with `__TOKEN__` placeholders:
  - `__CRON__` — for the `cron:` value (line 5)
  - `__INCLUDE_CONSUMERS_DEFAULT__`, `__INCLUDE_ARTIFACT_STORAGE_DEFAULT__`,
    `__INCLUDE_RELEASE_ASSETS_DEFAULT__` — for the `default:` fields of
    the `workflow_dispatch` inputs (lines 11, 19, 27), rendered as
    `'true'` or `'false'` (with surrounding single quotes already in the
    template). **Do NOT add a token for `report_email`** — keep it as a
    plain `workflow_dispatch` string input with no default (see Design
    Decision 7). The template `default:` field looks like:
    ```yaml
    include_consumers:
      description: Include top repository breakdowns and key insights
      required: false
      default: __INCLUDE_CONSUMERS_DEFAULT__
      type: choice
      options:
        - 'false'
        - 'true'
    ```
  - In the `run:` block, each `${{ inputs.FLAG }}` comparison gets a
    `||` fallback using the same tokens:

    ```yaml
    # template (in email-report.yml.template):
    if [ "${{ inputs.include_consumers || '__INCLUDE_CONSUMERS_DEFAULT__' }}" = "true" ]; then
    ```

    ```yaml
    # rendered output (in email-report.yml) when include_consumers is true:
    if [ "${{ inputs.include_consumers || 'true' }}" = "true" ]; then
    ```

  This preserves full `workflow_dispatch` override behavior. On a
  scheduled run, `inputs.include_consumers` is `null` (the input is not
  defined at all — GitHub Actions does not set it to `""`), which is
  falsy in GitHub Actions expressions, so `|| 'true'` fires and the
  flag is included. On a manual dispatch where the user picks `"false"`,
  the non-empty string `"false"` is truthy so `||` never fires and the
  check correctly evaluates to false. The `workflow_dispatch` input
  dropdowns in the GitHub UI continue to work as overrides.

- [ ] **Add `src/github_usage/setup_workflow.py`.** New module
  (~80–120 lines) containing:
  - `DEFAULT_WORKFLOW_CONFIG` — dict with `cron`, `include_consumers`,
    `include_artifact_storage`, `include_release_assets`. (Distinct
    from `DEFAULT_SCHEDULE` which drives the local launchd job; the
    two crons are independent and have separate config sections.)
  - `validate_cron(expr: str) -> str` — accepts a 5-field cron
    expression (`m h dom mon dow`), returns the normalized form or
    raises `ValueError` with a clear message. No external
    dependencies. Rules: exactly 5 whitespace-separated fields, no
    `@`-shortcuts, no seconds field; `*` and `*/n` are valid in all
    fields; weekday `0–7`; comma-separated sub-expressions within a
    field (e.g., `0 9 * * 1,3` for Mon+Wed); ranges with `-`
    (e.g., `9-17`). Explicitly reject Quartz/Spring extensions `?`
    and `L` (GitHub Actions does not support them). Validate field
    count first, then per-field values. Document in the prompt that
    the schedule always runs in UTC.
  - `render_workflow(config: dict) -> str` — read the template from
    `workflow_path(root).with_suffix('.template')`, apply substitutions
    using `str.replace()` for each `__TOKEN__` (not `str.format()` —
    see Design Decision 3), return the rendered text. Token map:
    `__CRON__`, `__INCLUDE_CONSUMERS_DEFAULT__`,
    `__INCLUDE_ARTIFACT_STORAGE_DEFAULT__`,
    `__INCLUDE_RELEASE_ASSETS_DEFAULT__` (rendered as `'true'` or
    `'false'` with the surrounding single quotes already in the
    template's YAML string). Raise `FileNotFoundError` with a
    descriptive message if the template is missing — e.g.,
    `"Template not found: {path}. Re-clone the repository or restore
    the file from git."`.
  - `workflow_path(root: Path) -> Path` — `root/.github/workflows/email-report.yml`.
  - `write_workflow(root: Path, text: str) -> None` — call
    `workflow_path(root).parent.mkdir(parents=True, exist_ok=True)`
    first (handles first-run clones or deleted directory), then write
    atomically using `tempfile.NamedTemporaryFile(dir=workflow_path(root).parent,
    delete=False)` and `os.replace()` so an interrupted run does not
    leave a half-rendered file. Wrap the `os.replace()` call in a
    `try/finally` that removes the temp file if `os.replace` raises
    (disk full, permission denied, etc.), so orphaned temp files are
    never left behind. After the rename, call `os.chmod(dest, 0o644)`
    to match the expected permissions for a tracked YAML file
    (NamedTemporaryFile defaults to `0o600`).
  - `diff_workflow(root: Path, new_text: str) -> str` — return a
    unified diff (use `difflib.unified_diff`) comparing `new_text`
    against the **current on-disk file** (not the git HEAD version).
    Returns empty string when the file does not exist yet (first-time
    setup).

- [ ] **Wire the renderer into `setup_config.py`.**
  In `src/github_usage/setup_config.py`:
  - Import `DEFAULT_WORKFLOW_CONFIG` from the new module.
  - Extend `load_config` to merge a `github_actions` key
    using `DEFAULT_WORKFLOW_CONFIG` as the base.
  - Extend `write_config` to emit a `[github_actions]` block in the
    rendered TOML following the existing f-string style:
    ```toml
    [github_actions]
    cron = "0 9 * * 1"
    include_consumers = false
    include_artifact_storage = false
    include_release_assets = false
    ```
  - Extend `status_lines` to print one line summarizing the scheduled
    cron. When the `[github_actions]` key is absent from config,
    print `GitHub Actions: not configured`. When the workflow file
    is missing, append `(workflow file: missing)` instead of
    `(workflow file: present)`. Example:
    `GitHub Actions cron: 0 9 * * 1 (workflow file: present)`.

- [ ] **Update `_load_or_create_config` in `setup_wizard.py`.**
  The fallback path (no config file yet) currently returns only
  `email_report` and `schedule` keys. Add `github_actions` here too,
  using `DEFAULT_WORKFLOW_CONFIG`, so the first-run wizard has the
  same defaults as subsequent runs.

- [ ] **Update `.github-usage/config.example.toml`** with a commented
  `[github_actions]` block matching the defaults. Doing this in Phase 1
  (not Phase 4) keeps the example file in sync with what `write_config`
  now emits.

---

## Phase 2 — Wizard Integration

- [ ] **Add a wizard step `_configure_github_actions(paths)`.**
  In `src/github_usage/setup_wizard.py`:
  - Load or default `[github_actions]` via `load_config`.
  - Prompt:
    - `cron` — default from config, validated via `validate_cron`.
      Re-prompt on `ValueError`. Print cron examples alongside the
      prompt. Prominently note that the schedule runs in UTC. Include
      weekday field guidance: "Weekday: 0 or 7 = Sunday, 1 = Monday,
      ..., 6 = Saturday" (matches the `_configure_schedule` wording).
    - `include_consumers`, `include_artifact_storage`,
      `include_release_assets` — yes/no with current values as
      defaults, mirroring `_configure_email_options`.
  - Save via `write_config`.

- [ ] **Add a post-config step `_render_and_offer_commit(paths)`.**
  - Call `render_workflow(config)`.
  - Print `diff_workflow(root, rendered)` so the user sees what will
    change (diff is against the on-disk file).
  - If non-empty and the user agrees, call `write_workflow` and print
    the suggested `git add .github/workflows/email-report.yml && git
    commit -m "chore(workflow): update email-report schedule" && git
    push` (the message is illustrative; wizard does not run git
    itself).
  - If the file would be unchanged, print
    `Workflow file already up to date.` and skip.

- [ ] **Wire into `_full_setup` and the menu.**
  - In `_full_setup`, call `_configure_github_actions(paths)` after
    `_configure_schedule` (which is already there at line 237) and
    before `_verify_setup`. This keeps the order: env secrets →
    email options → local schedule → **GitHub Actions options** →
    verify → install launchd → CI secrets → dev hooks.
  - Update the `_full_setup` completion message to mention the
    workflow write.
  - **Renumber the menu.** Insert the new "GitHub Actions workflow"
    option after option 4 (local schedule). Shift current options
    5–9 down to 6–9, and assign the new option key `"0"` as the
    10th entry. The string `"0"` is truthy in Python, so
    `choice or "1"` at `setup_wizard.py:408` already handles it
    correctly — no parser changes needed. Do not use "4b" or
    two-digit keys. Update option 4's description to remove the
    claim "The GitHub Actions workflow has its own cron and ignores
    this value" — option 0 now addresses that.

---

## Phase 3 — Tests

- [ ] **New file `tests/test_setup_workflow.py`.** Cover:
  - `render_workflow` with default config (`include_consumers=False`)
    produces text containing `cron: '0 9 * * 1'` and
    `|| 'false'` in the consumers conditional.
  - `render_workflow` with `include_consumers=True` produces
    `|| 'true'` in the consumers conditional; likewise for the other
    two flags. No `__TOKEN__` strings remain in the output.
  - `render_workflow` output is valid YAML (use `yaml.safe_load`).
  - `render_workflow` with same config twice produces identical output
    (idempotent — call it twice and assert the two strings are equal).
  - `diff_workflow` returns empty string when the rendered output
    matches the on-disk file (write via `write_workflow` first, then
    assert `diff_workflow` returns `""`). This is a separate assertion
    from the idempotency check above — they test different things.
  - `validate_cron` accepts `0 9 * * 1`, `*/30 9-17 * * 1-5`,
    `0 0 1 * *`, `0 9 * * 1,3`; rejects `9 * * *` (4 fields),
    `0 9 * * 8` (invalid weekday), `not a cron`.
  - `diff_workflow` returns empty string when current and new match.
  - `write_workflow` is atomic — patch `os.replace` to raise
    `OSError` after `NamedTemporaryFile` completes, and assert
    the destination file is unchanged (or absent if it did not
    exist before), and assert the temp file is removed by the
    `finally` block in the implementation (not left orphaned).

- [ ] **Extend `tests/test_setup_wizard.py`.** Cover:
  - `_configure_github_actions` writes a `[github_actions]` block
    when given a non-interactive `input=` stream.
  - Invalid cron input triggers a re-prompt and eventually accepts
    or aborts (no infinite loop on EOF).
  - `_full_setup` invokes the renderer (mock
    `setup_workflow.write_workflow`) at least once.

- [ ] **Extend `tests/test_setup_config.py`** (create if absent) to
  round-trip `[github_actions]` through `load_config` /
  `write_config`, including the first-run fallback path via
  `_load_or_create_config`.

---

## Phase 4 — Documentation

- [ ] **Update `README.md`.** Add a short section under
  "Configuration" explaining:
  - The local launchd schedule vs the GitHub Actions cron are
    independent.
  - GitHub Actions cron always runs in UTC.
  - Running `./setup.sh` (or the new menu option) regenerates the
    workflow file; the user commits and pushes the change.
  - The four `gh` secrets remain unchanged by this plan.
  - `workflow_dispatch` manual runs respect per-run overrides in the
    GitHub UI as before; the configured values act as fallbacks for
    scheduled runs only.

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
| `src/github_usage/setup_wizard.py` | New `_configure_github_actions` + `_render_and_offer_commit`; wire into `_full_setup` and menu; update `_load_or_create_config` fallback; renumber menu. |
| `.github/workflows/email-report.yml.template` | New template with placeholder tokens (tracked in git). |
| `.github/workflows/email-report.yml` | Tracked in repo, regenerated by wizard. Keep current file as the rendered default so fresh clones keep working. |
| `.github-usage/config.example.toml` | Document `[github_actions]` block (Phase 1, not Phase 4). |
| `README.md` | New short section. |
| `tests/test_setup_workflow.py` | New tests. |
| `tests/test_setup_wizard.py` | Extended. |
| `tests/test_setup_config.py` | New or extended. |

---

## Resolved Decisions

1. **Menu key.** Renumber: insert the new option as `"0"` (the 10th
   item). The string `"0"` is truthy in Python so the existing
   `choice or "1"` default at `setup_wizard.py:408` works without
   change. Options 5–9 shift down to 6–9. Do not use "4b" or
   two-digit keys.
2. **Auto-commit.** Always manual. The wizard prints a copy-pasteable
   `git add … && git commit … && git push` line and does not run git.
   Consistent with the CI secrets approach.
3. **Cron syntax.** Minimal 5-field validation, no `croniter`. Accept
   comma-separated sub-expressions within fields (e.g., `0 9 * * 1,3`).
   Reject `@`-shortcuts and the seconds field. Document prominently
   that the schedule is always UTC.
4. **Multiple workflows.** Scoped to `email-report.yml` only. No need
   to generalize.
5. **Backwards compatibility.** `load_config` fills defaults for missing
   `[github_actions]` key. `_load_or_create_config` fallback also
   updated (Phase 1). No migration needed.
