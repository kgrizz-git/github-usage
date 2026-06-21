# Plan: Add Schedule Configuration as a Dedicated Menu Option

**Date:** 2026-06-21

## Objective

Allow users to easily modify their reporting schedule directly from the `setup.sh` main menu, without having to run through the entire "Recommended full setup" wizard or waiting until launchd prompts for it.

## Proposed Changes

### 1. Update `src/github_usage/setup_wizard.py`

- [ ] Add a new function `_schedule_only(paths: SetupPaths) -> int` that:
  - Calls the existing `_configure_schedule(paths)`.
  - Calls `generate_plist(paths)` from `setup_launchd` so the plist in `.github-usage/launchd/` stays in sync with `config.toml`. (Without this, an already-installed LaunchAgent keeps the old `StartCalendarInterval` silently.)
  - Prints a reminder: "If the LaunchAgent is already installed, run option 5 to reinstall it for the new schedule to take effect."
  - Returns `0`.
  - Define this function before `_MENU_OPTIONS`, alongside the other 5 handler functions (`_secrets_only`, `_options_only`, `_hooks_only`, `_ci_only`, `_status_only`).
- [ ] Insert the new schedule option at position 4 in `_MENU_OPTIONS`, right after "Report options only":
  - **Key**: `"4"`
  - **Label**: `"Report schedule only"`
  - **Description**: `"Configure the day of the week and time for your local reporting schedule and regenerate the LaunchAgent plist. Stored in .github-usage/config.toml. The GitHub Actions workflow has its own cron and ignores this value."`
  - **Handler**: `_schedule_only`
- [ ] Shift subsequent numbering: "macOS launchd schedule" → `5`, "GitHub Actions secrets" → `6`, "Developer security hooks" → `7`, "Verify configuration" → `8`, "Show status" → `9`. Menu now has 9 options.
- [ ] Confirm `_interactive_menu`'s default prompt (`or "1"`) still works — the new option is not the default.

### 2. Add New Test (`tests/test_setup_wizard.py`)

- [ ] Inside the existing `SetupWizardCliTests` class, add a test that choosing option 4 calls both `_configure_schedule` and `generate_plist`:
  ```python
  @mock.patch("sys.stdin.isatty", return_value=True)
  def test_schedule_menu_option_calls_configure_schedule(self, mock_isatty):
      with mock.patch("builtins.input", return_value="4"):
          with mock.patch(
              "github_usage.setup_wizard._configure_schedule"
          ) as mock_schedule, mock.patch(
              "github_usage.setup_wizard.generate_plist"
          ) as mock_plist:
              code = run_setup(["--root", str(self.paths.root)])
              self.assertEqual(code, 0)
              mock_schedule.assert_called_once()
              mock_plist.assert_called_once()
  ```
- [ ] `sys.stdin.isatty` is mocked to return `True` so the interactive code path runs without a real TTY.

### 3. Update Documentation

- [ ] Add an entry to the `[Unreleased]` `### Added` section in `CHANGELOG.md`:
  `- **Schedule-only menu option:** Configure the report schedule (weekday, hour, minute) from the setup menu without running the full wizard; regenerates the LaunchAgent plist and reminds the user to reinstall it.`
- [ ] Confirm `README.md` does not list the setup menu options (it does not — no changes needed). If any documentation does get modified, run `scripts/docs-check`.

### 4. Verification

- [ ] Run `scripts/check` (tests + lint + format).
- [ ] Run `scripts/docs-check`.
- [ ] Run `./setup.sh` manually to visually confirm the new menu option appears, the plist is regenerated, and the reinstall reminder is printed.

## Out of Scope (potential follow-ups)

- A non-interactive counterpart such as `./setup.sh --set-schedule "weekday=1 hour=9 minute=0"` for scripted changes. Worth a separate plan.
