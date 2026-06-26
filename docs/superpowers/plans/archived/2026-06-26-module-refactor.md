> **Status:** COMPLETE
>
> Refactor plan for the Code Health item in TO_DO.md. All 6 phases implemented; `scripts/check`, `scripts/smoke`, `scripts/docs-check` pass and 274 tests pass.

**Date:** 2026-06-26

## Objective

Bring `src/github_usage/` modules and functions within the advisory size thresholds enforced by `scripts/check-sizes` (file limit: 500 lines, warn: 400; function limit: 100 lines, warn: 80).

## Current State

| File / Function | Lines | Status |
|---|---|---|
| `setup_wizard.py` | 545 | **Over 500 limit** |
| `cli._run_email_report` | ~99 | Over 80 warn, near 100 limit |
| `legacy_report.main` | ~96 | Over 80 warn, near 100 limit |
| `src/github_usage/scripts/api_discovery_month.main` | ~82 | At 80 warn threshold |
| `report_data.build_report_data` | ~81 | At 80 warn threshold |

## Definition of Done

- `setup_wizard.py` is under the 400-line warn threshold.
- Each flagged function under the 100-line limit (ideally under 80).
- `scripts/check` passes.
- `scripts/check-sizes` shows no warnings.
- `scripts/docs-check` passes (required by AGENTS.md after doc/CLI help changes).
- Existing tests pass and coverage is maintained.
- `CHANGELOG.md` updated under `[Unreleased] > Changed`.

## Design Decisions

1. **Extract, don't rewrite.** Each extraction relocates existing code verbatim into a focused module, then re-imports it. No behavioral changes during refactoring.
2. **Prefer existing modules** over new ones where there is a thematic fit. This keeps the package directory navigable.
3. **One phase per target** so each change is independently reviewable and revertible.
4. **No new public API surface.** All extracted functions remain module-private (prefixed with `_`).
5. **Defer imports to break circular cycles.** `setup_config.py` imports `DEFAULT_WORKFLOW_CONFIG` from `setup_workflow.py` at module level. If `setup_workflow.py` imports back from `setup_config.py` at module level, a circular cycle arises. Any new import from `setup_config` inside `setup_workflow.py` must use a local/deferred import inside the function body, not a top-level import.

## Proposed Implementation

### Phase 1: Split `setup_wizard.py`

Extract six groups of functions into focused modules:

| Group | Functions | Destination |
|---|---|---|
| Email config prompting | `_configure_email_options`, `_prompt_email_format` | New `setup_email_config.py` |
| Secrets & token | `_resolve_github_token`, `_configure_env_secrets`, `_apply_env` | New `setup_secrets.py` |
| GitHub Actions config | `_configure_github_actions`, `_render_and_offer_commit` | Existing `setup_workflow.py` |
| Schedule config | `_configure_schedule` | Existing `setup_config.py` |
| Dev hooks | `_configure_dev_hooks` | Existing `setup_ci.py` |
| Launchd dispatcher | `_configure_launchd` | Existing `setup_launchd.py` |

**Cross-module dependencies:**

- **`_load_or_create_config` → `setup_config.py`.** Called by `_configure_email_options`, `_configure_github_actions`, `_render_and_offer_commit`, and `_configure_schedule` (in file order, see `setup_wizard.py:89, 127, 156, 175`). If it stays in `setup_wizard.py`, the extracted submodules would need to import it back, creating a circular dependency. They move to `setup_email_config.py`, `setup_workflow.py`, `setup_workflow.py`, and `setup_config.py` respectively. After the move, `_configure_github_actions` and `_render_and_offer_commit` in `setup_workflow.py` will need a **deferred (in-function) import** of `_load_or_create_config` from `setup_config.py` — per Design Decision #5, a top-level import would create a cycle (`setup_config.py` already imports from `setup_workflow.py`).
- **`_configure_launchd` → `setup_config._configure_schedule`** (when installing a LaunchAgent without a pre-existing `config.toml`, see `setup_wizard.py:275`). `setup_launchd.py` will need to import `_configure_schedule` from `setup_config.py`. Safe — `setup_config.py` does not import from `setup_launchd.py`, so the existing one-way `setup_launchd → setup_config` edge is preserved.
- **`_apply_env` → `setup_wizard.py` import (back from `setup_secrets.py`).** `_apply_env` moves to `setup_secrets.py` but is also called by `_verify_setup` (`setup_wizard.py:246`), which stays. After extraction, `setup_wizard.py` must import `_apply_env` from `setup_secrets.py`.

> **Important:** Update test mocks and imports *immediately* when extracting functions, not at the end. Each Phase 1 sub-extraction commit must update the corresponding test imports and mock targets, or tests will be broken between phases.

Remaining in `setup_wizard.py` (~365 lines after extraction and back-imports): `_setup_parser`, `_verify_setup`, `_full_setup`, all `_*_only` handlers, `_MENU_OPTIONS`, `_print_menu`, `_interactive_menu`, `_print_status`, `run_setup`. The 400-line warn threshold leaves ~35 lines of margin — treat it as a hard ceiling, not a guideline.

### Phase 2: Trim `cli._run_email_report` (~99 → ~55)

Target is under 80 lines (the warn threshold) so `scripts/check-sizes` shows no warnings.

- Extract the section/skip validation block (`include_actions`, `include_copilot`, `include_lfs`, `args.include_artifact_storage`) into a new `_validate_report_sections` helper. This is a different concern from `_validate_email_flags` (which only checks `--max-repos >= 1`, see `cli.py:148-153`) — do not merge.
- Extract token resolution + API init + scope check into a `_init_github_api` helper. **Note:** the env var check (`cli.py:191-197`, `RESEND_*` keys, only when not `dry_run`) and the `_confirm_release_assets` prompt (`cli.py:199-200`) currently sit between API init and the scope check. Hoist both blocks above the API init so the helper extraction is contiguous; they do not depend on the GitHub API and the reorder is safe.
- Extract the email-sending block (construct subject, call `email_report.send_email`) into a module-private helper.

### Phase 3: Trim `legacy_report.main` (~96 → ~70)

- Extract the report body (Actions → repos → Copilot → LFS → costs → limits → final summary → what-else) into a `_run_report_body` helper.

### Phase 4: Trim `src/github_usage/scripts/api_discovery_month.main` (~82 → ~60)

- Extract the endpoint definition + testing loop into a `_probe_endpoints` helper.

### Phase 5: Trim `report_data.build_report_data` (~81 → ~65)

- Extract the loop **and** the subsequent section-getter blocks into a `_fetch_sections` helper. The helper should accept the report dict (mutated in place) and the errors dict, and own:
  - The per-key enabled/getter loop (`actions`, `copilot`, `git_lfs`).
  - The `monthly_costs` `try/except` (which also seeds the empty-cost fallback on error).
  - The `repo_consumers`, `artifact_storage`, and `release_assets` `try/except` blocks (each gated on its respective `include_*` flag).
- `build_report_data` keeps the pre-fetch wiring (repos + rate limit, `api_estimate`, quota guard, base `report` dict construction) and the post-fetch tail (`get_key_insights`, `get_warning_state`, `return`).

### Phase 6: Final verification

- Run `scripts/check`, `scripts/check-sizes`, and the full test suite. Test mocks and imports were updated immediately during each prior phase, so this run is to catch any stragglers, not to do a bulk re-point.
- Update `TO_DO.md` (remove item) and `CHANGELOG.md`.
- Move completed plan to `archived/`, log merge commit.

## Out of Scope

- `email_report.py` (511 lines) is also over the file limit. Deferred — needs its own targeted plan.
- Behavioral changes, new features, or API surface additions.
- Renaming or reorganizing existing extracted modules (`setup_prompts.py`, `setup_config.py`, etc.).
