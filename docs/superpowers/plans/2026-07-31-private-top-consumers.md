> **Status:** IN PROGRESS

> Line numbers are accurate as of 2026-07-31; relocate by anchor (function name + dict key) if they drift.
>
> **Terminology:** user-facing name is **local full report** (CLI/TUI). Code modules still use `legacy_*` until the rename tracked in `TO_DO.md`.
>
> **Related:** OS-from-runs retirement → [`2026-07-31-actions-os-from-runs-honesty.md`](./2026-07-31-actions-os-from-runs-honesty.md). Opt-in deep analysis → [`2026-07-31-opt-in-deep-run-analysis.md`](./2026-07-31-opt-in-deep-run-analysis.md) (tracked on `TO_DO.md`; not in this plan’s implementation order).
>
> **Reviewed:** 2026-07-31 — Assessment `tmp/assessment-2026-07-31-2330.md` adopted (see Constraints / Phase 1a / 4a / 4b–c / 6d). Phase 9 deep analysis split out to its own plan; Phase 8 deferrals tracked on `TO_DO.md`.
> **Reviewed:** 2026-07-31 — Assessment `tmp/assessment-2026-07-31-2346.md` adopted: Phase 0b FakeAPI caveat — unwrap tests must use `GitHubAPI` + mocked `request_raw`, not `FakeAPI.get_all_pages`.
>
> **Implementation log:** Phase 0 complete 2026-08-01 (`get_all_pages` unwrap + tests + `workflow_name` hygiene).

# Private-Only Top Consumers in Reports

## Problem

The report already emphasizes **private** usage for the free-tier math (Limits Summary, utilization bars, forecast — archived `2026-07-30-private-usage-emphasis`). But the **top-consumer rankings** are still mixed-visibility:

- `render_actions_top_consumers` (`report_actions.py:268`) ranks top 10 by Actions minutes across public **and** private; a private repo ranked 6th+ is invisible. On the current account, public repos dominate (`MyPySkinDose` 2,730 min, `DICOMViewerV3` 1,516 min); top private `WeekendDigestFreeAPIs` (1,126 min) only appears mid-list tagged `[private]`.
- `_print_top_consumers` (`report_summary.py:176`) ranks top 5 by minutes and top 5 by cost, all visibilities. No top-by-storage list in the consumers section.
- `_consumer_findings` (`report_summary_insights.py:159`) reports biggest consumer / cost / storage from combined rankings only.
- Email (`email_report_text.py:126`, `email_report_html.py:184`) only has `by_minutes` / `by_cost`; visibility grouping only surfaces private repos that already made the combined top-5.
- TUI detail rows (`legacy_report_summary.py:_repo_rows`) show only combined `by_minutes` / `by_cost`.

Result: the quota-relevant signal — **which private repos burn the 2,000-minute / 500 MB allowance** — is buried. Recommendation text already says "review the private top-consumers below," but no private-only list exists.

**User goal:** top consumers of Actions **minutes** and **storage** among **private** repos (local + email), keeping overall rankings; plus a **by-workflow** minutes breakdown for the top private minutes consumer.

## Approach

Compute private-only rankings at the **data layer** (per-repo `visibility` already known) and store them on `repo_consumers` (shared by email and legacy builders). Renderers read the new keys; existing overall lists stay.

```python
{
    "by_minutes": [...],           # existing — overall top N by minutes
    "by_cost": [...],              # existing — overall top N by gross cost
    "by_storage": [...],           # NEW — overall top N by storage_avg_mb
    "by_minutes_private": [...],   # NEW — top N private/internal by minutes
    "by_storage_private": [...],   # NEW — top N private/internal by storage_avg_mb
}
```

- **Private** = `repo_visibility(row) in ("private", "internal")` (matches `usage_split.split_rows_by_visibility`).
- **Storage** = billed Actions storage as average MB (`storage_avg_mb`). Artifact scan stays as-is (already groups by visibility); only the billed ranking is new.
- **Scope:** local report (terminal + TUI) and email (text + HTML). Exports pick up new keys via JSON; dedicated columns/sheets deferred (Phase 8). No new CLI flags or config keys.

## Constraints (from reviews)

1. **Do not change the `repo_data` 6-tuple** `(full, minutes, storage_gb_hours, avg_mb, gross, sku)` — unpacked at `report_summary.py:190`/`:201` and indexed in insights. Filter dict rows in renderers; optional `visibility_by_repo` on `show_*` shims only (no active callers in `src/` today).
2. **Redundancy guard:** skip a private-only list when the combined list for that metric is entirely private, or when the private list is empty.
3. **Zero-division:** every `% of private minutes` uses `x / y * 100.0 if y and y > 0 else 0.0`.
4. **Tie-breaking:** all **new** rankings sort `(-metric, repo)` ascending. Existing combined-list sorts stay unchanged.
5. **Line budgets:** `email_report_html.py` ~468, `report_summary_insights.py` ~449, `legacy_report_summary.py` ~435; `report_actions.py` ~301 and grows with Phase 4 — extract workflow helpers before ~400. HTML table helpers → mandatory `_email_report_html_tables.py`.
6. **No public per-workflow billable minutes.** Live runs carry no `billable`; `/runs/{id}/timing` usage endpoints retired 2025-04-01. Phase 4 estimates from run start→end wall-clock and labels it as such.
7. **`get_all_pages` discards object-shaped responses** (`api.py:127-130`) — Phase 0 prerequisite. Restores artifact scan; does **not** restore OS billable minutes (still no `billable` on runs).
8. **Quota estimates must bump the numeric** `estimated_incremental_requests` (guards read that field, never `notes`).
9. **Shared redundancy helper:** one pure `private_list_is_redundant(combined, private) -> bool` used by all renderers (constraint 2), to avoid drift. Redundant only when `private` is empty **or** (every row in `combined` is private/internal **and** `len(private) <= len(combined)`). Without the length guard, a Top-5-all-private combined list would incorrectly suppress a longer private Top-10.
10. **ISO timestamps:** `_parse_iso` must return timezone-consistent datetimes (prefer reuse of `storage._parse_iso_datetime`: `Z` → `+00:00`, naive → UTC) so `(end - start)` never mixes aware/naive.

---

## Phase 0 — Prerequisite: paging for object-shaped responses (`api.py`)

**Done:** 2026-08-01 — Unwrapped `_COLLECTION_KEYS` (`workflow_runs`, `artifacts`, `workflows`) in `get_all_pages`; regression tests use real `GitHubAPI` + mocked `request_raw` (not FakeAPI); `billing.py` `workflow_name` hygiene. No deviations.

`get_all_pages` only appends array responses; dict responses without `"message"` hit `break` and return `[]`. Affected endpoints:

| Endpoint | Shape | Caller impact today |
|---|---|---|
| `.../actions/runs` | `{total_count, workflow_runs}` | `get_actions_from_runs` → `(0.0, zeros, {})`; Phase 4 would see no runs |
| `.../actions/artifacts` | `{total_count, artifacts}` | artifact scan / `get_artifact_storage_details` empty |
| `.../actions/workflows` | `{total_count, workflows}` | Phase 4 canonical names empty |

### 0a. Fix `get_all_pages`

- [x] Unwrap recognized collection keys and keep `rel="next"` pagination. Guard against null collections:

```python
_COLLECTION_KEYS = ("workflow_runs", "artifacts", "workflows")
# if dict with "message": raise
# elif dict:
#     for key in _COLLECTION_KEYS:
#         if key in result and isinstance(result[key], list):
#             result = result[key]
#             break
#     else:
#         break  # unknown dict shape — current behavior
```

### 0b. Regression tests

- [x] `get_all_pages` unwraps `{"workflow_runs": [...]}` and follows `rel="next"`; unknown dict shape still breaks; `{"workflow_runs": null}` does not raise.
- [x] `get_actions_from_runs` against an object-shaped runs response returns runs into the loop (proves unwrap). Minutes/OS may still be zero when fixtures omit `billable` — that is expected against the live API.
- [x] Artifact collectors populate rows from object-shaped artifacts responses.

**FakeAPI caveat (assessment 2346):** `tests/_fakes.py` `FakeAPI.get_all_pages` returns the preconfigured list from `pages_responses` and **does not** exercise `GitHubAPI.get_all_pages` unwrap logic. Phase 0b unwrap/pagination regressions must use a real `GitHubAPI("fake-token")` with `mock.patch.object(api, "request_raw", ...)` returning `Response` bodies — same pattern as `tests/test_api.py:114` (`test_get_all_pages_uses_link_header`). Do **not** feed object-shaped dicts through `FakeAPI.get_all_pages` and claim the unwrap is covered. Downstream tests that only use `FakeAPI.pages_responses` may still assert collector behavior, but they are not a substitute for the real unwrap unit test.

### 0c. What Phase 0 does and does not restore

- [x] **Restores:** artifact scan / `get_artifact_storage_details`; runs list access for Phase 4 estimation; workflows list for names.
- [x] **Does not restore:** "Actions Compute by OS" with real values. `get_actions_from_runs` still reads `run["billable"]`, which is absent live → OS section stays empty until a different data source exists. Fix `billing.py:166` to `run.get("workflow_name") or "Unknown"` as hygiene when the loop does run.

---

## Phase 1 — Data: shared ranking helper + new `repo_consumers` keys

### 1a. New module `src/github_usage/repo_consumers.py` (~120 lines)

```python
def build_consumer_rankings(rows: list[dict], *, limit: int) -> dict:
    """Rank consumer rows by minutes, gross, and storage — overall and private-only.

    Each row needs ``repo``, ``minutes``, ``gross``, ``storage_avg_mb``, ``visibility``.
    ``"internal"`` folds into private. Returns all five ranking keys (empty lists ok).
    Rows are not mutated. Sort: ``(-metric, repo)``.
    """

def private_list_is_redundant(combined: list, private: list) -> bool:
    """True when ``private`` is empty, or every row in ``combined`` is
    private/internal **and** ``len(private) <= len(combined)``.

    The length guard prevents skipping a longer private Top-N when the
    combined list is a shorter all-private Top-M (e.g. Top 5 vs Top 10).
    Renderers skip the private-only list when this returns True (constraint 2).
    """
```

Also export `private_list_is_redundant` for Phase 2/3/5 renderers. Call sites should pass lists sliced to the **same display limits** they render (matched 5/5 or 10/10); the helper still guards mismatches.
### 1b. `get_repo_consumers` (`report_optional.py:23`) — email path

Replace inline sort/slice with `build_consumer_rankings(rows, limit=limit)`; spread into returned dict. Keep `scanned_repo_count`, `max_repos`, `truncated`, `errors`, `by_visibility`. No new API calls.

### 1c. `derive_repo_consumers` (`legacy_report_data.py:41`) — legacy path

Same: build row shape, call helper, spread. Keep `errors` passthrough.

### 1d. Cache

Bump `CACHE_VERSION` (`report_cache.py:27`) from `2` → `3`. Update `tests/test_report_optional.py:244` assertion to `3`.

---

## Phase 2 — Local terminal report

### 2a. `render_actions_top_consumers` (`report_actions.py:268`)

Keep combined "Top 10 Repos by Actions Minutes". After it, when private rows exist and are not redundant (`private_list_is_redundant`):

```
  Top 10 Private Repos by Actions Minutes
    {minutes:>8.1f} min | {avg_mb:>8.1f} MB | {full}
```

Filter dict rows in place (`visibility` already present). Shim `show_actions_top_consumers`: optional `visibility_by_repo`; `None` → current output.

### 2b. `_print_top_consumers` (`report_summary.py:176`)

Add optional `repo_consumers: dict | None = None` and `private_minutes: float | None = None`. `render_final_summary_from_data` passes `data.get("repo_consumers")` and `actions.get("private_minutes")`.

When keys non-empty and not redundant (`private_list_is_redundant`):

- **"Private Actions Minutes (top 5 repos):"** — `by_minutes_private`; `% of private minutes` uses EC3 guard on `private_minutes`.
- **"Actions Storage (top 5 repos, billed):"** — `by_storage`.
- **"Private Actions Storage (top 5 repos, billed):"** — `by_storage_private`.

### 2c. `_print_storage_breakdown` (`report_summary.py:242`)

Keep combined scan list. Add **"Top 10 Private Repos by Storage (scan)"** when private rows exist and not redundant (`private_list_is_redundant`). Rows already carry `visibility` (`storage.py:181`).

### 2d. Findings (`report_summary_insights._consumer_findings`, `:159`)

When private rows exist and not redundant (`private_list_is_redundant`):

- "Biggest private Actions consumer: `repo [private]` at N min (X% of private minutes)."
- "Biggest private storage consumer: `repo [private]` (size_str)." — from billed `by_storage_private`.

### 2e. Recommendations (`_collect_recommendations`, `:395`)

`_concentration_recommendation` (`:321`): add private-only variant when private minutes exist — "Top 2 private repos (X, Y) consume Z% of private Actions minutes — consider self-hosted runners." Keep combined variant. Minute-recommendation wording already points at private top-consumers; no change.

---

## Phase 3 — Email report

### 3a. `email_report_text.py:_format_consumers_section` (`:126`)

After combined lists, when keys non-empty and not redundant (`private_list_is_redundant`):

- "Top Repositories by Actions Storage (all)" — `by_storage`
- "Top Private Repositories by Actions Minutes" — `by_minutes_private`
- "Top Private Repositories by Actions Storage" — `by_storage_private`

Reuse `_grouped_list` / `_annotated_repo_name`. Private lists are flat (no visibility grouping). Keep `by_visibility` summary unchanged.

### 3b. `email_report_html.py:_format_html_consumers_section` (`:184`)

Mirror 3a via `_html_grouped_table`. **Mandatory:** extract table helpers (and Phase 4e workflow table) into `_email_report_html_tables.py` in the same change set.

---

## Phase 4 — Workflow breakdown for the top private-repo consumer (estimated minutes)

Live runs expose **no** billable minutes. Estimate from `updated_at − run_started_at` (fallback `created_at`), current calendar month. Label every section as an approximation.

**Why estimates diverge from billed totals (live check):** the verification estimate used raw fractional wall-clock (`total_seconds() / 60`) — it did **not** round each run up to the nearest minute. GitHub bills per **job**, rounding each job up to a whole minute, then applying OS multipliers (Linux 1× / Windows 2× / macOS 10×). Run-level wall-clock also undercounts parallel jobs (one run's elapsed time vs sum of job minutes). So ~486 est-min vs ~1,126 billed for the same repo is expected — do not try to "fix" the estimate to match billed. Caveat text must say the total **will not match** the billed repo figure.

### 4a. Module + data collector

Put Phase 4 helpers in a new small module `src/github_usage/report_workflow_minutes.py` (keeps `report_actions.py` under ~400). Re-export `fetch_workflow_minutes` / `render_workflow_breakdown` from `report_actions.py` only if call sites already import from there; otherwise import the new module from builders/renderers directly.

Shared runs cache — **must** be plumbed into Phase 4 (and later the opt-in deep-analysis plan when enabled); never `cache or {}`:

```python
def _fetch_runs_cached(api, owner: str, name: str, created_range: str, *, cache: dict) -> list:
    """Return workflow runs for (owner, name, created_range), memoized in ``cache``.

    Callers must pass one shared ``cache`` dict from the report builder.
    Do not use ``cache or {}`` — a fresh dict defeats memoization.
    """
    key = (owner, name, created_range)
    if key not in cache:
        cache[key] = api.get_all_pages(
            f"/repos/{owner}/{name}/actions/runs",
            {"created": created_range, "per_page": 100},
        )
    return cache[key]
```

`fetch_workflow_minutes` receives a builder-owned `runs_cache: dict` (always a real dict, never `None` at the builder boundary). The opt-in deep-analysis plan reuses the same cache key convention when both run.

```python
def fetch_workflow_minutes(api, owner: str, name: str, *, runs_cache: dict) -> dict | None:
    """Per-workflow estimated Actions minutes from run start→end times (current month).
    ``None`` when no usable completed runs.

    Computes ``created_range`` internally (same calendar-month logic as
    ``get_actions_from_runs``); do not leave it undefined in the call site.
    """
    first_day = date.today().replace(day=1)
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    created_range = f"{first_day.isoformat()}..{last_day.isoformat()}"
    runs = _fetch_runs_cached(api, owner, name, created_range, cache=runs_cache)
    wf_names = _workflow_name_map(api, owner, name)  # soft-fails to {}
    by_wf: dict = {}
    for run in runs:
        if run.get("status") != "completed":
            continue
        end = _parse_iso(run.get("updated_at"))
        start = _parse_iso(run.get("run_started_at")) or _parse_iso(run.get("created_at"))
        if not start or not end or end <= start:
            continue
        wf_id = run.get("workflow_id") or run.get("name") or "unknown"
        entry = by_wf.setdefault(wf_id, {"name": None, "runs": 0, "minutes": 0.0})
        entry["name"] = (
            entry["name"]
            or wf_names.get(wf_id)
            or run.get("name")
            or (f"Workflow #{wf_id}" if isinstance(wf_id, int) else "Unknown Workflow")
        )
        entry["runs"] += 1
        # Fractional wall-clock — do NOT ceil to whole minutes (billing rounds per job, not per run).
        entry["minutes"] += (end - start).total_seconds() / 60
    if not by_wf:
        return None
    ranked = sorted(by_wf.values(), key=lambda e: (-e["minutes"], e["name"] or ""))
    return {
        "repo": f"{owner}/{name}",
        "total_minutes": round(sum(e["minutes"] for e in ranked), 1),
        "by_workflow": ranked,
    }
```

Notes:

- **Key on `workflow_id`** (stable); fall back to `run.name` / `"unknown"` so deleted/null IDs do not collide as `None`.
- **Name fallback** is always a non-`None` string (avoids `{None:<42}` in renderers).
- **Only `status == "completed"`** — in-progress/queued runs update `updated_at` while running and would inflate estimates; `end <= start` alone is not enough.
- **`_workflow_name_map` soft-fails:** wrap the workflows GET in `try/except`, return `{}` on failure so breakdown falls back to run names.
- **`_parse_iso`:** reuse or match `storage._parse_iso_datetime` — always timezone-aware UTC (`Z` → `+00:00`, naive → UTC). Missing/bad timestamps skipped; never raise on subtract of mixed aware/naive.
- Sort `(-minutes, name)` (constraint 4).
- Do not reuse `get_actions_from_runs`' `workflow_minutes` (keys on null `workflow_name`). Hygiene-fix `billing.py:166` anyway.
- Builder creates `runs_cache: dict = {}` once and passes it into Phase 4 (and deep analysis when that separate plan is wired).
### 4b. Legacy wiring — `build_legacy_report_data` (`legacy_report_data.py:206`)

After `repo_consumers`, if `by_minutes_private` non-empty and `[0]["minutes"] > 0`, parse `owner/name` (`if "/" in repo:`), call `fetch_workflow_minutes`, store `report["workflow_breakdown"]` (default `None`).

Quota: in `estimate_legacy_api_request_count` (`:136`), `estimated += 10` unconditionally when the workflow breakdown path is enabled (covers ≥1 runs page + 1 workflows page with headroom; filtered runs lists cap ~1000 → worst ~11). Note real cost is `ceil(runs/100) + 1` — the bump is a **safe floor for the guard**, not an exact counter (estimate runs before the fetch, so `total_count` is not free).

### 4c. Email wiring — `build_report_data` (`report_data.py:294`)

When `include_consumers` and top private has `minutes > 0`, fetch and store `workflow_breakdown` (default `None` in skeleton at `:335`).

Quota: in `estimate_api_request_count` (`report_optional.py:119`), `estimated += 10` when `include_consumers` is set (same safe headroom as 4b), plus pagination note.

### 4d. Local renderer — `report_workflow_minutes.py`

`render_workflow_breakdown(breakdown, *, limit=10)` called from `render_legacy_report` after OS breakdown:

```
  Minutes by Workflow — Top Private Repo (owner/repo)
  (estimated from run wall-clock; not billable — will not match billed repo total)
  ──────────────────────────────────────────────────────────────────────────
    Total (est): N.N min
    {workflow:<42} {minutes:>8.1f} min  ({pct:5.1f}%)
```

`pct` uses EC3 guard. No-op when falsy. Caveat is a one-line sub-header under the heading. Skip legacy `show_*` path (no active callers).

### 4e. Email renderers

- Text: `_format_workflow_breakdown_section` — top 5 workflows; caveat sub-header; register after consumers in `_SECTION_FORMATTERS`.
- HTML: small table (workflow, runs, minutes, %); helpers in `_email_report_html_tables.py`.

### 4f. Approximation caveat

Every "Minutes by Workflow" section:

`(estimated from run wall-clock; not billable — will not match billed repo total)`

Wall-clock over the current month — not GitHub billable. Billing meters **per job** (each job rounded up to a whole minute, then OS multipliers); this estimate is **per run** elapsed time with fractional minutes and no multipliers. Parallel jobs and short-job rounding make billed totals systematically higher. Do not ceil-per-run as a "fix" — that still would not match job-level billing.

---

## Phase 5 — TUI detail rows (`legacy_report_summary.py`)

In `_repo_rows` (`:295`), after combined sections (skip when redundant via `private_list_is_redundant`):

- `_section("Top private repos by Actions minutes")` — `by_minutes_private`
- `_section("Top private repos by Actions storage (billed)")` — `by_storage_private`
- `_section("Top repos by Actions storage (billed)")` — `by_storage` (**include** — matches terminal/email overall storage list)

Cap at 10 rows each. Watch ~480-line budget (currently ~435).

---

## Phase 6 — Tests

### 6a. `tests/test_repo_consumers.py`

- Ranks by minutes / cost / storage; `by_storage` uses `storage_avg_mb`
- Internal folds into private; public excluded from private keys
- Empty private → empty lists (keys present); limit applies per ranking
- Deterministic tie-break on repo name

### 6b. Builders

- `get_repo_consumers` / `derive_repo_consumers` return new keys with correct membership; `CACHE_VERSION == 3`

### 6c. Local renderers

- Private top list in `render_actions_top_consumers`; tuple contract unchanged (`test_report_actions.py` `show_actions_per_repo`)
- `_print_top_consumers` private + storage lists; redundancy + zero-division guards
- Insights: private findings + concentration recommendation
- TUI `_repo_rows` private sections

### 6d. Workflow breakdown + Phase 0

- [x] Object-shaped runs → `get_actions_from_runs` enters the loop; `workflow_name: null` → `"Unknown"` (Phase 0; Done 2026-08-01)
- `fetch_workflow_minutes`: aggregates by `workflow_id`; skips non-`completed` and zero-duration; soft-fail name map → `run.name`; sorted desc; renderer includes caveat; fractional minutes (no ceil)
- **Timezone math:** GitHub `...Z` timestamps and offset forms subtract cleanly (no aware/naive `TypeError`)
- **Redundancy helper:** all-private combined Top-M does **not** suppress a longer private Top-N (`len(private) > len(combined)`)
- Shared `runs_cache`: second fetch for the same `(owner, name, range)` is a cache hit within one report build
- Builders store `workflow_breakdown` only when top private has `minutes > 0`

### 6e. Email

- Text + HTML: private minutes/storage, overall storage, workflow block when present; absent keys → unchanged output

---

## Phase 7 — Documentation & changelog

### 7a. README

Consumers sections include private-only top lists for Actions minutes and storage; storage ranked by billed avg MB; workflow breakdown for top private minutes consumer (estimated from run wall-clock — not billable; will not match billed repo total).

### 7b. CHANGELOG.md — `[Unreleased]`

- **Added:** private-repo top consumers (minutes + storage) alongside overall rankings; overall top-by-storage list.
- **Added:** minutes-by-workflow for top private consumer (estimated from run wall-clock; not billable — will not match billed totals).
- **Fixed:** REST paging unwraps object-shaped responses (`workflow_runs`, `artifacts`, `workflows`), restoring the artifact-storage scan. (OS breakdown remains empty against the live API — no `billable` on runs.)

### 7c. TO_DO.md

Move Phase 8 deferrals onto `TO_DO.md` (do not keep a long deferred list here). No other completed TO_DO items to remove for this plan’s core scope.

---

## Phase 8 — Deferred (tracked on TO_DO.md)

Out of scope for this plan’s COMPLETE criteria. Tracked under **Actions / Local Full Report** in `TO_DO.md`:

- CSV/XLSX/PDF columns/sheets for private rankings and workflow breakdown (`TODO` comments at export `repo_consumers` readers).
- Private-only artifact-scan ranking.
- Workflow breakdown for more than the single top private repo.
- Opt-in deep run analysis → [`2026-07-31-opt-in-deep-run-analysis.md`](./2026-07-31-opt-in-deep-run-analysis.md).
- OS-from-runs honesty → [`2026-07-31-actions-os-from-runs-honesty.md`](./2026-07-31-actions-os-from-runs-honesty.md).

---

## Resolved decisions

1. Private = private + internal.
2. Storage ranking = billed avg MB; scan view stays separate and labeled "(scan)".
3. Rankings on `repo_consumers` via shared pure helper; overall lists kept.
4. No new CLI/config for Phases 0–7; cache version → 3. (Deep-analysis flags live in the separate opt-in plan.)
5. `repo_data` 6-tuple unchanged.
6. Redundancy / zero-division / deterministic-tie constraints as above; `private_list_is_redundant` requires `len(private) <= len(combined)` when combined is all-private.
7. Workflow minutes estimated from run wall-clock for top private consumer only (top 10 terminal / top 5 email); always labeled as estimate that **will not match** billed totals. `_parse_iso` is timezone-safe (UTC-aware).
8. Phase 0 ships with this work: restores artifacts + enables Phase 4; does **not** claim to restore OS billable minutes.
9. Phase 4 lives in `report_workflow_minutes.py`; builder-owned `runs_cache` (never `cache or {}`) — shared later with the opt-in deep-analysis plan when both run. Quota bump for Phase 4 is a **safe constant (`+= 10`)**, not exact `ceil(runs/100)+1`.
10. TUI includes overall billed storage section (not optional).

---

## Implementation order

1. ~~Phase 0 (paging + tests)~~ **Done 2026-08-01**
2. Phase 1 + 6a/6b
3. Phase 2 + 6c
4. Phase 3 + 6e
5. Phase 4 + 6d
6. Phase 5 + TUI tests
7. Phase 7 + seed Phase 8 items onto `TO_DO.md` (if not already)
8. `scripts/check`, `scripts/smoke`, `scripts/docs-check` → mark COMPLETE and archive

---

## Verification

- `scripts/check` — lint, types, tests, sizes (watch HTML/insights/TUI/`report_actions.py` line budgets; new `report_workflow_minutes.py` stays small).
- `scripts/smoke` — CLI entrypoints unchanged (no deep-analysis flags in this plan).
- `scripts/docs-check` — README + changelog.
- `./start.sh report` — private minutes top list (led by `WeekendDigestFreeAPIs` ~1,126 min, then `SpotiBye`, `PSDCalcRework`, `Notes_and_Ideas`, `SpotiByeMatcher`); summary private minutes + storage lists; overall lists still render; "Minutes by Workflow — Top Private Repo" with estimate caveat for `WeekendDigestFreeAPIs` (est total expected well below billed — do not expect parity). Artifact scan should populate. OS-from-runs section behavior deferred to honesty plan (may still be empty until that ships).
- `./start.sh email-report` (or unit tests) — private lists + workflow block in text and HTML (`include_consumers` enabled).
