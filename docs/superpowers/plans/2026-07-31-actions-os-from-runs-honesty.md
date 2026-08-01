> **Status:** IN PROGRESS

> Line numbers cited below are accurate as of 2026-07-31; relocate by anchor (function / section title / dict key) if they drift.
>
> **Terminology:** user-facing name is **local full report** (CLI/TUI). Code modules still use `legacy_*` until the rename tracked in `TO_DO.md`.
>
> **Coordination:** Paging unwrap (`workflow_runs` / `artifacts` / `workflows`) is **owned by** [`2026-07-31-private-top-consumers.md`](./2026-07-31-private-top-consumers.md) Phase 0. This plan does **not** re-specify that unwrap. Opt-in job-level deep analysis lives as a **late phase of that same plan** (not here).
>
> **Implementation log:** (none yet)

# Retire Dead Actions OS-from-Runs Path

## Problem

`get_actions_from_runs` / the local full report **"Actions Compute by OS (from workflow runs)"** section is dead on the live API.

Confirmed via GitHub docs + live `gh api` on `kgrizz-git/WeekendDigestFreeAPIs` (2026-07-31):

1. `GET .../actions/runs` returns `{total_count, workflow_runs}` — not an array. Current `get_all_pages` discards non-lists → `[]` (fixed by private-top-consumers Phase 0, not this plan).
2. Live Workflow Run objects have **no `billable`** (0/100 sampled). Official list-runs schema has no `billable`.
3. `get_actions_from_runs` (`billing.py`) only aggregates `run["billable"][OS]["millis"]` → still zeros after paging unwrap.
4. `billable` lived on `GET .../runs/{id}/timing`, which is **closing down** (changelog 2025-02-02; transition complete 2025-04-01). Replacement billing usage has **no workflow detail**.
5. Consequence: the section is silently empty (or soft-fails after wasting up to ~10 repo runs-list calls). Name/docs imply a working fallback.

Account-level **GitHub Actions Usage → Per-SKU Breakdown** already shows real runner/OS cost from the billing API — that is the honest signal.

## Approach

**Retire the dead path; never silent empty; no expensive substitute in this plan.**

1. Stop calling `get_actions_from_runs` / `fetch_actions_os_breakdown` on the default local full report path.
2. Omit the "from workflow runs" OS section, **or** replace with one explicit unavailable note that points at Per-SKU Breakdown — **no** extra runs API calls.
3. Do **not** call retired `/runs/{id}/timing` here.
4. Delete or narrowly stub the billable-millis aggregator so it cannot be mistaken for a live fallback. Shared runs fetching for other features belongs in private-top-consumers helpers (`report_workflow_minutes`, deep analysis), not this function.
5. Fix tests that only pass with synthetic array + `billable` shapes so they cannot hide the live contract.
6. Drop `+ os_breakdown` (up to +10) from `estimate_legacy_api_request_count` when the default path no longer fetches runs for OS.

**Out of scope here:** opt-in job-level deep analysis (ceil-per-job + multipliers, monthly cache) — that is a late phase of [`2026-07-31-private-top-consumers.md`](./2026-07-31-private-top-consumers.md).

## Constraints

1. Do not re-implement Phase 0 paging unwrap.
2. Do not change the `repo_data` 6-tuple.
3. No secrets / live tokens in tests.
4. Can ship independently of private-top-consumers deep-analysis phase; may land before or after Phase 0 (Part 1 does not need unwrap).

## Resolved decisions

1. Default OS-from-runs section retired; rely on account SKU breakdown.
2. No timing/jobs fan-out in this plan.
3. Paging unwrap owned by private-top-consumers Phase 0.

---

## Phase 1 — Inventory + stop default fetch

- [ ] List callers of `get_actions_from_runs`, `fetch_actions_os_breakdown`, `show_actions_os_breakdown`, `render_actions_os_breakdown`.
- [ ] Note wiring in `legacy_report_data.py` (`actions_os_breakdown` / `OS_BREAKDOWN_LIMIT`) and `legacy_terminal.py`.
- [ ] Remove `fetch_actions_os_breakdown` from `build_legacy_report_data` (or no-op with `{"available": False}` and **zero** API calls).
- [ ] Update renderer: omit section, or explicit unavailable pointing to Per-SKU Breakdown — title must not say "from workflow runs".
- [ ] Soft message that still burns ~10 repo runs calls is **not** acceptable.

## Phase 2 — `get_actions_from_runs` disposition + quota

- [ ] After private-top-consumers decides shared runs helpers: **delete** billable-millis aggregation, or keep a clearly named dead-compat stub whose docstring states live API has no `billable`.
- [ ] `workflow_name` hygiene (`or "Unknown"`) only if the function survives; otherwise leave to private-top-consumers.
- [ ] Drop `+ os_breakdown` from `estimate_legacy_api_request_count`; update user-facing estimate notes.

## Phase 3 — Tests, docs, changelog

- [ ] Tests: object-shaped runs fixtures where claiming live shape; no-`billable` path asserts honest product behavior (omitted/explicit unavailable).
- [ ] Legacy array+`billable` fixtures only if stub remains, clearly marked non-live.
- [ ] Builder tests do not expect a populated OS-from-runs breakdown.
- [ ] README: remove claims that local full report derives OS from workflow runs; point to SKU breakdown; mention deep analysis lives under private-top-consumers (opt-in late phase).
- [ ] `CHANGELOG.md` `[Unreleased]` **Fixed/Changed:** no longer silently relies on absent run `billable`; OS-from-runs section retired or explicit; quota estimate no longer counts dead fetches.

## Phase 4 — Deferred (other plans)

- Opt-in job-level deep analysis / monthly cache → private-top-consumers late phase.
- Restoring true per-workflow billable if GitHub ever exposes it again.

---

## Implementation order

1. Phase 1 (stop fetch + section honesty)
2. Phase 2 (aggregator + quota)
3. Phase 3 (tests/docs/changelog)
4. `scripts/check` (+ `scripts/docs-check` / `scripts/smoke` as needed) → mark COMPLETE and archive

## Verification

- [ ] Local full report: no "from workflow runs" OS section claiming billable data; no ~10 runs-list calls for OS; Actions SKU breakdown still present.
- [ ] `scripts/check` passes; no tokens or generated reports committed.
