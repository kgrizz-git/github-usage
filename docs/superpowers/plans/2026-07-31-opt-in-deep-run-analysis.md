> **Status:** IN PROGRESS

> Line numbers / anchors may drift; prefer function names. Depends on [`2026-07-31-private-top-consumers.md`](./2026-07-31-private-top-consumers.md) Phase 0 (paging unwrap) and ideally Phase 4 (`runs_cache` / wall-clock breakdown) so deep analysis can share the runs list.
>
> **Terminology:** user-facing name is **local full report** (CLI/TUI).
>
> **Split from:** formerly Phase 9 of private-top-consumers (2026-07-31).
>
> **Implementation log:** (none yet)

# Opt-in Monthly Deep Run Analysis

## Problem

Private-top-consumers Phase 4 adds a **cheap** wall-clock-by-workflow estimate (always-on with consumers, labeled approximate). Users also want an optional **closer-to-billable** analysis: per-job ceil-to-minute + OS multipliers for the top private repo by **gross** Actions cost (minutes cost before discount) — expensive (one jobs call per run), so default off and preferably once per calendar month.

## Approach

Opt-in `--deep-run-analysis` on the local full report:

1. Rank top **private/internal** repo by **`gross`** (fallback **`minutes`**).
2. After Phase 0 unwrap, list current-month runs; fetch `GET .../runs/{id}/jobs` per run (cap e.g. `max_runs=200`).
3. Approximate: ceil each job duration to whole minutes × OS multipliers from labels; honest caveats.
4. Calendar-month cache with visible mid-month staleness caveat; `--force-deep-run-analysis` refreshes.
5. Email / export / multi-repo deferred (see TO_DO.md).

## Constraints

1. Depends on private-top-consumers Phase 0 unwrap; share builder `runs_cache` with Phase 4 when same repo (never `cache or {}`).
2. Default **off**; bump numeric `estimated_incremental_requests` on cache miss only.
3. Do **not** call retired `/runs/{id}/timing` in the product path.
4. Distinct keys/caveats from Phase 4 `workflow_breakdown` — do not overwrite.
5. No secrets / raw private dumps in cache — aggregates + `cached_at` only.

## Resolved decisions

1. Ranking: **gross** among private/internal; **minutes** fallback.
2. Calendar-month cache; intentional mid-month staleness with visible caveat.
3. Local full report only for v1; email deferred.
4. Safe quota bump on miss: `ceil(runs/100) + min(run_count, max_runs)` (or documented cap).

---

## Phase 1 — CLI / config (default off)

- [ ] `--deep-run-analysis` / `--no-deep-run-analysis` on the local full report path.
- [ ] `--force-deep-run-analysis` to bypass calendar-month cache.
- [ ] `deep_run_analysis = false` in profile/`config.toml` defaults (not enabled for email profiles by default).
- [ ] Help text: ranking metric, jobs-per-run quota cost, monthly cache, approximate (ceil-per-job + OS multipliers — not GitHub's retired timing API).

## Phase 2 — Collector — `report_deep_run_analysis.py`

- [ ] `select_top_private_repo` by gross (minutes fallback).
- [ ] List current-month runs (shared `runs_cache` with private-top-consumers Phase 4 when same repo).
- [ ] For each completed run (cap e.g. `max_runs=200`): `GET .../actions/runs/{id}/jobs`.
- [ ] Per job: duration from `started_at`/`completed_at`; `ceil(seconds/60)`; map `labels` → Linux 1× / Windows 2× / macOS 10×; unknown/self-hosted/larger → separate buckets with caveats.
- [ ] Aggregate by workflow and OS/label class; show approx totals **alongside** billed `minutes`/`gross` (expect divergence).
- [ ] Soft-fail on 403/partial; timezone-safe datetime parsing (match `storage._parse_iso_datetime`).

## Phase 3 — Once-a-month cache

- [ ] Cache under gitignored cache dir, keyed by `{user/owner, repo, YYYY-MM, analysis_version}` (include `cached_at`).
- [ ] Cache hit → skip jobs fan-out; `--force-deep-run-analysis` refreshes.
- [ ] **Staleness is intentional:** mid-month hits omit later runs. Visible caveat: `(cached as of YYYY-MM-DD; later runs omitted — use --force-deep-run-analysis to refresh)`.
- [ ] Quota: on miss, bump numeric estimate; on hit, `+0` for the deep path.

## Phase 4 — Render (local full report only for v1)

- [ ] Section title e.g. **"Deep run analysis — top private repo by gross Actions cost (opt-in)"**.
- [ ] Caveats: not official billable; job-sum can exceed run wall-clock; distinct from wall-clock workflow estimate; plus mid-month cache line when serving cache.
- [ ] Flag off → zero extra calls.
- [ ] Wire into `build_legacy_report_data` / `render_legacy_report` only when flag on.

## Phase 5 — Tests / docs

- [ ] Ranking (gross vs minutes fallback); ceil + label mapping; FakeAPI object-shaped runs + jobs; cache hit skips jobs; flag off → no fetch.
- [ ] **Mid-month cache:** seed cache mid-month, add newer runs to FakeAPI, assert stale cache unless force refresh.
- [ ] README + changelog **Added:** opt-in deep run analysis (job-level approx; monthly cache; staleness caveat).
- [ ] `scripts/check`, `scripts/smoke`, `scripts/docs-check`.

## Phase 6 — Deferred (tracked on TO_DO.md)

- Email (text/HTML) deep-analysis section.
- Deep analysis for top-N repos / more than one.
- CSV/XLSX/PDF export columns for deep analysis.
- Auto-enable on first local report of each month without an explicit flag (rejected for v1).

---

## Implementation order

1. After private-top-consumers Phase 0 (+ ideally Phase 4) lands
2. Phases 1–5 of this plan
3. Mark COMPLETE and archive; remove corresponding TO_DO bullet

## Verification

- [ ] Flag off → zero deep calls.
- [ ] Flag on → top private-by-gross analyzed; second run same month hits cache + staleness caveat; `--force-deep-run-analysis` refreshes.
- [ ] Phase 4 wall-clock section (if present) still independent and labeled as estimate.
- [ ] No tokens or generated reports committed.
