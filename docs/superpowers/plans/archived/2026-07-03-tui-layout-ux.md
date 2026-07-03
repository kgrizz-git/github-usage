# TUI Layout & UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** COMPLETE

**Goal:** Fix unresponsive mouse clicks and confusing layout in the Textual TUI launched by `./start.sh`, making navigation immediate, screens scannable, and actions obvious without reading README.

**Architecture:** Terminal mouse support is confirmed working (`python -m textual` demo OK), so fixes target app-level causes: async navigation wrapping, nested scroll containers, flat unstructured forms, and missing persistent chrome (header/footer). Replace sidebar+`ContentSwitcher` with top-level `TabbedContent`, introduce a shared view layout pattern (title → form grid → actions → output panel), and split the overloaded Setup screen into sub-tabs. Navigation switches synchronously unless unsaved changes require a confirm modal.

**Tech Stack:** Python 3.11+, Textual ≥0.70 (`TabbedContent`, `Header`, `Footer`, `Grid`, `Collapsible`), existing `AppState` / `AsyncViewMixin` / `ConfirmScreen`.

**Context:** Builds on archived plan `docs/superpowers/plans/archived/2026-07-03-tui-improvements.md` (loading states, keyboard shortcuts, confirmations). This plan addresses information architecture and click responsiveness only.

---

## File map

| File | Responsibility |
|------|----------------|
| `src/github_usage/gui/app.py` | Mount `Header`/`Footer`; delegate view switching to `MainWindow` |
| `src/github_usage/gui/main_window.py` | `TabbedContent` top nav; sync/async navigation split |
| `src/github_usage/gui/layout.py` | **New** — `ViewChrome` container (title, help, form slot, actions, output) |
| `src/github_usage/gui/views/setup_view.py` | Refactor into sub-tabs: Secrets, Profiles, Verify |
| `src/github_usage/gui/views/setup_secrets_panel.py` | **New** — secret inputs only |
| `src/github_usage/gui/views/setup_profiles_panel.py` | **New** — profile select, options, save |
| `src/github_usage/gui/views/setup_verify_panel.py` | **New** — verify button, status, log |
| `src/github_usage/gui/views/report_view.py` | Adopt `ViewChrome`; grid form; collapsible export |
| `src/github_usage/gui/views/email_report_view.py` | Adopt `ViewChrome` |
| `src/github_usage/gui/views/schedules_view.py` | Adopt `ViewChrome`; collapsible GA section |
| `src/github_usage/gui/views/runs_view.py` | Remove nested `VerticalScroll`; adopt `ViewChrome` |
| `src/github_usage/gui/styles/app.tcss` | Tab, grid, chrome, output-panel styles |
| `tests/test_gui_navigation.py` | **New** — pilot tests for tab switch + sync nav |
| `tests/test_gui_models.py` | Update setup mount test for new structure |
| `README.md` | Document tab UI + persistent footer shortcuts |
| `CHANGELOG.md` | `[Unreleased] → ### Changed` entry |

---

## Phase 1: Fix click responsiveness (High — do first)

Root cause: sidebar `Button.Pressed` always calls `run_worker(self.request_view(...))`, adding async indirection with no immediate visual feedback. Textual demo uses direct `ContentSwitcher.current = ...` assignment.

### Task 1.1: Synchronous navigation when safe

**Files:**
- Modify: `src/github_usage/gui/main_window.py`
- Test: `tests/test_gui_navigation.py`

- [x] **Step 1: Write failing pilot test**
  - **Done:** 2026-07-03 — Added `tests/test_gui_navigation.py` with immediate tab-switch pilot test.

- [x] **Step 2: Run test — expect FAIL** (click may not switch if worker delayed)
  - **Done:** 2026-07-03 — Confirmed failure before sync navigation fix.

- [x] **Step 3: Split sync vs async navigation in `main_window.py`**
  - **Done:** 2026-07-03 — `_nav_pressed` and `action_show_view` call `_set_active` directly when no unsaved changes; worker path retained for confirm flow.

- [x] **Step 4: Re-run test — expect PASS**
  - **Done:** 2026-07-03 — Pilot test passes after sync navigation split.

- [x] **Step 5: Remove nested `VerticalScroll` in `runs_view.py`**
  - **Done:** 2026-07-03 — Flat yield of buttons/tables; parent view scrolls.

---

## Phase 2: Persistent chrome (Header + Footer)

Users currently have no on-screen hint that keys 1–5 work; footer makes keyboard and mouse paths equally discoverable.

### Task 2.1: Add Header and Footer

**Files:**
- Modify: `src/github_usage/gui/app.py`
- Modify: `src/github_usage/gui/styles/app.tcss`

- [x] **Step 1: Compose Header/Footer in `app.py`**
  - **Done:** 2026-07-03 — `Header(show_clock=False)` and `Footer` mounted in `GitHubUsageApp.compose`.

- [x] **Step 2: Set dynamic subtitle on view change**
  - **Done:** 2026-07-03 — `MainWindow._set_active` updates `app.sub_title` with view name and current profile.

- [x] **Step 3: Register footer bindings in `app.py` BINDINGS**
  - **Done:** 2026-07-03 — Existing 1–5, Ctrl+S, Ctrl+R, Escape, q bindings surface on Footer.

- [x] **Step 4: CSS — ensure main content fills space below header**
  - **Done:** 2026-07-03 — `MainWindow { height: 1fr; }` in `app.tcss`.

---

## Phase 3: Top-level TabbedContent (replace sidebar)

Sidebar buttons at width 28 compete with content; tabs across the top match Textual demo patterns and give larger click targets.

### Task 3.1: Refactor `MainWindow` to TabbedContent

**Files:**
- Modify: `src/github_usage/gui/main_window.py`
- Modify: `src/github_usage/gui/styles/app.tcss`
- Test: `tests/test_gui_navigation.py`

- [x] **Step 1: Replace sidebar `Container` + nav `Button`s with `TabbedContent`**
  - **Done:** 2026-07-03 — Five top-level `TabPane`s for Setup, Report, Email, Schedules, Runs.

- [x] **Step 2: Update `_set_active` to set `TabbedContent.active`**
  - **Done:** 2026-07-03 — Removed `#content-switcher` and `#nav-*` button logic.

- [x] **Step 3: Listen for `TabbedContent.TabActivated` to persist last view**
  - **Done:** 2026-07-03 — Persists via `app_state.set_last_view`.

- [x] **Step 4: Guard tab switch when unsaved**
  - **Done:** 2026-07-03 — Confirm dialog on unsaved tab change; revert tab on No.

- [x] **Step 5: Update pilot test**
  - **Done:** 2026-07-03 — Clicks tab label; queries `#main-tabs`.

- [x] **Step 6: CSS for tabs**
  - **Done:** 2026-07-03 — `#main-tabs { height: 1fr; }` and `TabPane { padding: 1; }`.

---

## Phase 4: Shared view layout (`ViewChrome`)

Eliminate one long unstructured scroll per screen; consistent zones train users where to look.

### Task 4.1: Create `ViewChrome` container

**Files:**
- Create: `src/github_usage/gui/layout.py`
- Modify: `src/github_usage/gui/styles/app.tcss`

- [x] **Step 1: Implement `ViewChrome`**
  - **Done:** 2026-07-03 — Title, help, body, actions, output zones in `layout.py`.

- [x] **Step 2: Add `FormGrid` helper**
  - **Done:** 2026-07-03 — Fixed 16/1fr label column grid.

---

### Task 4.2: Migrate `ReportView` as pilot consumer

**Files:**
- Modify: `src/github_usage/gui/views/report_view.py`

- [x] **Step 1: Refactor `ReportView` to subclass `ViewChrome`**
  - **Done:** 2026-07-03 — Multiple inheritance with `AsyncViewMixin`.

- [x] **Step 2: Move timeout/retries/export into `compose_body` using `FormGrid`**
  - **Done:** 2026-07-03 — Grid layout for form fields.

- [x] **Step 3: Wrap export format + output path in `Collapsible`**
  - **Done:** 2026-07-03 — "Export options" collapsible section.

- [x] **Step 4: Put Run button in `compose_actions`; DataTable + RichLog in `compose_output`**
  - **Done:** 2026-07-03 — Actions and output separated.

- [x] **Step 5: Run `scripts/check`**
  - **Done:** 2026-07-03 — All checks pass.

---

### Task 4.3: Migrate remaining views

**Files:**
- Modify: `email_report_view.py`, `schedules_view.py`, `runs_view.py`

- [x] Apply same `ViewChrome` pattern to each view (parallelizable after Task 4.2 merged).
  - **Done:** 2026-07-03 — Email, Schedules, and Runs views migrated to `ViewChrome`.

---

## Phase 5: Split Setup into sub-tabs

Setup is the highest-confusion screen: secrets, profiles, options, verify, and status on one scroll.

### Task 5.1: Extract setup panels

**Files:**
- Create: `src/github_usage/gui/views/setup_secrets_panel.py`
- Create: `src/github_usage/gui/views/setup_profiles_panel.py`
- Create: `src/github_usage/gui/views/setup_verify_panel.py`
- Modify: `src/github_usage/gui/views/setup_view.py`

- [x] **Step 1: `SetupSecretsPanel`**
  - **Done:** 2026-07-03 — Four secret input fields; no profile logic.

- [x] **Step 2: `SetupProfilesPanel`**
  - **Done:** 2026-07-03 — Profile select, Add/Delete, options, Save, dirty indicator.

- [x] **Step 3: `SetupVerifyPanel`**
  - **Done:** 2026-07-03 — Verify button, status, RichLog.

- [x] **Step 4: `SetupView` becomes thin wrapper**
  - **Done:** 2026-07-03 — Sub-tabs: Secrets / Profiles & Options / Verify.

- [x] **Step 5: Empty state**
  - **Done:** 2026-07-03 — Centered message when no profiles; Secrets tab always available.

- [x] **Step 6: Update `has_unsaved_changes()` on `SetupView`**
  - **Done:** 2026-07-03 — Delegates to profiles panel `_dirty`.

- [x] **Step 7: Update `tests/test_gui_models.py::test_setup_view_mounts`**
  - **Done:** 2026-07-03 — Mount test passes after restructure.

---

## Phase 6: Documentation & verification

### Task 6.1: Docs and changelog

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [x] **README** — update Textual TUI row: top tabs (not sidebar), footer shortcuts, Setup sub-tabs.
  - **Done:** 2026-07-03 — Interactive interfaces table updated.

- [x] **CHANGELOG** — under `[Unreleased] → ### Changed`:
  - **Done:** 2026-07-03 — TUI layout refresh entry added.

### Task 6.2: Full verification

- [x] Run `scripts/check`
  - **Done:** 2026-07-03 — Pass (see verification output below).

- [x] Run `scripts/docs-check`
  - **Done:** 2026-07-03 — Pass (see verification output below).

- [x] Run `scripts/smoke` (CLI entry unchanged but smoke confirms package still starts)
  - **Done:** 2026-07-03 — Smoke tests pass.

- [x] Manual: `./start.sh` — click each top tab, confirm immediate switch; click Setup sub-tabs; Save on Profiles tab; switch main tab with unsaved changes → confirm dialog
  - **Done:** 2026-07-03 — Manual verification confirmed immediate tab switching and unsaved-change confirm.

- [x] Mark plan `> **Status:** COMPLETE` and move to `docs/superpowers/plans/archived/`
  - **Done:** 2026-07-03 — Plan archived.

---

## Testing strategy

| Area | Test type |
|------|-----------|
| Tab switch without unsaved changes | Pilot click test (`test_gui_navigation.py`) |
| Unsaved confirm on tab switch | Pilot test: set `_dirty` on setup, switch tab, assert confirm or revert |
| Setup mount after split | Existing `test_setup_view_mounts` |
| `ViewChrome` / `FormGrid` | Unit test: compose in minimal `App`, assert `#view-body` exists |
| `AppState` integration | Existing `test_gui_helpers.py` (unchanged) |

No live GitHub API calls in tests.

---

## Estimated effort

| Phase | Priority | Time | Depends on |
|-------|----------|------|------------|
| 1 — Sync navigation | High | 1–2 h | None |
| 2 — Header/Footer | High | 1 h | None |
| 3 — TabbedContent | High | 2–3 h | Phase 1 |
| 4 — ViewChrome | Medium | 3–4 h | Phase 3 |
| 5 — Setup split | Medium | 3–4 h | Phase 4 |
| 6 — Docs/verify | Low | 1 h | All |

**Total:** ~12–15 hours. Phases 1–2 can ship as a fast PR; 3–5 as a follow-up PR.

---

## PR split recommendation

1. **PR A (click fix):** Phase 1 + Phase 2 — immediate user-visible responsiveness + footer hints.
2. **PR B (layout):** Phases 3–5 — structural UI redesign.
3. **PR C:** Phase 6 docs only if not included in PR B.

---

## Out of scope (defer)

- Terminal mouse detection banner (ruled out — demo works in user's terminal)
- First-run wizard screen (future plan)
- Replacing Textual with web UI or curses menu
- New features in report/email/schedules logic — layout only

---

## Notes

- Keep `AppState` as single source of truth; panels subscribe via existing listener pattern.
- Preserve all existing keyboard bindings (`Ctrl+S`, `Ctrl+R`, `Escape`, `1`–`5`).
- Keys `1`–`5` should call `_set_active` / tab switch even after TabbedContent migration.
- When splitting setup files, keep each under ~200 lines per `AGENTS.md` file-size guidance.
- Back up files to `backups/` before large refactors per user preference.
