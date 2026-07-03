> **Status:** COMPLETE

# Fix GUI Backend Profile Export and CLI GUI Error Handling

## Overview
Launching `./start.sh` without arguments when `textual` is installed failed with "Error: TUI dependencies are not installed." This occurred because `schedules_view.py` and `setup_view.py` try to import `DEFAULT_PROFILE_NAME` from `gui_backend.py`, but `gui_backend.py` did not export it. In addition, `cli_gui.py` caught all `ImportError` exceptions when importing `GitHubUsageApp`, masking internal import errors as missing dependencies.

## Phases

### Phase 1: Export `DEFAULT_PROFILE_NAME` in `gui_backend.py`
**Done:** 2026-07-03 - Exported `DEFAULT_PROFILE_NAME` from `.setup_workflow` in `gui_backend.py` and verified GUI app import succeeds.
- [x] In `src/github_usage/gui_backend.py`, add `DEFAULT_PROFILE_NAME` to the imported and re-exported symbols from `.setup_workflow`.
- [x] Verify that `import github_usage.gui.app` succeeds without raising an ImportError.

### Phase 2: Improve CLI GUI Error Handling and Helper Instructions
**Done:** 2026-07-03 - Updated `_MISSING_GUI_MESSAGE` to use `--python .venv` and added `find_spec("textual")` check in `run_tui()`.
- [x] In `src/github_usage/cli_gui.py`, update `_MISSING_GUI_MESSAGE` to recommend `uv pip install --python .venv -e '.[gui]'`.
- [x] In `src/github_usage/cli_gui.py`, check whether `textual` is installed using `importlib.util.find_spec` before importing `GitHubUsageApp`, so internal import errors raise their actual tracebacks instead of printing `_MISSING_GUI_MESSAGE`.

### Phase 3: Tests and Verification
**Done:** 2026-07-03 - Updated `SetupViewPilotTests` to `IsolatedAsyncioTestCase`, added unit tests for `DEFAULT_PROFILE_NAME` export and `--python .venv` message, verified all checks pass, updated CHANGELOG.md, and archived plan.
- [x] In `tests/test_gui_models.py`, update `SetupViewPilotTests` to inherit from `unittest.IsolatedAsyncioTestCase` so async test methods are actually awaited.
- [x] In `tests/test_gui_models.py`, add a test verifying that `DEFAULT_PROFILE_NAME` can be imported from `gui_backend` and checking that `_MISSING_GUI_MESSAGE` contains `--python .venv`.
- [x] Run `scripts/check` and `scripts/docs-check`.
- [x] Update `CHANGELOG.md` under `[Unreleased]`.
- [x] Archive this plan once complete.
