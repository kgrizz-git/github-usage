# TUI Guided Setup and Friendly Schedules

> **Status:** COMPLETE

Add an in-TUI step-by-step setup wizard and replace raw cron/weekday-number inputs with friendly schedule pickers.

## Goals

- Guided first-run and on-demand setup in the Textual TUI
- Human-friendly schedule controls (no cron literacy required)
- Shared schedule logic for CLI and TUI

---

## Phase 1: Shared schedule helpers

- [x] **Add `schedule_helpers.py`**
  - **Done:** 2026-07-03 — `build_weekly_cron_utc`, `parse_weekly_cron_to_local`, `describe_cron_human`, `WEEKDAY_CHOICES`, tests in `tests/test_schedule_helpers.py`; `cli_runs` re-exports `describe_cron_human`.

---

## Phase 2: SchedulePicker widget

- [x] **Build `SchedulePicker`**
  - **Done:** 2026-07-03 — `gui/widgets/schedule_picker.py` with local/GA sections, previews, advanced cron override.

- [x] **Integrate into Schedules tab**
  - **Done:** 2026-07-03 — `schedules_view.py` uses `SchedulePicker` for load/save.

---

## Phase 3: Guided setup wizard

- [x] **Implement `SetupWizardScreen`**
  - **Done:** 2026-07-03 — `gui/wizard/` with 8 steps, `gui_backend` persistence, verify worker.

- [x] **Entry points**
  - **Done:** 2026-07-03 — Setup tab button, first-run prompt in `app.py`, `wizard_completed` / `dismissed_setup_wizard` in `gui.toml`.

---

## Phase 4: Docs and verification

- [x] **CHANGELOG, README, tests, `scripts/check`**
  - **Done:** 2026-07-03 — `tests/test_schedule_picker.py`, wizard integration test, docs updated.
