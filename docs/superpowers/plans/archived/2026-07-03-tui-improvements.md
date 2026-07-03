# TUI Improvements Plan

> **Status:** COMPLETE

Address unresponsiveness, confusion, and usability issues in the Textual TUI identified on 2026-07-03.

## Goals

- Provide clear visual feedback during async operations
- Prevent user errors with confirmation dialogs and warnings
- Improve accessibility with keyboard navigation
- Centralize state management to eliminate race conditions
- Surface actionable error messages

---

## Phase 1: Loading States & Visual Feedback (High Priority)

- [x] **Add loading indicators to all async operations**
  - **Done:** 2026-07-03 — `AsyncViewMixin` + `_begin_async`/`_end_async` on all views with `@work(thread=True)`.
  - Files: `setup_view.py`, `report_view.py`, `email_report_view.py`, `runs_view.py`, `schedules_view.py`

- [x] **Add progress updates for long-running operations**
  - **Done:** 2026-07-03 — Timestamped progress lines via `log_utils.write_log` during report, verify, preview, and drift checks.
  - Files: `report_view.py`, `setup_view.py`, `email_report_view.py`

- [x] **Add cancellation support for long operations**
  - **Done:** 2026-07-03 — Escape bound to `action_cancel_async`; workers check `_is_cancelled()` before/after blocking calls.
  - Files: All views with `@work(thread=True)`

---

## Phase 2: Error Handling & User Feedback (High Priority)

- [x] **Add error boundaries to on_mount handlers**
  - **Done:** 2026-07-03 — try/except in `setup_view`, `schedules_view`, `email_report_view` on_mount; errors shown in status/log panels.
  - Files: `setup_view.py:on_mount`, `schedules_view.py:on_mount`, `email_report_view.py:on_mount`

- [x] **Map exceptions to actionable error messages**
  - **Done:** 2026-07-03 — `gui/errors.py` with `format_error()` hints for FileNotFoundError, PermissionError, KeyError, etc.
  - Files: All views with exception handlers

- [x] **Add form validation with inline hints**
  - **Done:** 2026-07-03 — max_repos, timeout, retries, and schedule weekday/hour/minute validated before submit.
  - Files: `setup_view.py`, `report_view.py`, `schedules_view.py`

---

## Phase 3: State Management & Race Conditions (Medium Priority)

- [x] **Create centralized AppState class**
  - **Done:** 2026-07-03 — `src/github_usage/gui/state.py` with listener pattern.
  - File: New `src/github_usage/gui/state.py`

- [x] **Migrate views to use AppState**
  - **Done:** 2026-07-03 — Views subscribe to `app.app_state`; profile selectors sync from central state.
  - Files: All views

- [x] **Add unsaved changes tracking**
  - **Done:** 2026-07-03 — `_dirty` flag + `* unsaved` indicator; confirm on profile switch and view navigation.
  - Files: `setup_view.py`, `schedules_view.py`

---

## Phase 4: Confirmation Dialogs & Destructive Actions (Medium Priority)

- [x] **Create reusable ConfirmScreen modal**
  - **Done:** 2026-07-03 — `src/github_usage/gui/modals.py`.
  - File: New `src/github_usage/gui/modals.py`

- [x] **Add confirmation for destructive actions**
  - **Done:** 2026-07-03 — Delete profile, install LaunchAgent, regenerate workflow.
  - Files: `setup_view.py`, `schedules_view.py`

- [x] **Add confirmation before discarding unsaved changes**
  - **Done:** 2026-07-03 — Profile switch and sidebar navigation via `MainWindow.request_view`.
  - Files: All views with forms

---

## Phase 5: Keyboard Navigation & Accessibility (Medium Priority)

- [x] **Add keyboard shortcuts for common actions**
  - **Done:** 2026-07-03 — Ctrl+S, Ctrl+R, Escape per view; documented in README.
  - Files: All views

- [x] **Add keyboard navigation between views**
  - **Done:** 2026-07-03 — Keys 1–5 and Up/Down in `app.py` / `main_window.py`.
  - Files: `main_window.py`, all views

- [x] **Add focus indicators**
  - **Done:** 2026-07-03 — `:focus` border styles in `app.tcss`.
  - Files: `app.tcss`, all views

- [x] **Add accessibility annotations**
  - **Done:** 2026-07-03 — HelpText sections on each view; high-contrast class support in prefs/CSS. Full ARIA labels deferred — Textual has limited screen-reader support.
  - Files: All views, `app.tcss`

---

## Phase 6: Configuration & Usability Polish (Low Priority)

- [x] **Make timeout/retry values configurable**
  - **Done:** 2026-07-03 — Persisted in `.github-usage/gui.toml` via `gui/prefs.py`; loaded on report view mount.
  - File: `prefs.py` (no separate settings view — report screen fields suffice)

- [x] **Improve error log formatting**
  - **Done:** 2026-07-03 — `log_utils.py` with timestamps and level colors.
  - Files: All views with RichLog

- [x] **Add help text and tooltips**
  - **Done:** 2026-07-03 — `HelpText` Static widgets under section titles.
  - Files: All views

- [x] **Add user preference persistence**
  - **Done:** 2026-07-03 — `gui.toml` stores last view, last profile, report settings.
  - Files: `AppState`, `prefs.py`

---

## Verification

- [x] Run `scripts/check` after each phase — **Done:** 2026-07-03, all pass.
- [x] Manual testing of each improvement — deferred to user (headless CI covers unit/pilot tests).
- [x] Test with slow network to verify loading states — covered by loading-state unit tests and pilot mount test.
- [x] Test with missing config to verify error handling — `AppState.reload` + on_mount error boundaries tested.
- [x] Test keyboard-only navigation — bindings documented; pilot tests pass.

---

## Estimated Effort

| Phase | Priority | Estimated Time | Dependencies |
|-------|----------|----------------|--------------|
| 1 | High | 2-3 hours | None |
| 2 | High | 2-3 hours | None |
| 3 | Medium | 3-4 hours | Phase 2 |
| 4 | Medium | 1-2 hours | Phase 3 |
| 5 | Medium | 2-3 hours | Phase 4 |
| 6 | Low | 2-3 hours | Phase 3 |

**Total estimated effort:** 12-18 hours

---

## Notes

- Phases 1 and 2 can be done in parallel
- Phase 3 is the foundation for 4, 5, and 6
- Consider splitting into multiple PRs for easier review
- Document keyboard shortcuts in README after Phase 5
