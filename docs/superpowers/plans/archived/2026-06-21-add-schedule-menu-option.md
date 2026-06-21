# Plan: Add Schedule Configuration as a Dedicated Menu Option

**Date:** 2026-06-21

**Done:** 2026-06-21 — Added `_schedule_only` handler (option 4) and `_REINSTALL_REMINDER` constant in `src/github_usage/setup_wizard.py`, renumbered the rest of `_MENU_OPTIONS` (5–9), wired `generate_plist` into `_full_setup` after `_configure_schedule`, added 9 new tests in `tests/test_setup_wizard.py`, and updated `CHANGELOG.md` + a named mention in `README.md`. `scripts/check`, `scripts/smoke`, and `scripts/docs-check` all pass (232 tests total).

## Objective

Allow users to easily modify their reporting schedule directly from the `setup.sh` main menu, without having to run through the entire "Recommended full setup" wizard or waiting until launchd prompts for it.

## Proposed Changes

### 1. Update `src/github_usage/setup_wizard.py`

- [x] Add a module-level constant (near the other menu handlers, before `_MENU_OPTIONS`):

  ```python
  _REINSTALL_REMINDER = (
      "LaunchAgent is installed. Run option 5 (macOS launchd schedule) "
      "and choose install to apply the new schedule."
  )
  ```

- [x] Add a new function `_schedule_only(paths: SetupPaths) -> int` (place it after `_options_only`, before `_hooks_only`, to mirror menu order) that:
  - Calls the existing `_configure_schedule(paths)` (platform-agnostic; updates `config.toml`).
  - Calls `generate_plist(paths)` from `setup_launchd` so the plist in `.github-usage/launchd/` stays in sync with `config.toml`. (Without this, an already-installed LaunchAgent keeps the old `StartCalendarInterval` silently.) `generate_plist` is safe on non-macOS — it only writes the plist file under `.github-usage/launchd/`.
  - Prints `Generated {plist.relative_to(paths.root)}` (same confirmation as `_configure_launchd`'s generate action).
  - Prints `_REINSTALL_REMINDER` **only when both** `sys.platform == "darwin"` **and** `launch_agent_status() == "installed"`.
  - Returns `0`.
- [x] Insert the new schedule option at position 4 in `_MENU_OPTIONS`, right after "Report options only":
  - **Key**: `"4"`
  - **Label**: `"Report schedule only"`
  - **Description**: `"Configure the day of the week and time for your local reporting schedule and regenerate the LaunchAgent plist. Stored in .github-usage/config.toml. The GitHub Actions workflow has its own cron and ignores this value."`
  - **Handler**: `_schedule_only`
- [x] Shift subsequent numbering: "macOS launchd schedule" → `5`, "GitHub Actions secrets" → `6`, "Developer security hooks" → `7`, "Verify configuration" → `8`, "Show status" → `9`. Menu now has 9 options.
- [x] In `_full_setup`, call `generate_plist(paths)` immediately after `_configure_schedule(paths)` and **before** `_verify_setup` so the on-disk plist under `.github-usage/launchd/` stays in sync when the user skips LaunchAgent install. **Intentional:** plist regeneration still runs when verify fails — schedule already changed in `config.toml` and the plist should reflect it regardless of dry-run success.
- [x] Confirm `_interactive_menu`'s default prompt (`or "1"`) still works — the new option is not the default (covered by test below).

### 2. Add Tests (`tests/test_setup_wizard.py`)

Import `_MENU_OPTIONS`, `_REINSTALL_REMINDER`, `_schedule_only`, and `_full_setup` from `github_usage.setup_wizard` as needed.

- [x] **`test_menu_options_numbering_and_labels`** — Assert `_MENU_OPTIONS` has 9 entries with expected `(key, label)` pairs at positions 1–9 (option 4 = "Report schedule only"; shifted originals at 5–9; option 1 still = "Recommended full setup").
- [x] **`test_default_menu_option_is_full_setup`** — Mock `builtins.input` to return `""` (empty → default `"1"`), mock `_full_setup`, call `run_setup(["--root", str(self.paths.root)])`; assert exit code `0` and `_full_setup` called once.
- [x] **`test_schedule_only_regenerates_plist_and_prints_reminder_when_installed`** — Direct unit test of `_schedule_only(self.paths)`:
  - Mock `_configure_schedule`.
  - Mock `launch_agent_status` to return `"installed"`.
  - Patch `sys.platform` to `"darwin"`.
  - Capture stdout; assert `"Generated"` and `_REINSTALL_REMINDER` appear exactly.
  - Assert `generate_plist` was called once with `self.paths`.
  - Assert return value is `0`.
- [x] **`test_schedule_only_skips_reminder_when_not_installed`** — Same as above but `launch_agent_status` returns `"not installed"`; assert `_REINSTALL_REMINDER` is absent; assert return value is `0`.
- [x] **`test_schedule_only_skips_reminder_on_non_macos`** — Patch `sys.platform` to `"linux"`; mock `launch_agent_status`; assert `_REINSTALL_REMINDER` is absent; assert `generate_plist` was called once with `self.paths` (plist sync is not macOS-gated).
- [x] **`test_schedule_menu_option_dispatches_option_4`** — Integration-style test via `run_setup` with `input("4")`, mocking `_schedule_only`; assert exit code `0` and `_schedule_only` invoked once.
- [x] **`test_full_setup_regenerates_plist_after_schedule`** — Call `_full_setup(self.paths)` with mocks for `_configure_env_secrets`, `_configure_email_options`, `_verify_setup` (return `0`), `_prompt_yes_no` (return `False` to skip launchd/CI/hooks), and spies on `_configure_schedule` + `generate_plist`. Assert both are called and `generate_plist` runs after `_configure_schedule`.
- [x] **`test_full_setup_regenerates_plist_even_when_verify_fails`** — Same mocks as above but `_verify_setup` returns non-zero; assert `generate_plist` **is still called** (runs before verify, not gated on verify success).
- [x] **`test_launchd_menu_option_still_dispatches_at_key_5`** — Optional sanity check: `run_setup` with `input("5")` and mock `_configure_launchd`; assert it is invoked (confirms numbering shift did not break launchd dispatch).

### 3. Update Documentation

- [x] Add entries to the `[Unreleased]` `### Added` section in `CHANGELOG.md`:
  `- **Schedule-only menu option:** Configure the report schedule (weekday, hour, minute) from the setup menu without running the full wizard; regenerates the LaunchAgent plist and reminds the user to reinstall it when a LaunchAgent is already installed.`
  `- **Full-setup plist sync:** Recommended full setup now regenerates the LaunchAgent plist after schedule prompts, even when launchd install is skipped.`
- [x] Confirm `README.md` does not list numbered setup menu options (it references choices by name only — no changes required unless adding a named mention of **Report schedule only**). If any documentation is modified, run `scripts/docs-check`. Added a named mention in the macOS launchd Setup section.

### 4. Verification

- [x] Run `scripts/check` (tests + lint + format).
- [x] Run `scripts/docs-check`.
- [ ] Run `./setup.sh` manually on macOS to confirm the new menu option appears, the plist is regenerated, and `_REINSTALL_REMINDER` prints only when a LaunchAgent is installed. (Test suite covers the logic; manual macOS verification deferred to the user.)

## Out of Scope (potential follow-ups)

- A non-interactive counterpart such as `./setup.sh --set-schedule "weekday=1 hour=9 minute=0"` for scripted changes. Worth a separate plan.
- **`generate_plist` script-path validation (pre-existing):** `generate_plist` writes a plist pointing at `scripts/send-email-report.sh` without checking the file exists. A warning or existence check would be a separate small improvement.

## Assessment Notes (2026-06-21)

Incorporated from `tmp/2026-06-21-141000-add-schedule-menu-assessment.md`:

- Conditional reminder (darwin + installed) and macOS-only reminder text.
- Direct `_schedule_only` tests plus menu layout, full-setup plist sync, and non-macOS reminder tests.
- Reminder references option 5 by name as well as number.
- **Not adopted:** Skipping `generate_plist` on non-macOS — plist generation is harmless off-macOS and keeps `.github-usage/launchd/` aligned with `config.toml`.

Incorporated from `tmp/2026-06-21-141500-add-schedule-menu-assessment.md`:

- **`_REINSTALL_REMINDER` module constant** for implementation and exact test assertions (E2, I2).
- **`test_default_menu_option_is_full_setup`** for empty-input default routing (E1).
- **Non-macOS test asserts `generate_plist` is called**, not just that the reminder is absent (G1).
- **Return value `0` asserted** in direct-handler tests (G2).
- **`generate_plist` missing-script validation** noted in Out of Scope; pre-existing, not blocking (G3).
- **Verify-failure behavior documented and tested:** `_full_setup` regenerates the plist before verify, so `generate_plist` still runs when verify fails — do **not** gate plist sync on verify success (G4 rejected as proposed).
