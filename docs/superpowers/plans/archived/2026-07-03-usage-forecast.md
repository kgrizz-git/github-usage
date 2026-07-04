> **Status:** COMPLETE

# Usage Forecast for Legacy and Email Reports

Add end-of-month projections for Actions minutes, artifact storage (avg MB), and premium requests to both the legacy terminal report and the scheduled email report (text + HTML). Extrapolate current usage based on day-of-month trajectory and estimate when free-tier or plan limits will be exhausted.

---

## Phase 1 — Core forecast computation

Create `src/github_usage/forecast.py` with a single pure function:

```python
def compute_forecast(
    *,
    day_of_month: int,
    days_in_month: int,
    minutes: float,
    minutes_limit: float,
    storage_avg_mb: float,
    storage_limit_mb: float,
    premium_requests: float,
    premium_requests_limit: float | None,
) -> dict | None:
```

**Guard: minimum-day threshold.** When `day_of_month < 3`, return `None` — early-month projections are too volatile to be useful.

**Guard: date validation.** If `day_of_month > days_in_month` or `day_of_month < 1`, return `None`.

**Projection math** (only when guards pass):
- `ratio = days_in_month / day_of_month`
- `projected_minutes = minutes * ratio`
- `projected_storage_avg_mb = storage_avg_mb * ratio`
- `projected_premium_requests = premium_requests * ratio`

**Rounding:** Projected values use full precision internally. Display rounds to 1 decimal place in rendered output; exports keep full precision.

**Skip when empty:** If all three current values (`minutes`, `storage_avg_mb`, `premium_requests`) are 0.0 (all sections disabled or errored), return `None`.

**Run-out estimate** (for each metric with a known limit):
- If `current_value > 0` and `projected >= limit`: `run_out_day = ceil(day_of_month * limit / current_value)`
- Return `None` for `run_out_day` when the metric won't reach its limit this month, the limit is unknown, or `current_value` is 0.
- On the last day of the month, if `current_value > limit`, `run_out_day` will be earlier than today; render it as "day N" anyway because it signals the metric has already exceeded its allowance.

**Return dict shape:**
```python
{
    "day_of_month": int,
    "days_in_month": int,
    "minutes": {"current": float, "projected": float, "limit": float, "run_out_day": int | None},
    "storage_avg_mb": {"current": float, "projected": float, "limit": float, "run_out_day": int | None},
    "premium_requests": {"current": float, "projected": float, "limit": float | None, "run_out_day": int | None},
}
```

**Add to `report_helpers.py`:**
- `days_in_month(reference_date)` — analogous to existing `hours_in_month()` but returning days. Implement via `calendar.monthrange(reference_date.year, reference_date.month)[1]`.
- `day_of_month(reference_date)` — convenience wrapper for `reference_date.day`.
- Both accept `date | None` and default to `date.today()`.

---

## Phase 2 — Render-time forecast integration

Do **not** store `forecast` in the cached report dict. This repo caches fetched report snapshots and then reuses them in the CLI, GUI, exports, and email dry-run paths. A date-sensitive derived forecast inside the cache would drift immediately and make cached output stale in exactly the way this feature is meant to avoid.

Instead, compute the forecast from the already-fetched current values at the moment a consumer renders or exports the report.

### New helper (`report_forecast_data.py`)

Create a small helper module, separate from the pure math in `forecast.py`:

```python
def build_report_forecast(
    report: dict,
    *,
    premium_requests_limit: float | None = None,
    reference_date: date | None = None,
) -> dict | None:
```

Responsibilities:
- Read current values from a report dict and call `compute_forecast()`.
- Default missing sections to `0.0` so cached/partial reports still render safely:
  - `minutes = float((report.get("actions") or {}).get("minutes", 0.0))`
  - `storage_avg_mb = float((report.get("actions") or {}).get("storage_avg_mb", 0.0))`
  - `premium_requests = float((report.get("copilot") or {}).get("total_requests", 0.0))`
- Read limits from the report when present, otherwise fall back to `2000` minutes and `500` MB.
- Derive `day_of_month` and `days_in_month` from `reference_date or date.today()`.
- Return `None` when the underlying data is insufficient, matching `compute_forecast()`.

This keeps the computation logic reusable for text/HTML renderers, legacy terminal output, TUI summary rows, and exporters without duplicating section-reading code.

### What should *not* change

- `report_data.build_report_data()` should **not** add `report["forecast"]`.
- `legacy_report_data.build_legacy_report_data()` should **not** add `data["forecast"]`.
- `report_cache.email_cache_params()` and `report_cache.legacy_cache_params()` should **not** gain forecast-specific inputs such as `premium_requests_limit`; those affect presentation, not the fetched data shape.
- Cached reports loaded by `cli.py`, `legacy_report.py`, and `gui_backend.py` should render a fresh forecast based on the current day without forcing a refetch.

---

## Phase 3 — Rendering

### Plain-text email (`email_report_text.py`)

Add `_format_forecast_section(data, *, premium_requests_limit=None, reference_date=None)` → `list[str]`:

```
Monthly Forecast (day 15 of 31)
───────────────────────────────────────────
Metric              Current    Projected  Limit    Run-out
Actions Minutes     823.0      1,699.7    2,000    day 27
Storage (avg MB)    145.2      300.1      500      --
Premium Requests    120.0      247.9      --       --
```

- "Run-out" column shows "day N" (e.g. "day 27") when the limit will be reached or exceeded, or "--" when no exhaustion is expected or the limit is unknown.
- Use `{value:,.1f}` for current/projected numbers and `{limit:,.0f}` for limits.
- Call `build_report_forecast()` inside the formatter. If it returns `None`, render nothing.
- **Placement:** Append to the end of `_SECTION_FORMATTERS` (after `_format_errors_section`), so the forecast appears at the bottom of the email body before the API quota notes. Create a new tuple with the forecast formatter appended; tuples are immutable.

### HTML email (`email_report_html.py`)

Add `_format_html_forecast_section(data, *, premium_requests_limit=None, reference_date=None)` → `list[str]`:

- Same table structure as text, wrapped in `<table>` with header row.
- Escape all text with `html.escape`.
- Call `build_report_forecast()` inside the formatter. If it returns `None`, render nothing.
- **Placement:** Append to the end of `_SECTION_HTML_FORMATTERS` (after `_format_html_errors_section`), same reasoning as above. Create a new tuple.

### Email formatter entry points (`email_report.py`)

The public formatter functions currently accept only `data`. Extend the surface so callers can opt into a configured premium-requests limit without mutating cached report dicts:

```python
def format_report_email(
    data: dict,
    *,
    premium_requests_limit: float | None = None,
    reference_date: date | None = None,
) -> str: ...

def format_html_report(
    data: dict,
    *,
    premium_requests_limit: float | None = None,
    reference_date: date | None = None,
) -> str: ...
```

Thread these kwargs through to the forecast section formatter only; other sections stay unchanged.

### Legacy terminal (`legacy_terminal.py`)

Add `render_forecast(data, *, premium_requests_limit=None, reference_date=None)` call in `render_legacy_report()`, placed after `render_final_summary_from_data(data)` and before `render_what_else()`. The renderer should call `build_report_forecast()` internally rather than reading `data["forecast"]`. The function lives in a new `report_forecast.py` module and uses `print_header()` / `print_sep()` from `terminal.py`. Keep `report_forecast.py` small; if it grows beyond ~100 lines, split it further.

### TUI summary rows (`legacy_report_summary.py`)

Add forecast rows to `legacy_report_detail_rows()`:
- "Projected minutes at month end: X / 2,000 (Y%)"
- "Projected storage at month end: X MB / 500 MB (Y%)"
- "Projected premium requests at month end: X" (limit and percent shown only if `premium_requests_limit` is known)

Where `Y%` is `projected / limit * 100`. Compute the forecast inside `legacy_report_detail_rows()` (or via a tiny local helper) and skip these rows entirely when the computed forecast is `None`.

---

## Phase 4 — Configuration, CLI, workflow, and TUI

### Profile config (`setup_config.py`)

Add to `DEFAULT_EMAIL_REPORT`:
```python
"include_forecast": True,
"premium_requests_limit": None,  # when None, run-out day is not calculated; limit column shows "--"
```

Add to `_email_flags_from_dict()` (following the existing `include_*` → `--include-*` pattern):
- `include_forecast` → `--include-forecast` (when `True`)
- `premium_requests_limit` → `--premium-requests-limit <value>` (when not `None`)

### CLI parsers (`cli_parsers.py`)

Add `--include-forecast` / `--no-include-forecast` and `--premium-requests-limit` to `_email_parser()`.

For `_legacy_parser()`: the legacy parser currently has **no** section-level include/skip flags (unlike the email parser which has `--skip-actions`, `--skip-copilot`, `--skip-lfs`). To avoid breaking this pattern, thread `include_forecast` through the config/profile mechanism only for the legacy path — don't add a CLI flag to `_legacy_parser()`. The legacy report always includes the forecast when `include_forecast` is `True` in the active profile (or the default). If a CLI toggle is later desired, it should be added alongside the other section flags in a separate change.

### Legacy report session (`legacy_report.py`)

Do **not** thread forecast config into `build_legacy_report_data()`. Instead, read the active profile's `email_report.include_forecast` and `email_report.premium_requests_limit` at render time inside `run_legacy_report_session()` / its caller and pass them into `render_legacy_report()`.

### Email CLI path (`cli.py`)

Thread `include_forecast` and `premium_requests_limit` into the formatter/export call sites, not into `build_report_data()` or cache params:
- `body = email_report.format_report_email(data, premium_requests_limit=...)`
- `html_body = email_report.format_html_report(data, premium_requests_limit=...)`
- Any text export path that formats from the dict should receive the same kwarg.

This is important because `github-usage email-report --dry-run`, `--export`, and cached email runs all reuse the same fetched dict.

Make the option-precedence contract explicit and keep it the same for cached and uncached email runs:
- CLI flags win over everything else.
- Active profile values from `config.toml` are next.
- `DEFAULT_EMAIL_REPORT` values are the fallback.
- Cached report payloads never supply or override forecast presentation options.

Concretely:
- `include_forecast` defaults to `True` unless disabled by CLI or profile.
- `premium_requests_limit` defaults to `None` unless set by CLI or profile.
- Loading a cached report changes only the fetched usage data source; it must not change which forecast options are applied during rendering/export.

### GUI legacy report path (`gui_backend.py`)

The GUI also loads cached legacy report dicts. If the TUI/detail rows show forecast information, they must derive it fresh from the cached current values rather than depending on a stored `forecast` key.

### TUI / wizard

Update the TUI profile editor and wizard to surface the new options:
- `gui/views/setup_profiles_panel.py`: add an "Include forecast" checkbox bound to `include_forecast`.
- `gui/wizard/setup_wizard_flow.py` and `gui/wizard/setup_wizard_screen.py`: add `include_forecast` to the wizard data class and UI.
- `gui/views/schedules_view.py`: if the schedule view exposes section toggles, include `include_forecast`.

### Workflow template

Update `.github/workflows/email-report.yml.template`:
- Add `include_forecast` workflow input with default `__INCLUDE_FORECAST_DEFAULT__`.
- Add the corresponding shell block to append `--include-forecast` when the input is true.
- Update `setup_workflow.py`:
  - Add `"include_forecast": True` to `DEFAULT_WORKFLOW_CONFIG`.
  - Add `text = text.replace("__INCLUDE_FORECAST_DEFAULT__", bval(ga["include_forecast"]))` in `render_workflow()`.
- Regenerate `.github/workflows/email-report.yml` so it stays in sync with the template.

### Example config

Update `.github-usage/config.example.toml` to show `include_forecast` and `premium_requests_limit` under `[email_report]`.

### README

Document the new `--include-forecast`, `--no-include-forecast`, and `--premium-requests-limit` flags in the email-report CLI section.

---

## Phase 5 — Exports

Because the forecast is render-time derived, exporters must compute it explicitly instead of assuming a stored `report["forecast"]` key exists.

- **`export_json.py`:** JSON exports **will include** a derived `forecast` block. Compute it at write time by enriching a shallow copy of the report so the exported JSON reflects the export date without mutating the source dict or cache snapshot. Add a test that verifies the original input dict is unchanged and the emitted JSON contains `forecast`.
- **`export_text.py`:** Text exports delegate to `email_report.format_report_email`, so the forecast appears once the text formatter accepts `premium_requests_limit`. Update the write path if needed so exporter callers can pass formatter options through.
- **`export_csv.py`:** Add a dedicated "Forecast" section after "Monthly Costs". Flatten the nested dict into rows: `metric`, `current`, `projected`, `limit`, `run_out_day`. Limit should be blank when `None`; run-out day should be blank when `None`.
- **`export_xlsx.py`:** Add a "Forecast" sheet with the same columns as CSV.
- **`export_pdf.py`:** Add a "Forecast" page with label/value rows for each metric, including current, projected, limit, and run-out day.

Update existing export tests to assert exporters compute the forecast from current usage fields even when the input report dict has no `forecast` key.

---

## Phase 6 — Tests

Create `tests/test_forecast.py` for the pure computation:
- `test_compute_forecast_mid_month()` — day 15 of 31, verifies ratio math.
- `test_compute_forecast_first_day()` — day 1 of 31, no run-out when usage is low.
- `test_compute_forecast_run_out()` — usage pace exceeds limit, `run_out_day` is correct.
- `test_compute_forecast_exactly_at_limit()` — projected equals limit, `run_out_day` is the last day of the month.
- `test_compute_forecast_unknown_limit()` — `premium_requests_limit=None`, `run_out_day=None`.
- `test_compute_forecast_last_day()` — day 31 of 31, projected == current.
- `test_compute_forecast_last_day_already_over()` — day 31 of 31 with current > limit, run-out day is earlier.
- `test_compute_forecast_skipped_before_day_3()` — day 1 or 2 returns `None`.
- `test_compute_forecast_invalid_date()` — `day_of_month > days_in_month` returns `None`.
- `test_compute_forecast_zero_current_value()` — current=0.0, no division-by-zero.

Add `tests/test_report_helpers.py` (or extend an existing test file) for:
- `test_days_in_month()` — verifies `calendar.monthrange` behavior, including leap year.
- `test_day_of_month()` — verifies day extraction.

Add `tests/test_report_forecast_data.py` for the report-dict adapter helper:
- Verify current values are read from `actions.minutes`, `actions.storage_avg_mb`, and `copilot.total_requests`.
- Verify missing `actions` / `copilot` sections default to `0.0`.
- Verify default limits of `2000` minutes and `500` MB are used when actions data is absent.
- Verify a provided `premium_requests_limit` is threaded through.
- Verify `reference_date` controls the computed day count so cached reports can be tested deterministically.
- Verify the helper returns `None` when all current values are `0.0`.

Retain `tests/test_report_data.py` and `tests/test_legacy_report_data.py` coverage only for fetched report shape; do **not** assert a stored `forecast` key there.

Add rendering tests:
- `tests/test_email_report.py` or split text/HTML formatter tests:
  - forecast section present when underlying usage exists
  - forecast section absent when day-of-month < 3
  - cached/stale `generated_at` does not affect the forecast date when `reference_date` is supplied
  - `premium_requests_limit` controls whether the premium run-out column is shown
- `tests/test_legacy_terminal.py` (or existing legacy terminal tests): verify `render_forecast` output includes projected minutes and run-out day.
- `tests/test_legacy_report_summary.py` (or existing summary tests): verify projected rows appear in `legacy_report_detail_rows()`.
- Add one cache-oriented integration test for each main consumer path that matters:
  - cached email report still renders a forecast for the current mocked date
  - cached legacy report still renders a forecast for the current mocked date

Add config/CLI/workflow tests:
- `tests/test_setup_config.py`: verify `DEFAULT_EMAIL_REPORT` includes `include_forecast` and `premium_requests_limit`; verify `_email_flags_from_dict` emits `--include-forecast` and `--premium-requests-limit`.
- `tests/test_cli_parsers.py`: verify the new email parser flags parse correctly.
- `tests/test_cli.py`: verify CLI/profile/default precedence for `include_forecast` and `premium_requests_limit`, including the cached email path passing the resolved `premium_requests_limit` through to the formatter without forcing a refetch.
- `tests/test_setup_workflow.py`: verify the rendered workflow contains the `include_forecast` input and shell block.

Add export round-trip tests for each exporter as noted in Phase 5.

---

## Phase 7 — TO_DO.md cleanup and changelog

- Remove the Deferred item: "Add clearly labeled end-of-month spend projections based on elapsed days in the billing period." — this plan supersedes it.
- Mark the new TO_DO item as in-progress or link to this plan.
- Update `CHANGELOG.md` under `[Unreleased] > Added` when implementation is complete.

When implementation and verification pass, set the status banner to `> **Status:** COMPLETE` and move this plan to `docs/superpowers/plans/archived/` in the same change set.

---

## Verification

Run the standard verification commands after implementation:

- `scripts/check` — default verification (lint, type checks, tests, sizes).
- `scripts/smoke` — after CLI entrypoint/parser changes.
- `scripts/docs-check` — after README, docs, CLI help, and workflow template changes.

---

## Resolved decisions

1. **Premium request limits** — Resolved as option (a): fully configurable in the profile, default `None` = don't show run-out. GitHub doesn't expose these via the billing API.
2. **Storage projection basis** — Resolved: extrapolate `storage_avg_mb` directly, since it's the user-facing number and is already rate-normalized.
3. **Default on/off** — Resolved: `include_forecast` defaults to `True`.
4. **Build-time vs render-time forecast** — Resolved: compute at render/export time from current usage values already present in the report dict. Cached report snapshots are reused across CLI, GUI, exports, and dry-run email output, so storing a date-sensitive forecast in the cache would be stale by design.
5. **Run-out when projected equals limit** — Resolved: report `run_out_day` when `projected >= limit`, so exactly hitting the limit on the last day is still surfaced.
6. **JSON export contract** — Resolved: JSON exports include a derived `forecast` block computed at export time from current report values.
7. **Forecast option precedence** — Resolved: CLI flags override active profile values, which override `DEFAULT_EMAIL_REPORT`; cached report payloads never override forecast presentation options.

---

## Revision notes

- Reviewed 2026-07-04.
- Converted top-of-file "NEEDS REVIEW" to canonical status banner.
- Replaced brittle line-number references with function/section anchors.
- Added run-out behavior for `projected >= limit` and last-day edge cases.
- Reworked the design from build-time cached forecast storage to render/export-time derivation so cached reports do not show stale projections.
- Removed the incorrect assumption that scheduled email always builds and sends in the same uncached pass; the CLI can reuse cached email data for dry-runs, sends, and exports.
- Added explicit guidance to keep forecast-specific options out of cache-key parameters because they affect presentation, not fetched data.
- Locked down the JSON export behavior so implementation and tests do not have to guess whether derived forecast data belongs in exported JSON.
- Locked down CLI/profile/default precedence for forecast presentation options so cached and uncached email runs behave identically.
- Moved section-related `compute_forecast` tests to the correct data-layer test files.
- Added missing coverage: `report_helpers` date helpers, legacy terminal rendering, TUI summary rows, CLI/config/workflow tests, and export formatters.
- Added explicit export handling for CSV, XLSX, and PDF (they do not automatically include nested dicts).
- Added TUI, workflow template, example config, README, and verification commands that were absent from the original draft.
