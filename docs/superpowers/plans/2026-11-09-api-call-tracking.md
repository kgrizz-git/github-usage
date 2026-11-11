> **Status:** IN PROGRESS

> Line numbers cited below are accurate as of 2026-11-09; relocate by anchor (function / section title / dict key) if they drift.
>
> **Terminology:** user-facing name is **local full report** (CLI/TUI). Code modules still use `legacy_*` until the rename tracked in `TO_DO.md`.
>
> **Implementation log:** Chunk 1 complete 2026-11-11 — `GitHubAPI` request
> counting (`request_count`, `request_log`, ordered resource buckets) plus
> `get_request_stats()` and unit tests; reviewed APPROVE with minor findings
> folded in (structural sum==total, segment-based actions match, TypedDicts,
> dense zeroed buckets, normalized-path/params/404 tests). Chunk 2 complete
> 2026-11-11 — `report_api_usage.py` shared lines/rows formatters with scope
> labels, rate-limit reference line, and cache-hit message; 9 unit tests at
> 100% file coverage. Chunk 3 complete 2026-11-11 — builder merge with
> per-getter tracking, caller-passed legacy baselines with listing carve-out,
> `annotate_cache_hit` at all three cache sites, `CACHE_VERSION` 4, and
> CountingFakeAPI + builder/helper/cache-hit tests (831 tests green).
> Chunk-3 review (deepseek, APPROVE, no blockers): most findings were already
> satisfied by the implementation (caller-baseline and session tests, fallback
> `other`-bucket, extracted `_merge_legacy_api_estimate`, sorted buckets,
> multi-page `page_counts`, GUI test placement); applied the remainder —
> fallback non-dict/count-combined tests, section-level abort coverage,
> redaction assertions, `_track_repo_calls`/`deltas` typing, legacy docstring.
> Chunk 4 in progress — email text/HTML quota blocks, legacy terminal
> renderer, CSV/XLSX/PDF sections, GUI detail rows; 15 new tests.

# Track GitHub REST API Calls and Report Usage

## Goal

Count the GitHub REST API requests a report actually makes, and surface
actual-vs-estimated usage in every report surface: the email report (text and
HTML), the legacy terminal report, and all file exports (JSON, CSV, XLSX, PDF,
text). Keep the existing pre-fetch estimate for the quota guard.

## Non-goals

- Counting GraphQL calls (this project only uses REST).
- Re-architecting the report data model. The change should extend the existing
  `api_estimate` dict, not introduce a parallel structure.
- Changing the email report's quota-guard behavior.
- Fixing the unrelated "50 of 51" truncation-message lower bound (see
  Related follow-ups).

## Current state

- `GitHubAPI` (`src/github_usage/api.py`) has `request()` and `request_raw()`;
  `get_all_pages()` calls `request_raw()` once per page. Neither counts calls.
- `http_retry.request_with_retries()` (`src/github_usage/http_retry.py`) hides
  retry attempts from the caller.
- `report_data.build_report_data()` computes `estimate_api_request_count()`
  before fetching (`report_optional.py:125`) and stores it as
  `report["api_estimate"]`. It never measures actual usage.
- `legacy_report_data.build_legacy_report_data()` does the same with
  `estimate_legacy_api_request_count()` (`legacy_report_data.py:141`).
- The email renderers only print `api_estimate["notes"]`
  (`email_report_text.py:445`, `email_report_html.py:491`). The numeric fields
  (`estimated_incremental_requests`, `core_remaining`,
  `estimated_percent_of_remaining`) are not rendered.
- Exports serialize `data` as-is: JSON includes `api_estimate`; CSV/XLSX/PDF
  have explicit section lists and currently omit it; text delegates to the
  email formatter.
- `report_cache.CACHE_VERSION` is 3. Cached reports are reused without
  re-fetching, so a cache hit makes 0 new API calls but still carries the
  original fetch's `api_estimate`.

## Design

### 1. Counting layer

Add a small request counter to `GitHubAPI` (`src/github_usage/api.py`):

- `self.request_count: int = 0` — logical API calls (each `request()` and
  `request_raw()` invocation, including each page of `get_all_pages()`).
- `self.request_log: list[dict[str, object]]` — always populated; bounded by
  the report's own request count (worst case ~600-700 entries at
  `max_repos=100` with all sections, tens of KB). Each entry:
  `{"method": "GET", "path": "/user/repos", "status": 200}`. Record the entry
  in a `finally` block with the status captured (or `None` on failure) so
  failed calls stay in both the total and the breakdown.
- `self.http_attempts: int = 0` — optional stretch goal for retry attempts
  (see Open questions). If deferred, label the rendered number "requests
  issued (retries excluded)".
- `get_request_stats() -> dict[str, object]` — returns
  `{"actual_requests": int, "actual_requests_by_resource": dict}`.
  Resource categories are derived from the path with ordered matching
  (billing before user, because `/users/.../billing/...` starts with `/user`):
  - `billing`: `/users/{u}/settings/billing/...` (`billing.py:24,92,139,176`)
  - `user`: `/user`, `/user/repos` (`report_data.py:179`)
  - `rate_limit`: `/rate_limit` (`report_data.py:259`)
  - `actions`: `/repos/{o}/{n}/actions/...` (`report_optional.py:70`,
    `storage.py:138`, `report_workflow_minutes.py:28,38`)
  - `repos`: `/repos/{o}/{n}/releases` and other repo paths
    (`report_optional.py:99`, `storage.py:156`)
  - `other`: anything else
  Assert in tests that `sum(actual_requests_by_resource.values()) ==
  actual_requests`.

Increment at the top of `request()` and `request_raw()` so failed calls are
counted too (they generally consume quota). Do not count the internal
`/rate_limit` fetch differently; it is a normal API call. `request_log` must
never enter the report dict: raw paths would bypass `redact.py`'s key-based
username/repo masking (`redact.py:31-42,72-81`) and leak the username into
file exports.

Thread safety: no threads in `src`; GUI `@work(thread=True)` workers each
build their own client (`gui_backend.py:361`). A plain `int` is sufficient;
note the assumption in a comment. If a client is ever shared across threads,
add a `threading.Lock` then.

### 2. Report data integration

Add a helper in `report_data.py`:

```python
def _api_request_stats(api) -> dict[str, object]:
    stats = getattr(api, "get_request_stats", None)
    if callable(stats):
        return stats()
    return {"actual_requests": int(getattr(api, "request_count", 0) or 0),
            "actual_requests_by_resource": {}}
```

This keeps the `GitHubAPIClient` Protocol (`report_data.py:22`) unchanged and
avoids breaking test fakes that do not implement the new method.

**Baseline and variance.** `estimated_incremental_requests` covers only the
optional repo-level sections for the email builder
(`report_optional.py:137-143`), and for the legacy builder the optional
sections plus `account_level = 10`
(`legacy_report_data.py:141-161`) — while the client's raw count includes
every call made before and during the builder (e.g. `/user`, `_limited_repos`,
`_rate_limit`, and for the legacy CLI path the pre-builder `check_user_scope` /
`fetch_account_info` / `fetch_rate_limits` in `legacy_report.py:94-101`).
Comparing the raw total to the estimate is apples-to-oranges. Instead, define
one matching window per estimate and subtract a full stats snapshot:

- The **baseline is the full `get_request_stats()` snapshot** (total +
  per-resource), captured before the first call the estimate covers.
- `total_requests = current_total` — the raw client total, used for
  original-fetch messages (not comparable to the estimate).
- `actual_requests` must cover exactly the calls the estimate covers — no
  more. Snapshot the counter immediately around each repo-level getter and
  sum the per-getter deltas field-by-field
  (`actual_requests_by_resource[res] = sum(after[res] - before[res])`).
  The resource deltas must reconcile: assert in tests that
  `sum(actual_requests_by_resource.values()) == actual_requests`.
- `estimate_variance = actual_requests - estimated_incremental_requests`.
- Document the window in the report dict (e.g. `estimate_scope`).

Matching windows (baseline capture points):

- `build_report_data`: capture a `window_baseline` **in-builder, immediately
  after `_rate_limit(api)`** (`report_data.py:374`) for `total_requests`
  context. But the email estimate covers only the optional repo-level
  sections, while the window also contains account-level section fetches
  (`get_actions_usage`, `get_copilot_usage`, `get_gitlfs_usage`,
  `get_monthly_costs` — e.g. an LFS-only report estimates 0 while making ≥4
  calls there). So `actual_requests` comes only from snapshots taken around
  the repo-level getters (`get_repo_consumers`,
  `get_artifact_storage_details`, `get_release_asset_details`,
  `workflow_breakdown_for_top_private`, and the
  `fetch_repo_actions_table` fallback at `report_data.py:435`), summed as
  above. The quota guard still uses the pre-fetch estimate vs
  `core_remaining`, unchanged. The caller must not pass an earlier snapshot
  here.
- `build_legacy_report_data`: the legacy estimate's `account_level = 10`
  covers account-level calls including `/user` and `/rate_limit`, which in the
  CLI path happen **before** the builder is invoked
  (`fetch_account_info` / `fetch_rate_limits`, `legacy_report.py:99-101`).
  A builder-entry baseline would miss them while the estimate counts them.
  So: add an optional `baseline_stats: dict | None = None` parameter;
  `run_legacy_report_session` captures the snapshot before its first
  API-calling operation (`check_user_scope`, which GETs `/user` when no user
  payload is passed) and passes it in. The GUI path
  (`gui_backend.run_legacy_report_data`, `gui_backend.py:361-368`) shares
  `_init_github_api`, which issues its own pre-builder `GET /user` on the
  fresh client (`cli_email_report.py:83`) — so a builder-entry default
  snapshot would exclude that call while the CLI window includes its
  pre-builder calls. The GUI caller must therefore supply a baseline
  captured before initialization (a fresh-client zero snapshot is
  equivalent), never the entry default, preserving comparable counts with
  the CLI. When `baseline_stats` is None (direct builder use), the builder
  snapshots at entry and records no scope, so renderers use the neutral
  scope label instead of implying full-report coverage (the entry window is
  narrower than the full estimate span).
  Carve `_limited_repos()` out of `actual_requests`: snapshot the counter
  around that call (`legacy_report_data.py:234`) and subtract those
  repository-listing page fetches from the delta — including from
  `actual_requests_by_resource`, in whichever bucket(s) the listing pages
  were recorded in, so the reconciliation assertion still holds. Neither
  estimate models listing pagination, so a second `/user/repos` page at
  101+ repos must not move the variance. (The email builder needs no
  carve-out: its baseline is already post-listing, and its `actual_requests`
  is a sum of per-repo-getter deltas rather than a window delta.)

Merge points (must be after the last fetch):
- `build_report_data`: immediately before
  `report["insights"] = get_key_insights(report)` (`report_data.py:441`) —
  after the `fetch_repo_actions_table(api, repos)` fallback at line 435.
- `build_legacy_report_data`: at the end, before line 360 — after
  `copilot_premium` / `copilot_billing` / `lfs_billing` (lines 345-358).

Add derived fields to `api_estimate`:

- `actual_requests`: measured delta over the estimate's matching window —
  repo-level-only for the email builder, account-level-inclusive for the
  legacy builder (each matching what its estimate covers). The only figure
  compared against the estimate; `estimate_scope` says which window applies,
  so renderers must never label legacy measurements as repo-level-only.
- `total_requests`: raw client total for original-fetch messages (not
  comparable to the estimate).
- `actual_requests_by_resource`: per-resource repo-level deltas over the same
  window (must sum to `actual_requests`).
- `estimate_scope`: which window the numbers cover
  (e.g. `"repo-sections-only"` vs `"full-report-including-account-level"`).
- `estimate_variance`: `actual_requests - estimated_incremental_requests`.
- `core_remaining_before`: already present as `core_remaining`.
- `core_remaining_after`: optional; only if a post-fetch `/rate_limit` call is
  made (see Open questions). If made, exclude that probe from
  `actual_requests` or label it.
- `from_cache`: set by the cache-hit path (see section 3).

Keep `estimated_incremental_requests` as the pre-fetch estimate. The email and
exports can then show both numbers.

### 3. Cache interaction

A cache hit must not claim the original fetch's API usage as new usage, and
must not destroy the cached measurement either.

- Add a small `annotate_cache_hit(data)` helper (e.g. in `report_cache.py`)
  that sets `data["api_estimate"]["from_cache"] = True`. Leave both counts
  intact; renderers print `total_requests` as the original-fetch total, e.g.
  "0 new API requests (M total during the original fetch; N in estimate
  scope)". Never present the window delta as the full-fetch total.
- Call it from all three cache-hit sites:
  1. `cli_email_report._load_or_fetch_email_data()`
  2. `legacy_report.run_legacy_report_session()`
  3. `gui_backend.run_legacy_report_data()` (`gui_backend.py:358`) — currently
     returns cached data unannotated, so the GUI legacy table would label a
     cache hit as a live fetch.
- Do not put the annotation inside `load_cached_report`: `test_report_cache.py:65`
  asserts `loaded == data`.
- Bump `report_cache.CACHE_VERSION` from 3 to 4. Reason: the report shape
  changes, and v3 snapshots would otherwise render as live fetches with 0
  actuals. `test_report_cache.py:131` already covers `CACHE_VERSION - 1`
  rejection.

### 4. Reporting surfaces

Add a shared formatter module `src/github_usage/report_api_usage.py` with one
pure lines function plus a shared rows adapter, matching the existing
`email_actions_table_rows` convention (`_email_report_common.py:30-39`):

- `api_usage_lines(estimate: dict | None) -> list[str]`
- `api_usage_rows(estimate: dict | None) -> list[tuple[str, str]]` derived from the
  lines (label/value pairs for HTML tables, CSV, XLSX, PDF).

Suggested content (compact):

```
REST API Usage
- Repo requests in estimate scope: 123 (estimated 120)
- Total requests this fetch (retries excluded): 130
- Core quota remaining before: 4,877 / 5,000
- Core rate limit: 5,000 requests/hour (authenticated) - https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- By resource (estimate scope): actions 100, billing 20, repos 1
- Source: live fetch
```

The scope label comes from `estimate_scope`: email renderers show
`Repo requests in estimate scope:`, legacy renderers show
`All requests in estimate scope:`, and unknown scopes fall back to the
neutral `Requests in estimate scope:`. Scope strings live as
`SCOPE_REPO_SECTIONS` / `SCOPE_FULL_REPORT` constants in
`report_api_usage.py` so builders import them instead of re-typing.
Formatters return no lines when the estimate carries no measurement keys,
zero-count buckets are omitted from the breakdown, and all strings are
ASCII-only (the PDF writer uses core Helvetica, which has no em dash).

On a cache hit: `- Source: cached report (0 new API requests; 130 total during the original fetch)`.

Cached rendering keeps the original measurement on the scope line; only the
total line is relabeled. (Recorded 2026-11-11: do not zero the scope line —
chunk 4 must preserve this.)

Surface-by-surface:

- **Email text** (`email_report_text.py`): do NOT add a new
  `_SECTION_FORMATTERS` entry — the quota notes are rendered after the loop
  (`email_report_text.py:445-448`). Extend the existing "REST API Quota
  Notes" block to include the usage lines above the notes.
- **Email HTML** (`email_report_html.py`): likewise extend
  `_html_api_notes_block()` (`email_report_html.py:434-442`) rather than
  adding a new `_SECTION_HTML_FORMATTERS` entry. Render the usage rows in the
  existing `<ul>` (or a small table) before the notes.
- **Legacy terminal** (`legacy_terminal.py`): add
  `render_api_usage(data.get("api_estimate"))` next to
  `render_rate_limits(...)`. Implement the printer in
  `report_api_usage.py` (or `report_account.py`). Add a case to
  `test_legacy_terminal.py`.
- **JSON export** (`export_json.py`): no code change needed; `api_estimate` is
  already serialized. Add the new fields to the documented schema.
- **CSV export** (`export_csv.py`): add `_write_api_usage_section(writer, data)`
  to `_write_sections()` (`export_csv.py:61-86`), using the
  `### Name ###` header convention (`export_csv.py:279-281`).
- **XLSX export** (`export_xlsx.py`): add an "API Usage" sheet through the
  `write_sheet(name, title, rows)` closure (`export_xlsx.py:62-75`), registered
  in `_SECTION_WRITERS` (`export_xlsx.py:306`); place it first (near Metadata).
- **PDF export** (`export_pdf.py`): add an "API Usage" page in
  `_SECTION_PAGES` (`export_pdf.py:291`) rather than editing the cover; note
  `_MAX_SECTION_ROWS = 30` (`export_pdf.py:30,59-71`) and `_fmt_num` for ints.
- **Text export** (`export_text.py`): no code change; it delegates to
  `format_report_email()`, so it inherits the email section.
- **GUI**: `gui/views/email_report_view.py` inherits via
  `run_email_dry_run` → `cli.main` → `format_report_email`
  (`gui_backend.py:431`). The legacy report view does NOT:
  `gui/views/report_view.py` renders through
  `legacy_report_summary.legacy_report_detail_rows` (`report_view.py:277`), a
  separate renderer with no `api_estimate` rows. Add the usage rows there and
  a case to `test_legacy_report_summary.py`.
- **`runs --api`**: out of scope for billing reports, but its `--json` output
  could include the client's request count as a cheap follow-up.

**Rate-limit reference line.** Every surface that shows API usage must include
the current GitHub REST API primary limit and a link to the authoritative docs:

`- GitHub core rate limit: 5,000 requests/hour (authenticated) — https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api`

Use the live `core_limit` from `/rate_limit` when available (the report already
fetches it) and fall back to the documented 5,000/hour value otherwise. As of
November 2026 the documented primary limits are:

- Authenticated requests: 5,000 requests/hour.
- Unauthenticated requests: 60 requests/hour.
- GitHub App installation tokens: 5,000/hour (15,000/hour for GitHub
  Enterprise Cloud organizations).
- Built-in `GITHUB_TOKEN` in GitHub Actions: 1,000/hour per repository
  (15,000/hour for GHEC).
- Search API: separate, more restrictive limits (30 requests/minute).
- Secondary limits also apply (max 100 concurrent requests; 900 points/minute
  for REST). `GET /rate_limit` does not count against the primary limit.

Authoritative link: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

Also update `report_account.render_what_else` (`report_account.py:144-152`),
which already lists static rate-limit numbers, to include the same docs link.

### 5. Protocol and test fakes

- Leave `GitHubAPIClient` as-is and use `getattr` in `_api_request_stats`.
- Update fakes in tests that assert on `api_estimate` to include the new keys.
- Search for classes implementing `request`/`get_all_pages` in `tests/` and add
  a `request_count` attribute where the new assertions need it.

## Tests

- `tests/test_api.py`: counter increments on `request()` and `request_raw()`;
  `get_all_pages()` counts each page; `get_request_stats()` totals and
  breakdown; failed calls still count; `sum(breakdown.values()) ==
  actual_requests` even when a call fails.
- `tests/test_report_data.py`: `build_report_data()` merges actual counts into
  `api_estimate`; estimate fields remain; baseline delta is computed over the
  matching window; partial-failure (`errors` non-empty) still merges counts and
  keeps the pre-fetch estimate.
- `tests/test_legacy_report_data.py`: same for the legacy builder, plus the
  caller-passed `baseline_stats` path: a snapshot taken before the
  pre-builder account/rate-limit fetches yields deltas covering the full
  `account_level = 10` span, and per-resource deltas sum to `actual_requests`.
- `tests/test_email_report_text.py` / `test_email_report_html.py`: extended
  quota block renders actual, estimated, breakdown, and cache-hit variants.
- `tests/test_export_csv.py`, `test_export_xlsx.py`, `test_export_pdf.py`:
  new section/sheet renders.
- `tests/test_legacy_terminal.py`: legacy terminal API usage section.
- `tests/test_legacy_report_summary.py`: GUI legacy detail rows include usage.
- `tests/test_report_cache.py`: cache hit annotates `from_cache` (and leaves
  both counts); `CACHE_VERSION` bump invalidates old wrappers. Update the
  `CACHE_VERSION` pin in `tests/test_report_optional.py:327`
  (`CacheVersionTests.test_cache_version_is_3`) from 3 to 4 alongside the
  bump, or `scripts/check` fails.
- `tests/test_api.py` (or the new module's test): cover the `getattr` fallback
  path (client without `get_request_stats`), the no-estimate case, the
  `estimate_variance` sign / zero-estimate cases, and the listing carve-out:
  a two-page `_limited_repos()` fetch must change `total_requests` while
  leaving the variance against `estimate_legacy_api_request_count()`
  untouched.
- Fixtures `tests/fixtures/email_report_data.json:78` and
  `tests/fixtures/export_report_data.json:97` lack the new keys; render with
  `.get()` defaults so existing `assertIn`-style tests
  (`test_email_report.py:16-29`) keep passing, or update the fixtures.
- State that aggregated counts need no redaction; assert `request_log` never
  enters the report dict.
- Assert the original-fetch message uses `total_requests` (not the window
  delta) in the email, legacy terminal, and export surfaces; assert the
  estimate-scope delta is labeled separately.
- Assert the rate-limit reference line and the docs link render in the email,
  legacy terminal, and export surfaces.
- New `report_api_usage.py` must clear the 82% new-file coverage gate
  (`scripts/coverage-check`).
- Run `scripts/check` (install the `gui` extra first if the environment lacks
  `textual`).

## Docs and changelog

- `docs/reports.md:64-65` (JSON preserves `api_estimate`) and
  `docs/email-reports.md:140-141` (request-cost framing): document the new
  `api_estimate` fields and the API usage section.
- `CHANGELOG.md`: add an `[Unreleased]` → `Added` entry.
- This plan now lives in `docs/superpowers/plans/`; follow the repo's plan
  lifecycle (status banner, archive to `archived/` when complete).

## Open questions

1. **Logical calls vs HTTP attempts.** Counting logical calls is simple and
   matches the estimate. Retry attempts are invisible without threading a
   counter through `http_retry` (one logical call can consume up to
   `max_retries + 1` HTTP requests, `http_retry.py:113-118`). Recommendation:
   ship logical calls first, label the number "requests issued (retries
   excluded)", and add an `on_attempt` callback / `http_attempts` only if
   users ask.
2. **Post-fetch `/rate_limit`.** Fetching `/rate_limit` after the report gives
   an exact `core_remaining_after` and `quota_consumed`, at the cost of one
   extra request. Recommendation: make it an opt-in flag (default off); the
   actual request count plus `core_remaining_before` is enough for the email.
   If enabled, exclude the probe from `actual_requests` or label it.
3. **Breakdown granularity.** By resource category is compact and useful; by
   full path is noisy. Recommendation: resource category, always logged.
4. **Cache-hit semantics.** Set `from_cache: True` and leave the original
   count; renderers print "0 new requests (N during the original fetch)".
5. **Naming.** Extend `api_estimate` with `actual_*` fields (recommended) vs a
   new top-level `api_usage` key. Extending avoids two sources of truth.
6. **Redundant `/rate_limit`.** `build_legacy_report_data` calls
   `_rate_limit(api)` at `legacy_report_data.py:238` even when `rate_limits`
   was already fetched and passed in (`legacy_report.py:101`). The new counter
   will surface this; do not fix it here, but record it as a follow-up.

## Task breakdown

- [x] Add `GitHubAPI` request counting + `get_request_stats()`; unit tests.
  **Done:** 2026-11-11 — counter, per-resource log, and stats merged in
  `api.py`; 9 unit tests (incl. failure/transport, pagination, buckets);
  reviewer minors applied (no functional deviations).
- [x] Add `report_api_usage.py` (lines + rows adapter); cover the new file's 82%
  coverage gate.
  **Done:** 2026-11-11 — shared `api_usage_lines`/`api_usage_rows` with scope
  labels, quota/rate-limit/breakdown/source lines; 9 unit tests at 100% file
  coverage.
  **Review:** deepseek APPROVE with follow-ups applied — ASCII-only strings
  (PDF-safe), absent-measurement gate returning no lines, zero-bucket filter,
  cached total label, shared `SCOPE_*` constants, shorter PDF-safe labels.
- [x] Merge repo-level-delta actual usage into `api_estimate` in both builders
  (email: per-getter snapshots around repo-level getters, using the shared
  `SCOPE_*` constants for `estimate_scope`; legacy: caller-passed
  `baseline_stats` full-snapshot subtraction incl. per-resource, minus the
  `_limited_repos` listing calls); bump `CACHE_VERSION` (plus the test pin);
  add `annotate_cache_hit()` at all three sites; tests.
  **Done:** 2026-11-11 — per-getter `_track_repo_calls` + `_sum_repo_deltas`
  merge in both builders; legacy caller-passed `baseline_stats` with listing
  carve-out and omitted scope on entry fallback; `annotate_cache_hit` at all
  three cache sites; `CACHE_VERSION` 4 + pin update; CountingFakeAPI (incl.
  multi-page listings) + builder/helper/cache-hit integration tests (incl.
  caller-baseline, 2-page invariance, session coverage, section-failure
  fallback).
  **Review:** deepseek APPROVE with follow-ups folded in — `_api_request_stats`
  fallback buckets unknowns under `other`; merge helpers consolidated in
  `report_api_usage.py` (report_data.py stays under the 500-line budget);
  non-dict snapshots tolerated; exact-bucket test assertions kept where they
  pin the dense contract; legacy None-baseline omits (rather than invents) a
  scope value.
  **Review 2:** deepseek APPROVE (no blockers) with minors applied — caller-
  baseline test proves pre-builder inclusion; `_merge_legacy_api_estimate`
  extracted to `report_api_usage.py` (~163→~140-line builder); section-level
  abort path tested with fallback re-run; `annotate_cache_hit` covered at all
  three call sites via integration tests; `_track_repo_calls`/`deltas` typed;
  monotonicity documented; GUI test module ordering fixed.
  **Review 3 (chunk 4):** deepseek verdict pending — chunk-4 review requested.
- [ ] Extend the email text/HTML quota blocks; legacy terminal; CSV/XLSX/PDF;
  GUI legacy detail rows; add the rate-limit reference line + docs link;
  tests. Chunk-4 decisions (locked): keep the cached scope line as the original
  measurement (only the total line is relabeled); gate the extended quota
  block on `notes or usage lines` so measured reports with zero notes still
  render; label totals as requests-issued (retries excluded); HTML docs URL
  stays plain text (matches text body; mail clients autolink); terminal keeps
  both quota lines (usage block stays self-contained); PDF splits the docs URL
  onto its own row (fixed-width cells can't wrap).
- [ ] Docs (`docs/reports.md`, `docs/email-reports.md`), changelog,
  `scripts/check`, and a final review.

## Related follow-ups (out of scope here)

- The truncation note "Repository list truncated to 50 of 51 repositories" is a
  lower bound (`max_repos + 1`), not the true repo count. Fixing it needs a
  separate count or a full fetch.
- The email "Top Repositories by Actions Minutes" list is capped at 5
  (`get_repo_consumers(..., limit=5)`); raising `max_repos` does not raise the
  top-N.
- Redundant `/rate_limit` call in `build_legacy_report_data`
  (`legacy_report_data.py:238`); the counter will surface it.
