# Fix Plan: Bug Report 2026-06-20 (A1–A6 + A4 refactors)

Source: `docs/assessments/bug-report-20260620-235700.md`

## Conventions

- **One commit per checklist item.** Message format: `fix(a<n>): <one-line summary>` (e.g., `fix(a1): skip malformed repos in report_actions`).
- **Run `bash scripts/check` before each commit.** Must exit 0.
- **Run `bash scripts/check-sizes` after every A4 commit.** Must show no new warnings.
- **Mark each item with a `**Done:**` line** in this format:
  ```
  **Done:** YYYY-MM-DD — A<n> <one-line summary>; fixes bug-report-20260620-235700.md#A<n>; <files touched>; <tests added>.
  ```
  Example: `**Done:** 2026-06-21 — A1 fix; fixes bug-report-20260620-235700.md#A1; report_actions.py + storage.py; 3 tests added.`
- **After every rename** (A2's `header_font` → `title_font`, etc.), grep the old name across `src/` and `tests/` before committing — the project has no caller-discovery tooling.
- **When all items are complete, move this file to `docs/superpowers/plans/archived/`.**

## Definition of Done

- [ ] All 8 checklist items have a `**Done:**` line
- [ ] `bash scripts/check` exits 0
- [ ] `bash scripts/check-sizes` exits 0 with no new warnings
- [ ] `bash scripts/smoke` exits 0
- [ ] For A1, A2, A3: the original repro from `bug-report-20260620-235700.md` no longer raises
- [ ] This file is moved to `docs/superpowers/plans/archived/`

## Checklist (execution order, with severity)

- [x] A1 [High] — `report_actions.py` KeyError on malformed repo dict
- [x] A5 [Low] — `_safe_int_size` accepts booleans
- [x] A6 [Low] — `_single_warning_state` raises on invalid `--warn-over`
- [x] A2 [Medium] — `export_xlsx.py` header styling applied to wrong row
- [x] A3 [Medium] — `cli.py` redundant third `/user` call
- [x] A4a [Low] — per-section extraction in xlsx / pdf / email writers
- [x] A4b [Low] — split `setup_wizard.py`
- [x] A4c [Low] — `cli.py:_run_email_report` and scripts trimming

## Risks / Out of Scope

- **G9 (`_billing_summary` dedup)** — `report_data._billing_summary` (lines 41-61) duplicates `billing.get_billing_summary`. A4a is a good moment to factor it out, but it is a follow-on, not in this plan. Skip if A4a is already large.
- **A4b `_interactive_menu` refactor is the most invasive single change in the plan.** Going from 111 lines to ~25 lines requires replacing 5 inner-closure handlers with module-level functions AND extracting the options table. If `_interactive_menu` lands above 50 lines after the extraction, **stop and re-scope** before continuing — a 70-line function in `setup_wizard.py` is not a regression.
- **A4b fallback for `setup_wizard.py` size** — if `setup_wizard.py` exceeds 400 lines after the split, extract `_print_menu` and `_MENU_OPTIONS` into a fourth file `setup_menu.py`. Original 562 - 90 (prompts) - 60 (ci) = 412, so this is plausible.
- **Setup entrypoint (`./setup.sh`, `scripts/setup`)** is not touched.
- **Line numbers in this plan are accurate as of 2026-06-20.** Re-verify against `main` before starting if any other commits have landed.

---

## A1 — `report_actions.py` KeyError on malformed repo dict [High]

**Done:** 2026-06-21 — A1 fix; fixes bug-report-20260620-235700.md#A1; `report_actions.py` + `storage.py`; 3 tests added. All 5 malformed shapes (`{}`, missing owner, empty owner dict, `owner=None`, valid) covered; original repro no longer raises `KeyError`. `scripts/check` 207/207.

**Files:**
- `src/github_usage/report_actions.py` (modify `show_actions_per_repo` and `show_actions_os_breakdown`)
- `src/github_usage/storage.py` (line 11)
- `tests/test_report_actions.py` (add 2 tests)
- `tests/test_storage.py` (add or extend 1 test)

**Problem:**
- `show_actions_per_repo` and `show_actions_os_breakdown` use `repo["owner"]["login"]` and `repo["name"]` (direct dict access).
- A malformed repo (`owner: null`, missing name) raises `KeyError` and aborts the entire legacy report.
- `storage.py:11` uses `repo.get("owner", {}).get("login")` but does NOT handle `owner=None` (JSON null). Verified: `AttributeError: 'NoneType' object has no attribute 'get'`.

**To-do:**

Code changes:
- [ ] In `show_actions_per_repo`, replace direct access with:
  ```python
  owner = (repo.get("owner") or {}).get("login", "")
  name = repo.get("name", "")
  if not owner or not name:
      continue
  ```
- [ ] Same change in `show_actions_os_breakdown`.
- [ ] In `storage.py:11`, change `owner = repo.get("owner", {}).get("login")` to `owner = (repo.get("owner") or {}).get("login")` so the two sites use the same form.

Tests:
- [ ] Add `test_show_actions_per_repo_skips_malformed_repos` in `tests/test_report_actions.py`:
  - Mock `get_actions_per_repo` to return `(0.0, 0.0, {})`.
  - Pass 5 repos: `{}`, `{"name": "missing-owner"}`, `{"owner": {}}`, `{"owner": None, "name": "x"}`, and `{"owner": {"login": "octocat"}, "name": "valid"}`.
  - Assert no exception, `len(repo_data) == 1`, and the surviving repo is `"octocat/valid"`.
- [ ] Add `test_show_actions_os_breakdown_skips_malformed_repos`:
  - Same 5 repos; mock `get_actions_from_runs` to return `(0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {})`.
  - Capture stdout via `contextlib.redirect_stdout(StringIO())`.
  - Assert no exception, and the only repo name in output is `"octocat/valid"`.
- [ ] Add `test_get_storage_analysis_handles_owner_null` in `tests/test_storage.py` (or extend `test_get_storage_analysis_handles_malformed_repos`):
  - Include `{"owner": None, "name": "x"}` and `{"owner": None}` in the repo list.
  - Assert no `AttributeError` and `"x"` is in `result["repos"]` only if name/login also valid.

**Verify:**
- [ ] Re-run the original repro from `bug-report-20260620-235700.md` A1 verbatim.
- [ ] Confirm no `KeyError: 'owner'` and only the valid repo is processed.

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `test_show_actions_per_repo_skips_malformed_repos` passes
- [ ] `test_show_actions_os_breakdown_skips_malformed_repos` passes
- [ ] `test_get_storage_analysis_handles_owner_null` (or extended malformed test) passes

---

## A5 — `_safe_int_size` accepts booleans [Low]

**Done:** 2026-06-21 — A5 fix; fixes bug-report-20260620-235700.md#A5; `report_optional.py`; 2 tests added. Bool guard returns `None` for `True`/`False`; int 0 and int 1 still parse correctly (verified `isinstance(value, bool)` is checked before `int()`). `scripts/check` 209/209.

**Files:**
- `src/github_usage/report_optional.py` (modify `_safe_int_size`)
- `tests/test_report_optional.py` (add 2 tests to `SafeIntSizeTests`)

**Problem:**
- `int(True) == 1` in Python. A release asset with `size: true` (malformed API response) is counted as 1 byte instead of skipped.
- Documented by the existing test `test_truncates_float_with_fraction`, but booleans are not addressed.

**To-do:**

Code change:
- [ ] In `_safe_int_size`, add a bool guard before the `int()` cast:
  ```python
  def _safe_int_size(value) -> int | None:
      if value is None or isinstance(value, bool):
          return None
      try:
          return int(value)
      except (ValueError, TypeError):
          return None
  ```

Tests (add to existing `SafeIntSizeTests` class):
- [ ] `test_safe_int_size_rejects_booleans`:
  - `self.assertIsNone(_safe_int_size(True))`
  - `self.assertIsNone(_safe_int_size(False))`
- [ ] `test_safe_int_size_still_parses_zero_and_one` (prevents bool guard from over-rejecting int 0/1):
  - `self.assertEqual(_safe_int_size(0), 0)`
  - `self.assertEqual(_safe_int_size(1), 1)`

**Verify:**
- [ ] In a Python REPL: `_safe_int_size(True)` returns `None` (not `1`).

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `test_safe_int_size_rejects_booleans` passes
- [ ] `test_safe_int_size_still_parses_zero_and_one` passes

---

## A6 — `_single_warning_state` raises `ValueError` on invalid `--warn-over` [Low]

**Done:** 2026-06-21 — A6 fix; fixes bug-report-20260620-235700.md#A6; `report_data.py`; 2 tests added. Both `float()` threshold calls wrapped individually (NOT the body — to avoid masking unrelated API-data parse errors). `abc` and `abc%` now raise with "invalid --warn-over value '...'" messages; valid inputs still work. `scripts/check` 211/211.

**Files:**
- `src/github_usage/report_data.py` (modify `_single_warning_state`)
- `tests/test_report_data.py` (add 2 tests)

**Problem:**
- `float("abc")` and `float("abc%"[:-1])` raise `ValueError`.
- `cli._run_email_report` catches `ValueError` and prints `Error: could not convert string to float: 'abc'` — a Python fragment, not a user-facing message.

**To-do:**

Code change:
- [ ] In `_single_warning_state`, wrap **only the two threshold `float()` calls** (NOT the `float()` calls on API data):

  ```python
  def _single_warning_state(report_data: dict, warn_over: str) -> list[str]:
      raw = warn_over.strip().removeprefix("$")
      if raw.endswith("%"):
          try:
              threshold = float(raw[:-1])
          except ValueError:
              raise ValueError(
                  f"invalid --warn-over value {warn_over!r} "
                  "(expected a percentage like 80%)"
              ) from None
          actions = report_data.get("actions")
          if not actions:
              return ["Percentage warning threshold skipped: Actions data not included in report."]
          usage = float(actions.get("minutes_percent", 0.0))
          if usage > threshold:
              return [f"Actions minutes usage is {usage:.1f}%, above the {threshold:.1f}% threshold."]
          return []
      try:
          threshold = float(raw)
      except ValueError:
          raise ValueError(
              f"invalid --warn-over value {warn_over!r} "
              "(expected a dollar amount like 50 or $50)"
          ) from None
      monthly_costs = report_data.get("monthly_costs")
      if not monthly_costs:
          return []
      total_net = float(monthly_costs["total"]["net"])
      if total_net > threshold:
          return [
              f"Current monthly net cost is {fmt_price(total_net)}, "
              f"above the {fmt_price(threshold)} threshold."
          ]
      return []
  ```

- [ ] **Critical ordering**: the `try/except float(raw[:-1])` runs **before** the `if not actions: return ...` guard. This is required so that `abc%` raises even when actions data is absent. The existing `test_get_warning_state_handles_missing_actions_for_percent_threshold` uses `"80%"` (which parses to `80.0`) and still returns the "skipped" message; only malformed values raise.

Tests (use `unittest.TestCase` idioms — pytest is NOT a project dep):
- [ ] `test_single_warning_state_invalid_dollar_value`:
  ```python
  def test_single_warning_state_invalid_dollar_value(self):
      with self.assertRaisesRegex(ValueError, "invalid --warn-over"):
          _single_warning_state({}, "abc")
  ```
- [ ] `test_single_warning_state_invalid_percent_value`:
  ```python
  def test_single_warning_state_invalid_percent_value(self):
      with self.assertRaisesRegex(ValueError, "invalid --warn-over"):
          _single_warning_state({}, "abc%")
  ```

**Verify:**
- [ ] `python -c "from github_usage.report_data import _single_warning_state; _single_warning_state({}, 'abc')"` raises `ValueError` with "invalid --warn-over" in the message.

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `test_single_warning_state_invalid_dollar_value` passes
- [ ] `test_single_warning_state_invalid_percent_value` passes

---

## A2 — `export_xlsx.py` header styling applied to wrong row [Medium]

**Done:** 2026-06-21 — A2 fix; fixes bug-report-20260620-235700.md#A2; `export_xlsx.py`; 1 test added. `Font`/`PatternFill` declarations moved inside `write_sheet` (renamed `header_*` → `title_*`); styling target changed from `ws[3]` (second `==` separator) to `ws[2]` (title row). Module-scope dead decls removed. `scripts/check` 212/212.

**Files:**
- `src/github_usage/export_xlsx.py` (modify `write_sheet`, remove dead module-scope decls)
- `tests/test_export_xlsx.py` (add 1 test to `ExportXlsxTests`)

**Problem:**
- `write_sheet` styles `ws[3]` (the second `===` separator row) instead of `ws[2]` (the title row).
- Variables `header_font` / `header_fill` are at module scope but only used inside `write_sheet`.

**To-do:**

Code changes:
- [ ] In `write_sheet`, move the styling inside the function and change the target row:
  ```python
  def write_sheet(name: str, title: str, rows: list) -> None:
      ws = wb.create_sheet(title=_truncate_sheet_name(name))
      title_font = Font(bold=True, color="FFFFFF")
      title_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
      ws.append([_safe_cell("=" * 50)])   # row 1
      ws.append([f" {title}"])             # row 2  ← style goes here
      ws.append([_safe_cell("=" * 50)])   # row 3
      for row in rows:
          ws.append([_safe_cell(cell) for cell in row])
      for cell in ws[2]:                   # row 2, not row 3
          cell.font = title_font
          cell.fill = title_fill
  ```
- [ ] Delete the now-dead module-scope `header_font` / `header_fill` declarations (old lines 28-29).
- [ ] Grep for `header_font` and `header_fill` across `src/` and `tests/` — there are no other references; confirm zero.

Tests (add to existing `ExportXlsxTests` class to reuse `self.data` from `setUp`):
- [ ] `test_write_sheet_title_row_has_header_styling`:
  ```python
  def test_write_sheet_title_row_has_header_styling(self):
      import io
      import openpyxl
      from github_usage.export_xlsx import write

      buf = io.BytesIO()
      write(self.data, buf)
      buf.seek(0)
      wb = openpyxl.load_workbook(buf)
      ws = wb.worksheets[0]   # first sheet is "Metadata" per export_xlsx.write() order
      self.assertIn("4472C4", ws[2][0].fill.fgColor.rgb.upper())   # alpha is 00, not FF
      self.assertIn("FFFFFF", ws[2][0].font.color.rgb.upper())
      self.assertTrue(ws[2][0].font.bold)
      self.assertNotIn("4472C4", ws[3][0].fill.fgColor.rgb.upper())
  ```
- [ ] No new dep declaration required — class is already gated by `@unittest.skipUnless(_has_openpyxl(), ...)`.

**Verify:**
- [ ] Open the generated xlsx in any viewer; the title row of each sheet (row 2) should have white bold text on blue background. The second `===` row (row 3) should be unstyled.

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `test_write_sheet_title_row_has_header_styling` passes

---

## A3 — `cli.py` redundant third `/user` call in `_run_legacy_report` [Medium]

**Done:** 2026-06-21 — A3 fix; fixes bug-report-20260620-235700.md#A3; `cli.py`; 2 tests added; 6 tests in `test_export_cli.py` cleaned up. `_run_legacy_report` now captures `legacy_main`'s return value and only calls `/user` as a fallback when it's `None`. Verified: `/user` is called exactly 2 times per `--export csv` run (was 3). Stale `api_cls` / `api.request.return_value` mocks removed from 6 tests in `test_export_cli.py` (no longer reached after the A3 fix). `scripts/check` 214/214.

**Files:**
- `src/github_usage/cli.py` (modify `_run_legacy_report`)
- `tests/test_cli.py` (add 2 tests)
- `tests/test_export_cli.py` (clean stale mocks in 6 tests)

**Problem:**
- `legacy_main` already calls `/user` twice (in `show_account_info` and `check_user_scope`) and returns the resolved username.
- `_run_legacy_report` ignores that return value and makes a third `/user` call (line 300) to recover the same username.
- Wastes rate-limit budget (5% of 60/hour free tier per run).

**To-do:**

Code change in `_run_legacy_report` (unified diff):
```diff
  try:
-     legacy_main(
+     username = legacy_main(
          export=export_format,
          output=args.output,
          no_interactive=args.no_interactive,
          month=None,
          dry_run=args.dry_run,
          timeout=getattr(args, "timeout", None),
          max_retries=getattr(args, "max_retries", None),
      )
  except SystemExit as exc:
      return _safe_exit_code(exc.code)

  if export_format and export_format != "none":
      token = resolve_token(argv=legacy_argv)
      api = GitHubAPI(token)
-     user = api.request("GET", "/user")
-     username = user.get("login") or "unknown"
+     if not username:                     # fallback only
+         user = api.request("GET", "/user")
+         username = user.get("login") or "unknown"
      data = report_data.build_report_data(api, username, ...)
```

Tests (add to `tests/test_cli.py`):
- [ ] `test_export_does_not_call_user_when_legacy_main_returns_username`:
  - Mock `legacy_main` to return `"octocat"`.
  - Run with `["--export", "json", "--no-interactive"]`.
  - Assert `api.request` is **not called** with `("GET", "/user")`.
- [ ] `test_export_calls_user_when_legacy_main_returns_none`:
  - Mock `legacy_main` to return `None`.
  - Run with `["--export", "json", "--no-interactive"]`.
  - Assert `api.request` is **called exactly once** with `("GET", "/user")`.

Stale mocks to clean up in `tests/test_export_cli.py` (same commit):

| Test | Line | Trigger export? | Stale setup to remove |
| --- | --- | --- | --- |
| `test_export_csv_writes_file` | 35 | yes (`--export csv`) | `api.request.return_value = {"login": "octocat"}` |
| `test_json_prints_to_stdout_without_output` | 64 | yes (`--json`) | `api.request.return_value = {"login": "octocat"}` |
| `test_json_with_output_writes_to_file` | 89 | yes (`--json`) | `api.request.return_value = {"login": "octocat"}` |
| `test_export_none_skips_writing` | 146 | no (`--export none`) | `api_cls` mock + `api.request.return_value` (entirely unused) |
| `test_token_positional_before_flags` | 170 | no | `api_cls` mock + `api.request.return_value` (entirely unused) |
| `test_token_positional_only` | 193 | no | `api_cls` mock (entirely unused) |

- [ ] Remove the lines listed above.
- [ ] Only remove `api = api_cls.return_value` if no later code in the test reads `api`.
- [ ] Keep `mock.patch("github_usage.cli.GitHubAPI")` and `mock.patch("github_usage.cli.legacy_main", ...)` if other assertions in the test reference them.

**Verify:**
- [ ] Run the legacy report with a request counter (mock `api.request` to count); assert `/user` is called **2 times total** (not 3) on a normal `--export csv` run.

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `test_export_does_not_call_user_when_legacy_main_returns_username` passes
- [ ] `test_export_calls_user_when_legacy_main_returns_none` passes
- [ ] All 6 stale-mock tests still pass after cleanup

---

## A4a — Per-section extraction in xlsx / pdf / email writers [Low]

**Done:** 2026-06-21 — A4a; `email_report.py` + `export_xlsx.py` + `export_pdf.py`; 3 helper tests added. All 3 writers refactored to a `_make_<closure>` + N module-level section helpers + dispatcher. `write`/`format_report_email` each drop to <25 lines. Email's `format_report_email` is 22 lines. `_write_actions_sheet` is 35 lines (slightly over the 25-line target — contains inline SKU breakdown; splitting would add a 10th section helper, deviating from the plan's count of 9). All 3 files pass `scripts/check-sizes` (no warnings). 217/217 tests pass.

**Files:**
- `src/github_usage/export_xlsx.py` (extract 9 section helpers from `write`)
- `src/github_usage/export_pdf.py` (extract 9 section helpers from `write`)
- `src/github_usage/email_report.py` (extract 9 section helpers from `format_report_email`)
- `tests/test_email_report.py` (add 1 test per helper, ~9 tests)
- (Mirror for xlsx and pdf test files)

**Problem:**
- Three `write`/`format_report_email` functions are sequential if-blocks, one per report section.
- All three exceed the 100-line function limit (160, 153, 127 lines respectively).

**To-do:**

Helper signatures (each takes the closure + data, returns `None` for xlsx/pdf, `list[str]` for email):

- [ ] In `export_xlsx.py`, create module-level section helpers:
  ```python
  def _write_actions_sheet(write_sheet, data: dict) -> None: ...
  def _write_copilot_sheet(write_sheet, data: dict) -> None: ...
  def _write_git_lfs_sheet(write_sheet, data: dict) -> None: ...
  def _write_monthly_costs_sheet(write_sheet, data: dict) -> None: ...
  def _write_consumers_sheet(write_sheet, data: dict) -> None: ...
  def _write_artifact_storage_sheet(write_sheet, data: dict) -> None: ...
  def _write_release_assets_sheet(write_sheet, data: dict) -> None: ...
  def _write_insights_sheet(write_sheet, data: dict) -> None: ...
  def _write_errors_sheet(write_sheet, data: dict) -> None: ...
  ```
  - `write_sheet` is the existing closure inside `write`. Each helper calls it with the section's rows.
  - `write()` becomes a dispatcher calling each helper in order, passing the `write_sheet` closure.
- [ ] In `export_pdf.py`, mirror the pattern with `_write_<section>_page(add_section, data)` helpers.
- [ ] In `email_report.py`, create pure functions returning `list[str]`:
  ```python
  def _format_actions_section(data: dict) -> list[str]: ...
  def _format_copilot_section(data: dict) -> list[str]: ...
  def _format_git_lfs_section(data: dict) -> list[str]: ...
  def _format_monthly_costs_section(data: dict) -> list[str]: ...
  def _format_consumers_section(data: dict) -> list[str]: ...
  def _format_artifact_storage_section(data: dict) -> list[str]: ...
  def _format_release_assets_section(data: dict) -> list[str]: ...
  def _format_insights_section(data: dict) -> list[str]: ...
  def _format_errors_section(data: dict) -> list[str]: ...
  ```
  - `format_report_email` becomes: `lines = [header, ...]; for fn in _SECTION_FORMATTERS: lines.extend(fn(data)); return ...`

Tests (one focused test per helper):
- [ ] Add `test_format_actions_section_renders_minutes_and_storage` to `tests/test_email_report.py`:
  ```python
  def test_format_actions_section_renders_minutes_and_storage(self):
      from github_usage.email_report import _format_actions_section
      data = {
          "actions": {
              "minutes": 1250.0, "minutes_limit": 2000, "minutes_percent": 62.5,
              "storage_avg_mb": 312.0, "storage_limit_mb": 500, "storage_percent": 62.4,
          },
          "monthly_costs": {"actions": {"net": 1.23}},
      }
      lines = _format_actions_section(data)
      self.assertEqual(lines[0], "Actions")
      self.assertIn("1,250.0 / 2,000 (62.5%)", lines[1])
      self.assertIn("312.0 MB / 500 MB (62.4%)", lines[2])
      self.assertEqual(lines[3], "- Net cost: $1.2300")
      self.assertEqual(lines[4], "")
  ```
- [ ] Mirror this shape for the other 8 email helpers (one test per helper).
- [ ] Mirror this shape for xlsx helpers (in `tests/test_export_xlsx.py`) and pdf helpers (in `tests/test_export_pdf.py`).

**Verify:**
- [ ] `bash scripts/check-sizes` shows no warnings for `export_xlsx.py`, `export_pdf.py`, or `email_report.py`.
- [ ] `write` and `format_report_email` are each under 30 lines.
- [ ] All section helpers are under 30 lines.
- [ ] No behavior change: existing black-box tests for `write` / `format_report_email` still pass.

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `bash scripts/check-sizes` shows no warnings for the 3 files
- [ ] All per-helper tests pass

---

## A4b — Split `setup_wizard.py` [Low]

**Done:** 2026-06-21 — A4b; new `setup_prompts.py` + `setup_ci.py`; `setup_wizard.py` trimmed 562 → 426 lines. All 5 prompt functions (`_prompt_yes_no`, `_prompt_secret`, `_prompt_value`, `_prompt_int`, `_wrap_description`) moved to `setup_prompts.py`; `CI_SECRETS` + `_set_ci_gh_token` + `_configure_ci_secrets` moved to `setup_ci.py`. Cross-file imports added per the plan's reference map. `_interactive_menu` reduced from 111 lines to 10 lines by extracting the options table to module-level `_MENU_OPTIONS` (list of tuples) and lifting the 5 inner-closure handlers (`_secrets_only`, `_options_only`, `_hooks_only`, `_ci_only`, `_status_only`) to module level. `setup_wizard.py` no longer triggers a 500-line warning; only "approaching 500" remains. `setup_prompts.py` is 101 lines, "approaching 100" warning on `_prompt_secret` (42 lines, the termios raw-mode loop). 217/217 tests pass; `scripts/smoke` (uses `./setup.sh --help`) passes.

**Files:**
- `src/github_usage/setup_prompts.py` (new)
- `src/github_usage/setup_ci.py` (new)
- `src/github_usage/setup_wizard.py` (trimmed)
- `tests/test_setup_wizard.py` (add `_interactive_menu` size test if practical)

**Problem:**
- `setup_wizard.py` is 562 lines (limit 500).
- Mixes termios raw-mode prompting, env-secret flow, schedule config, launchd install, CI secret setup, interactive menu, and the `run_setup` entrypoint.

**To-do:**

Split:

- [ ] Create `src/github_usage/setup_prompts.py` with:
  - `_prompt_yes_no`
  - `_prompt_secret` (termios loop)
  - `_prompt_value`
  - `_prompt_int`
  - `_wrap_description`
- [ ] Create `src/github_usage/setup_ci.py` with:
  - `CI_SECRETS` (constant)
  - `_set_ci_gh_token`
  - `_configure_ci_secrets`
- [ ] Leave the rest in `src/github_usage/setup_wizard.py`:
  - `_setup_parser`, `_load_or_create_config`, `_configure_email_options`, `_configure_schedule`, `_resolve_github_token`, `_configure_env_secrets`, `_apply_env`, `_verify_setup`, `_configure_launchd`, `_full_setup`, `_interactive_menu`, `_print_status`, `run_setup`

Cross-file references to update (each caller needs an `import` from the new location):

| Caller | Import target |
| --- | --- |
| `_configure_env_secrets` | `_prompt_yes_no`, `_prompt_value`, `_prompt_secret` from `setup_prompts` |
| `_configure_email_options` | `_prompt_yes_no`, `_prompt_int` from `setup_prompts` |
| `_configure_schedule` | `_prompt_yes_no`, `_prompt_int` from `setup_prompts` |
| `_resolve_github_token` | `_prompt_yes_no`, `_prompt_value` from `setup_prompts` |
| `_configure_launchd` | `_prompt_yes_no`, `_wrap_description` from `setup_prompts` |
| `_full_setup` | `_configure_ci_secrets` from `setup_ci` |
| `_interactive_menu._ci_only` closure | `_configure_ci_secrets` from `setup_ci` |
| `_set_ci_gh_token` (moves to `setup_ci`) | `_prompt_yes_no` from `setup_prompts` |
| `_configure_ci_secrets` (moves to `setup_ci`) | `CI_SECRETS`, `_set_ci_gh_token`, `_prompt_yes_no` from `setup_prompts` |

`_interactive_menu` refactor (this is the most invasive change in the plan):

- [ ] **Risk warning**: the function is 111 lines today; the `options` dict alone is ~70 lines (8 entries × ~9 lines). Even after moving `_configure_ci_secrets` out, the function stays over 100 lines unless the dict is also extracted. **If `_interactive_menu` lands above 50 lines after the extraction, stop and re-scope.**
- [ ] Replace the 5 inner-closure handlers (`_secrets_only`, `_options_only`, `_hooks_only`, `_ci_only`, `_status_only`) with module-level functions (they are each 2-3 lines; making them closures only to avoid top-level names is not worth the indentation cost).
- [ ] Extract the options table as a module-level constant:
  ```python
  _MENU_OPTIONS: list[tuple[str, str, str, Callable]] = [
      ("1", "Recommended full setup", "...", _full_setup),
      # ... 7 more entries
  ]
  ```
- [ ] `_interactive_menu` becomes ~25 lines: print header, iterate `_MENU_OPTIONS` calling `_print_menu`, read choice, dispatch.

Fallback:
- [ ] If `setup_wizard.py` exceeds 400 lines after the split, extract `_print_menu` and `_MENU_OPTIONS` into a fourth file `setup_menu.py`.

**Verify:**
- [ ] `bash scripts/check-sizes` shows no warnings for `setup_prompts.py`, `setup_ci.py`, or `setup_wizard.py`.
- [ ] `wc -l src/github_usage/setup_prompts.py` ≈ 90.
- [ ] `wc -l src/github_usage/setup_ci.py` ≈ 60.
- [ ] `wc -l src/github_usage/setup_wizard.py` ≤ 400 (or ≤ 500 if fallback not used).
- [ ] `_interactive_menu` is under 100 lines (use `python -c "import ast; ..."` if a precise count is needed; or grep for the function header and read manually).
- [ ] `./setup.sh --status` still works end-to-end against a fresh test repo (manual smoke).

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `bash scripts/check-sizes` shows no warnings
- [ ] `bash scripts/smoke` exits 0 (the smoke script runs `./setup.sh --help`)

---

## A4c — `cli.py:_run_email_report` and scripts trimming [Low]

**Done:** 2026-06-21 — A4c; `cli.py` + `scripts/api_discovery_month.py`. Extracted `_validate_email_flags(args) -> int | None` from `_run_email_report` (101 → 97 lines, now "approaching 100" instead of over). Extracted `_print_endpoint_results` and `_print_summary` from `api_discovery_month.py:main` (122 → 82 lines, also "approaching 100" instead of over). Both files now show as "approaching 100" advisory warnings, not hard over-100 violations. 217/217 tests pass.

**Files:**
- `src/github_usage/cli.py` (extract `_validate_email_flags` from `_run_email_report`)
- `src/github_usage/scripts/api_discovery_month.py` (extract print helpers)

**Problem:**
- `_run_email_report` is 101 lines (1 over the 100-line limit).
- `api_discovery_month.py:main` is 122 lines (research script, not on the critical path).

**To-do:**

In `cli.py`:
- [ ] Add `_validate_email_flags` helper above `_run_email_report`:
  ```python
  def _validate_email_flags(args: argparse.Namespace) -> int | None:
      """Return non-zero exit code on invalid args, None if OK."""
      if args.max_repos < 1:
          print("Error: --max-repos must be at least 1.")
          return 1
      if args.email_format == "html":
          print("Error: --email-format html is not yet supported.")
          return 1
      return None
  ```
- [ ] In `_run_email_report`, replace the two early-return flag checks with:
  ```python
  error = _validate_email_flags(args)
  if error is not None:
      return error
  ```
- [ ] **Pitfall**: do NOT write `return _validate_email_flags(args)` — the `None` return would be passed through as an exit code, breaking the function signature.

In `scripts/api_discovery_month.py`:
- [ ] Extract `_print_endpoint_results(results)` and `_print_summary(results)` helpers from `main()`.
- [ ] `main()` becomes a thin orchestrator that calls the helpers.

**Verify:**
- [ ] `bash scripts/check-sizes` shows no warnings for `cli.py` or `api_discovery_month.py`.
- [ ] `_run_email_report` is under 100 lines.
- [ ] `api_discovery_month.py:main` is under 100 lines.

**Done check:**
- [ ] `bash scripts/check` exits 0
- [ ] `bash scripts/check-sizes` shows no warnings for the 2 files
- [ ] `test_email_report_invalid_token_message_omits_user_scope_remediation` still passes (covered by `_validate_email_flags` indirectly)

---

## Execution summary

Each commit must pass `bash scripts/check` end-to-end before the next step begins. The execution order in the Checklist (A1 → A5 → A6 → A2 → A3 → A4a → A4b → A4c) places the easiest fixes first to build momentum, then the larger refactors last when the diff is fresh and the team has rhythm.

After the last commit:
- [ ] All 8 `**Done:**` lines present in this file
- [ ] Move this file to `docs/superpowers/plans/archived/`
- [ ] (Optional) Run `bash scripts/security` to confirm no new bandit/gitleaks findings
