# Fix CI Failures (basedpyright and GUI SchedulePicker) Implementation Plan

> **Status:** COMPLETE
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the CI failure in `scripts/typecheck` / `.github/workflows/ci.yml` (`basedpyright: not found`) and resolve the 5 GUI integration/scroll test errors caused by DOM timing in `SchedulePicker.on_mount`.

**Architecture:** Make `scripts/typecheck` resilient by checking `.venv/bin/basedpyright`, system PATH, and `scripts/python -m basedpyright` before failing with a helpful error message. Update `.github/workflows/ci.yml` job `check` to install `.[dev,gui]` so `basedpyright` is available when `scripts/check` calls `scripts/typecheck`. In `SchedulePicker`, use Textual's `call_after_refresh` pattern in `on_mount` to defer child widget queries until after the initial DOM paint, and add defensive `NoMatches` exception handling in preview refresh methods.

**Tech Stack:** Python 3.11+, Textual, basedpyright, bash, GitHub Actions CI

## Global Constraints

- Never make file edits the user did not explicitly ask for.
- Active package code lives in `src/github_usage/`.
- Use `scripts/check` as the default verification command before claiming a code change is complete.
- Do not print, commit, or store real GitHub tokens, raw private API responses, or generated billing reports.
- Tests should use fake tokens, mocks, and fixtures rather than live GitHub API calls.

---

### Task 1: Fix `scripts/typecheck` and CI Workflow Dependencies

**Done:** 2026-07-05: Updated scripts/typecheck with 3-tier fallback and ci.yml check job to install dev dependencies.

**Files:**
- Modify: `scripts/typecheck:1-8`
- Modify: `.github/workflows/ci.yml:24-28`

**Interfaces:**
- Consumes: `basedpyright` executable from virtualenv or PATH
- Produces: Reliable static type check execution across local development and CI

- [x] **Step 1: Update `scripts/typecheck` to locate `basedpyright` reliably**

Modify `scripts/typecheck` to check `.venv/bin/basedpyright`, then command PATH, then fallback to `scripts/python -m basedpyright`. If none exist, output a clear installation error.

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -x ".venv/bin/basedpyright" ]; then
  exec .venv/bin/basedpyright src tests
elif command -v basedpyright >/dev/null 2>&1; then
  exec basedpyright src tests
elif scripts/python -m basedpyright --version >/dev/null 2>&1; then
  exec scripts/python -m basedpyright src tests
else
  echo "Missing basedpyright. Install dev tools with: scripts/python -m pip install -e '.[dev]'" >&2
  exit 1
fi
```

- [x] **Step 2: Update `.github/workflows/ci.yml` to install `.[dev,gui]` in `check` job**

In `.github/workflows/ci.yml`, the `check` job runs `scripts/check`, which invokes `scripts/typecheck` at line 30. Therefore, the `check` job must install `.[dev,gui]`.

**Replace** `.github/workflows/ci.yml` line 25, changing `'.[gui]'` to `'.[dev,gui]'`:

```diff
       - name: Install package
-        run: scripts/python -m pip install -e '.[gui]'
+        run: scripts/python -m pip install -e '.[dev,gui]'
```

- [x] **Step 3: Verify `scripts/typecheck` locally**

Run: `scripts/typecheck`
Expected output:
```
0 errors, 0 warnings, 0 informations
```

---

### Task 2: Fix `SchedulePicker` DOM Timing Issues in GUI

**Done:** 2026-07-05: Added NoMatches import and defensive error handling to SchedulePicker methods and used call_after_refresh in on_mount.

**Files:**
- Modify: `src/github_usage/gui/widgets/schedule_picker.py:7-12,151-163,165-190,279-286,288-336`
- Test: `tests/test_gui_integration.py`
- Test: `tests/test_gui_scroll.py`

**Interfaces:**
- Consumes: Textual CSS query and lifecycle methods (`query_one`, `call_after_refresh`)
- Produces: Crash-free initialization of `SchedulePicker` when mounted in dialogs and setup wizard screens

- [x] **Step 1: Run GUI integration and scroll tests to verify failure baseline**

Run: `pytest tests/test_gui_integration.py tests/test_gui_scroll.py -v`
Expected: FAIL (5 errors due to `NoMatches: No nodes match '#ga-advanced'` and `'#local-preview'`)

- [x] **Step 2: Import `NoMatches` in `schedule_picker.py`**

In `src/github_usage/gui/widgets/schedule_picker.py`, update the imports at the top to include `NoMatches`:

```python
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Checkbox, Collapsible, Input, Label, Select, Static
```

- [x] **Step 3: Defer mount initialization and guard widget queries in `schedule_picker.py`**

Update `set_local_schedule`, `set_ga_cron`, `_set_ga_picker_disabled`, `_sync_advanced_panel`, `_refresh_previews`, `_on_field_changed`, `_init_mount_state`, and `on_mount` in `src/github_usage/gui/widgets/schedule_picker.py` with the following defensive implementations:

```python
    def set_local_schedule(self, weekday: int, hour: int, minute: int) -> None:
        """Populate local launchd fields."""
        if not self._show_local:
            return
        self._loading = True
        try:
            weekday = normalize_launchd_weekday(weekday)
            self.query_one(f"#{self._field_id('local-weekday')}", Select).value = str(weekday)
            self.query_one(f"#{self._field_id('local-hour')}", Input).value = str(hour)
            self.query_one(f"#{self._field_id('local-minute')}", Input).value = str(minute)
        except NoMatches:
            pass
        finally:
            self._loading = False
        self._refresh_previews()

    def set_ga_cron(self, cron: str) -> None:
        """Populate GA fields from a cron expression or advanced mode."""
        if not self._show_ga:
            return
        self._loading = True
        try:
            parsed = parse_weekly_cron_to_local(cron, local_timezone())
            advanced = self.query_one(f"#{self._field_id('ga-advanced')}", Checkbox)
            cron_input = self.query_one(f"#{self._field_id('ga-cron')}", Input)
            if parsed is None:
                advanced.value = True
                cron_input.value = cron
                self._ga_advanced = True
            else:
                advanced.value = False
                cron_input.value = cron
                self._ga_advanced = False
                weekday, hour, minute = parsed
                self.query_one(f"#{self._field_id('ga-weekday')}", Select).value = str(weekday)
                self.query_one(f"#{self._field_id('ga-hour')}", Input).value = str(hour)
                self.query_one(f"#{self._field_id('ga-minute')}", Input).value = str(minute)
            self._set_ga_picker_disabled(self._ga_advanced)
            self._sync_advanced_panel()
        except NoMatches:
            pass
        finally:
            self._loading = False
        self._refresh_previews()

    def _set_ga_picker_disabled(self, disabled: bool) -> None:
        try:
            for widget_id in (
                self._field_id("ga-weekday"),
                self._field_id("ga-hour"),
                self._field_id("ga-minute"),
            ):
                self.query_one(f"#{widget_id}").disabled = disabled
            self.query_one(f"#{self._field_id('ga-cron')}", Input).disabled = not disabled
        except NoMatches:
            pass

    def _sync_advanced_panel(self) -> None:
        if not self._show_ga:
            return
        try:
            panel = self.query_one(f"#{self._field_id('ga-cron-advanced')}", Collapsible)
            panel.collapsed = not self._ga_advanced
        except NoMatches:
            pass

    def _refresh_previews(self) -> None:
        if self._show_local:
            try:
                preview = self.query_one(f"#{self._field_id('local-preview')}", Static)
            except NoMatches:
                preview = None
            if preview is not None:
                values = self.get_local_schedule()
                preview.update(
                    describe_local_schedule(values.weekday, values.hour, values.minute)
                    if values
                    else "Enter a valid local day and time"
                )
        if self._show_ga:
            try:
                ga_preview = self.query_one(f"#{self._field_id('ga-preview')}", Static)
                cron_input = self.query_one(f"#{self._field_id('ga-cron')}", Input)
            except NoMatches:
                return
            cron_text = cron_input.value.strip()
            if self._ga_advanced:
                human = describe_cron_human(cron_text)
                ga_preview.update(
                    f"[b]Saved:[/b] {human or cron_text}"
                    + (f" [dim](cron: {cron_text})[/dim]" if human else " UTC")
                )
            else:
                values = self._read_ga_picker_values()
                if values:
                    weekday, hour, minute = values
                    ga_preview.update(
                        describe_ga_schedule_local(weekday, hour, minute, local_timezone())
                        + (f" [dim](cron: {cron_text})[/dim]" if cron_text else "")
                    )
                else:
                    ga_preview.update("Enter a valid day and time")

    @on(Select.Changed)
    @on(Input.Changed)
    @on(Checkbox.Changed)
    def _on_field_changed(self, event: Checkbox.Changed | Input.Changed | Select.Changed) -> None:
        if self._loading:
            return
        control = event.control
        if control is not None and control.id == self._field_id("ga-advanced"):
            self._ga_advanced = bool(event.value)
            self._set_ga_picker_disabled(self._ga_advanced)
            self._sync_advanced_panel()
        self._refresh_previews()
        self.post_message(self.Changed(self))

    def _init_mount_state(self) -> None:
        if self._show_ga:
            try:
                self._ga_advanced = self.query_one(f"#{self._field_id('ga-advanced')}", Checkbox).value
                self._set_ga_picker_disabled(self._ga_advanced)
            except NoMatches:
                pass
        self._refresh_previews()

    def on_mount(self) -> None:
        self.call_after_refresh(self._init_mount_state)
```

- [x] **Step 4: Verify GUI integration and scroll tests pass**

Run: `pytest tests/test_gui_integration.py tests/test_gui_scroll.py -v`
Expected output:
```
tests/test_gui_integration.py::GitHubUsageAppIntegrationTests::test_app_mounts_clean_and_switches_tabs PASSED
tests/test_gui_integration.py::GitHubUsageAppIntegrationTests::test_guided_setup_button_opens_wizard PASSED
tests/test_gui_integration.py::GitHubUsageAppIntegrationTests::test_setup_secrets_show_hide_toggle PASSED
tests/test_gui_scroll.py::GitHubUsageGuiScrollTests::test_j_key_scrolls_without_error PASSED
tests/test_gui_scroll.py::GitHubUsageGuiScrollTests::test_scroll_target_is_active_view PASSED
```

---

### Task 3: Full Suite Verification

**Done:** 2026-07-05: Verified entire suite with scripts/check and scripts/smoke.

**Files:**
- Test: `scripts/check`
- Test: `scripts/smoke`

- [x] **Step 1: Run full repo check script**

Run: `scripts/check`
Expected output ends with:
```
echo "check passed"
```

- [x] **Step 2: Run CLI smoke test script**

Run: `scripts/smoke`
Expected output: exits with 0 and shows CLI smoke verification passing.

- [ ] **Step 3: Commit changes**

```bash
git add scripts/typecheck .github/workflows/ci.yml src/github_usage/gui/widgets/schedule_picker.py
git commit -m "fix: resolve basedpyright CI discovery and GUI SchedulePicker DOM mount timing"
```
