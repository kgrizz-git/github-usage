> **Status:** COMPLETE
>
> All 5 phases implemented: `email_report.py` is now a 12-line re-export facade over `email_report_text` (186 lines), `email_report_html` (267 lines), `email_report_send` (50 lines), and `_email_report_common` (20 lines). `scripts/check`, `scripts/smoke`, `scripts/docs-check`, `pre-commit run --all-files`, and the 274-test suite all pass.

**Date:** 2026-06-26

## Objective

Bring `src/github_usage/email_report.py` under the 500-line file limit (warn at 400) checked by `scripts/check-sizes`. Split it into focused sub-modules with no behavioral changes and a preserved public API.

## Current State

| File | Lines | Status |
|---|---|---|
| `email_report.py` | 511 | **Over 500 limit** |

The file holds three distinct concerns: plain-text section formatters, HTML section formatters (parallel structure, completely different markup), and Resend HTTP delivery. Two helpers (`_generated_line`, `_bytes_to_mb`) are shared between the text and HTML formatters.

`scripts/check-sizes` is **advisory** (always exits 0; see its own docstring). Crossing the threshold is a self-imposed style rule, not a build gate — but the resulting unwieldy file is the real motivation.

## Definition of Done

- `email_report.py` is under the 400-line warn threshold.
- `scripts/check` passes.
- `scripts/check-sizes` shows no warnings on the new modules and on the facade.
- `scripts/smoke` passes.
- `scripts/docs-check` passes.
- `pre-commit run --all-files` passes (covers ruff lint + format, which `scripts/check` does not run).
- Existing tests pass and coverage is maintained.
- `CHANGELOG.md` updated under `[Unreleased] > Changed`.

## Design Decisions

1. **Extract, don't rewrite.** Each extraction relocates existing code verbatim into a focused module, then re-imports it. No behavioral changes during refactoring. *Implication:* the function-level `from . import http_retry` in `send_email` (`email_report.py:486`) stays where it is — do not hoist it to module level.
2. **Preserve the public API.** Tests and other callers do `from github_usage.email_report import format_report_email, format_html_report, default_subject, send_email` (verified at `test_email_report.py:11, 26, 56, 81, 100, 142, 159, 175, 200, 234, 293, 325`). The facade must keep these names available.
3. **Prefer new modules over splitting one module** when there is a thematic fit. Each concern (text, HTML, send) gets its own file with a clear single responsibility.
4. **One phase per sub-extraction** so each change is independently reviewable and revertible.
5. **No new public API surface.** All extracted functions remain module-private (prefixed with `_`) except the four the facade re-exports. The package's public surface is still `github_usage.email_report`.
6. **Shared helpers go in a private common module** (not duplicated, not folded into one of the new modules with a cross-import). Done **first**, before any consumer phase, to avoid a circular import where `email_report.py` re-exports `format_report_email` from `email_report_text.py` while `email_report_text.py` imports shared helpers from `email_report.py`.
7. **Test changes are part of each phase, not a final cleanup step.** Direct imports and module-attribute accesses break between phases; mocks-only is insufficient. Each phase that moves test-visible names must update the test in the same commit.
8. **All facade re-exports use the `name as name` redundant-alias form.** This is the standard pyflakes/ruff idiom that flags an import as an intentional re-export (suppresses F401), so `pre-commit`'s `ruff --fix` does not silently delete the facade imports on commit. Plain `from .email_report_text import format_report_email` is **not** safe here — `ruff --fix` removes it.

## Per-Module Imports (must be added when functions move)

| Module | Imports needed |
|---|---|
| `_email_report_common.py` | `from datetime import UTC, datetime` |
| `email_report_text.py` | `from ._email_report_common import _bytes_to_mb, _generated_line`<br>`from .report_helpers import fmt_price` |
| `email_report_html.py` | `import html`<br>`from ._email_report_common import _bytes_to_mb, _generated_line`<br>`from .report_helpers import fmt_price` |
| `email_report_send.py` | `from datetime import UTC, datetime`<br>`import json`<br>`from . import http_retry` *(function-level, per Design Decision 1)* |

`html` and `json` are stdlib. `fmt_price` is in `report_helpers.py`. `http_retry` is in the package.

## Proposed Implementation

### Phase 1: Extract shared helpers → `_email_report_common.py`

- Move to `_email_report_common.py`:
  - `_generated_line` at `email_report.py:18-27` (used by both text and HTML formatters).
  - `_bytes_to_mb` at `email_report.py:30-31` (used by both text and HTML section formatters).
- New module gets a one-line module docstring (ruff D100 is selected; not auto-fixable).
- `email_report.py` imports from `_email_report_common` (the helpers are used internally by `format_report_email` and `format_html_report`).
- **Test changes required** in this phase (the plan previously claimed none — that was wrong):
  - `tests/test_email_report.py:35` does `from github_usage.email_report import _generated_line`. Update to `from github_usage._email_report_common import _generated_line`.
  - `tests/test_email_report.py:47` does `from github_usage.email_report import _generated_line`. Update to `from github_usage._email_report_common import _generated_line`.
  - The import was missed in the previous draft of this plan; both lines are direct imports that break the moment the helper moves.

Doing this first avoids the circular-import problem that would occur if a later phase tried to import these from `email_report.py` while `email_report.py` was already re-exporting from a new sub-module.

### Phase 2: Extract plain-text formatting → `email_report_text.py`

- Move to `email_report_text.py`:
  - All `_format_*_section` text functions (actions, copilot, git_lfs, monthly_costs, consumers, artifact_storage, release_assets, insights, errors) at `email_report.py:42-175`.
  - `_SECTION_FORMATTERS` tuple at `email_report.py:178-188`.
  - `_cost_line` helper at `email_report.py:34-39` — used only by the text `_format_monthly_costs_section`, so it belongs here. (The parallel `_html_cost_row` at `email_report.py:215-221` is HTML-only and will move in Phase 3.)
  - `format_report_email` at `email_report.py:191-212`.
- New module gets a one-line module docstring.
- Imports needed in `email_report_text.py`: see the per-module imports table above.
- `email_report.py` re-exports `format_report_email` using the alias form:
  ```python
  from .email_report_text import format_report_email as format_report_email
  ```
  This survives `ruff --fix` (Design Decision 8). Plain `from .email_report_text import format_report_email` would be auto-removed as F401 and silently break `test_email_report.py:11, 56`.
- **Test changes required** in this phase:
  - `tests/test_email_report.py:121` does `from github_usage.email_report import _format_actions_section` (direct import, not a mock). Update to `from github_usage.email_report_text import _format_actions_section`.
  - `tests/test_email_report.py:284` does `email_report._SECTION_FORMATTERS` (module-attribute access). Update to `from github_usage import email_report_text; text_formatters = email_report_text._SECTION_FORMATTERS`. Leave the `from github_usage import email_report` line in place — `_SECTION_HTML_FORMATTERS` still lives there until Phase 3.

### Phase 3: Extract HTML formatting → `email_report_html.py`

- Move to `email_report_html.py`:
  - All `_format_html_*_section` functions at `email_report.py:224-403`.
  - `_SECTION_HTML_FORMATTERS` tuple at `email_report.py:406-416`.
  - `_html_cost_row` helper at `email_report.py:215-221` (HTML-only, parallel to `_cost_line` in Phase 2).
  - `_HTML_DOCUMENT_HEAD` and `_HTML_DOCUMENT_TAIL` constants at `email_report.py:419-441`.
  - `format_html_report` at `email_report.py:444-472`.
- New module gets a one-line module docstring.
- Imports needed in `email_report_html.py`: see the per-module imports table above.
- `email_report.py` re-exports `format_html_report` using the alias form (Design Decision 8).
- **Test changes required** in this phase:
  - `tests/test_email_report.py:285` does `email_report._SECTION_HTML_FORMATTERS`. Update to `from github_usage import email_report_html; html_formatters = email_report_html._SECTION_HTML_FORMATTERS`.
  - **Also remove the now-unused** `from github_usage import email_report` line (line 282) — no attributes of `email_report` are referenced in this test method anymore. (If left in, ruff will flag F401 in a follow-up; tests' per-file-ignores do not cover F401.)

The structural-parity assertion (`test_section_html_formatters_order_matches_text_formatters`) is updated incrementally across Phases 2 and 3, never broken between them: at the end of Phase 3 both formatters come from the new sub-modules.

### Phase 4: Extract Resend delivery → `email_report_send.py`

- Move to `email_report_send.py`:
  - `send_email` at `email_report.py:475-511`. Keep the function-level `from . import http_retry` (line 486) verbatim — do not hoist (Design Decision 1).
  - `default_subject` at `email_report.py:12-15` (delivery-related: produces the subject line passed to `send_email`). Requires `from datetime import UTC, datetime` at the top of the new module (see per-module imports table; the prior draft of this plan missed this — `default_subject` calls `datetime.now(tz=UTC)`, which would `NameError` without the import).
- New module gets a one-line module docstring.
- Imports needed in `email_report_send.py`: see the per-module imports table above.
- `email_report.py` re-exports both `send_email` and `default_subject` using the alias form (Design Decision 8). The two re-exports can share one `from` line:
  ```python
  from .email_report_send import default_subject as default_subject, send_email as send_email
  ```
- **Test changes** are minimal. All callers do `from github_usage.email_report import send_email` / `default_subject` (verified at `test_email_report.py:26, 81, 100, 293, 325`) and the alias-form re-exports keep these working. The one known `mock.patch` is `tests/test_export_cli.py:360` (`github_usage.cli.email_report.send_email`); the dotted path resolves through the re-export, so it continues to work without changes.

### Phase 5: Final verification

- Run `scripts/check`, `scripts/smoke`, `scripts/docs-check`, and **`pre-commit run --all-files`** (added because `scripts/check` and `scripts/docs-check` do not run ruff; F401 and D100 problems would otherwise surface only on the next commit, where `ruff --fix` would silently mutate files).
- Run the full test suite. Confirm `scripts/check-sizes` shows no warnings on any of the new modules or the facade.
- Update `CHANGELOG.md` under `[Unreleased] > Changed` with a brief entry pointing at this plan.
- Move completed plan to `archived/`, set status banner to `> **Status:** COMPLETE` (canonical form per AGENTS.md).

> **Important for Phase 1 implementation:** Update test imports and mock targets *immediately* when extracting each sub-module, not at the end, or tests will be broken between sub-phases. Each sub-extraction commit must update the corresponding test references in the same commit. The structural-parity test (`test_email_report.py:281`) is updated incrementally — Phase 2 updates the text-formatter side, Phase 3 updates the HTML-formatter side and removes the now-unused `import email_report`; the test passes at every commit.

## Out of Scope

- Behavioral changes to email formatting (text or HTML).
- New sections, new senders, new delivery transports.
- Renaming any of the extracted functions or changing their signatures.
- Extracting `tests/test_email_report.py` (currently 349 lines; if it grows during this work, that's a separate concern).
- Adding `__all__` to the facade. The project does not use `__all__` (only `legacy.py` does, and that's a compatibility shim). The `name as name` re-export pattern keeps the public surface unchanged and survives `ruff --fix` without needing `__all__`.
- Changing `scripts/check` to run ruff. That's a separate tooling change.

## Cross-Module Dependencies (After Refactor)

- `_email_report_common.py` (base, no internal deps)
- `email_report_text.py` → `_email_report_common.py`, `report_helpers.fmt_price`
- `email_report_html.py` → `_email_report_common.py`, `report_helpers.fmt_price`
- `email_report_send.py` → `http_retry` (function-level only)
- `email_report.py` (facade) → `email_report_text.py`, `email_report_html.py`, `email_report_send.py` (re-export only; no logic)

No circular cycles. The facade is the apex; the common module is the base.
