> **Status:** IN PROGRESS (Phases 1–5 largely complete; Phase 6 exports / Phase 7 TUI / README polish remaining)

> Line numbers are accurate as of 2026-07-30; relocate by anchor (function name + dict key) if they drift.
>
> **Implementation log:**
> - **Done:** 2026-07-30 — Phase 1 complete. `src/github_usage/usage_split.py` created with runner-SKU classification, visibility split, finalize/unattributed, storage allowance helpers, `REPORT_SOURCES`, `attach_actions_visibility_split`. `tests/test_usage_split.py`. Committed `6af1e0d`. Deviation: std SKU check compares raw lowercased form against `STANDARD_RUNNER_SKUS`; `normalize_sku` for alias display only. Module grew past the ~150-line target (helpers justified).
> - **Done:** 2026-07-31 — Phase 1/3 audit fixes: SKU quantities **summed** across repos; `private_storage_avg_mb` via `gb_hours_to_avg_mb`; `_larger_runner_skus` passes item dict; `internal_repo_count`; `load_cached_report` rejects stale `CACHE_VERSION`; fragile empty-repos test replaced.
> - **Done:** 2026-07-31 — Phase 3 complete. 3a `by_visibility` on `get_repo_consumers`; 3b `attach_actions_visibility_split` in `build_legacy_report_data`; 3d `CACHE_VERSION=2` + load-time version check. Builder tests pass.
> - **Done:** 2026-07-31 — Phase 2a–2d/2g (+ partial 8a/8b): `storage.py` adds artifact expiry/retention rollups + `artifact_storage_gb`/`release_storage_gb`; `storage_summary` + `sources` on legacy report; `report_storage.py` (`render_artifact_storage_section`, `build_storage_summary`); sources footer in `legacy_terminal`.
> - **Done:** 2026-07-31 — Phase 4a/4b (`report_actions_limits.py`: Usage by Visibility + private Limits Summary + larger-runner `*`); 4c/4d (`report_summary_insights.py`: private utilization bars, visibility subsection, private recommendations, larger-runner/expiry findings); 4f forecast feeds private minutes/storage + public extras.
> - **Done:** 2026-07-31 — Phase 5a/5b/5c (+ email sources): email text/HTML prepend private-vs-public summary when `by_visibility` present; warnings use `private_minutes_percent`; insights prepend private-quota message; Sources footer on email bodies; `build_report_data` attaches `sources`.
> - **Remaining:** Phase 6 exports; Phase 7 TUI rows; Phase 8c/8d README polish; Phase 9 confirmation; Phase 11 README detail; full `scripts/check` / smoke / docs-check.

# Private Usage Emphasis & Runner-SKU Classification

## Problem

The free-tier Actions quota (2,000 minutes / 500 MB artifact storage for personal accounts) applies to **private repositories only**. Public-repo standard-runner usage is free and does not draw down the quota.

> **Reference links (all verified live 2026-07-30).** These are the sources for every claim in this plan and will appear in a "Sources" footer in the reports (Phase 8):
>
> - **About billing for GitHub Actions** — free-tier table (2,000 min / 500 MB artifact storage, private-only), GB-hour accrual model, shared artifact+Packages pool, separate 10 GB/repo cache, standard runners free in public repos, larger runners always billed, 90%/100% included-usage email alerts: https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions
> - **Actions runner pricing** — standard SKU list and larger-runner SKUs/rates (`linux_4_core`, `macos_l`, GPU, etc.): https://docs.github.com/en/billing/reference/actions-runner-pricing
> - **About releases** — release assets are **not** Actions artifact storage (≤2 GiB per file, unlimited total, no bandwidth charge): https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
> - **About GitHub Packages** — public packages free; private packages draw from the plan storage pool shared with Actions artifacts: https://docs.github.com/en/packages/learn-github-packages/about-github-packages

Today the report tracks and renders **combined** usage everywhere the quota matters, which misstates quota pressure:

- `actions.minutes` / `actions.storage_gb_hours` in `get_actions_usage()` (`report_data.py:68`) sum the account-level billing summary, which **includes public usage**. The report currently reports `8,758.3 / 2,000 min (437.9% used)` even though public-repo minutes (4,392 scanned) are free.
- `render_limits_summary()` (`report_actions.py:331`), legacy `show_limits_summary()` (`report_actions.py:117`), `_print_utilization()` (`report_summary.py:258`), `_print_recommendations()` (`report_summary.py:357`), and `build_report_forecast()` (`report_forecast_data.py:16`) all use the combined values against the 2,000/500 limits.
- The Per-SKU Breakdown (`render_actions_summary`, `report_actions.py:212`) does not flag **larger-runner** SKUs, which are **always billed even on public repos** and never covered by included minutes.
- **Storage semantics are mis-framed:** the free allowance is **500 MB of artifact storage** (private repos only), billed as an **hourly accrual in GB-hours**. 0.5 GB (500 MB) stored flat for a 30-day month = `0.5 × 720 = 360 GB-hrs`; that is the full private allowance. The report compares `avg MB vs 500 MB` using combined public+private values and never explains the accrual or the retention window.
- The email report and exports have no private-vs-public Actions summary, and per-repo artifact storage has no retention/expiry context (e.g. `DICOMViewerV3` accrued 49.4 GB-hrs but is public/free, and its artifacts are on the default 90-day retention).

User goal: keep reporting public-repo usage (nice to know), but make **private-repo usage the primary signal** so the small Actions budget (which SKUs and repos) is easy to optimize and track — including **artifact storage and its retention policies**.

**Context — larger runners:** GitHub-hosted larger runners (e.g. Linux 4/8/16-core, Windows 4-core, `macos_l`/`macos_xl`, GPU) are only available to organizations on Team/Enterprise Cloud, are always billed regardless of visibility, and included minutes cannot be used for them ([Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing), "Points to note about rates for runners"). Standard SKUs are exactly `actions_linux`, `actions_linux_slim`, `actions_linux_arm`, `actions_windows`, `actions_windows_arm`, `actions_macos`. This account is a **free personal plan**, so larger-runner SKUs should not appear today (the observed SKUs in the current report are all standard); the classifier is defensive and will surface them loudly if they ever do. The "over 0.5 GB-hrs" email the user received about `DICOMViewerV3` is a **storage alert**, not a runner alert — GitHub emails at 90%/100% of included usage, and the alert is measured in accrued GB-hours against the converted private allowance; `DICOMViewerV3` being public means its 49.4 GB-hrs never counted against the quota.

**Prior work already in the tree:** `src/github_usage/visibility.py` (shipped by the `2026-07-22-public-private-visibility` plan, archived/COMPLETE) already provides `repo_visibility()`, `group_by_visibility()`, `visibility_label()`, and `filter_repos_by_visibility()`. The email report already groups consumers by visibility via `group_by_visibility` (delivered by the `2026-07-27-visibility-billing-docs` plan). This plan builds on those primitives — it does not reintroduce them. One deliberate divergence: `group_by_visibility()` keeps `internal` as its own group for the per-repo table, while the billing aggregates here fold `internal` into `private` (billing-correct; see decision #1).

## Approach

Compute a **private / public / unattributed** split of Actions minutes, storage, and per-SKU usage from the per-repo rows that already carry `visibility`, reconciled against the authoritative account-level billing summary. Use the **private** bucket for every free-tier limit check and forecast; keep the public bucket visible but labeled free. Flag non-standard (larger-runner) compute SKUs. Add an artifact-storage section that explains the **accrual model** (GB-hrs vs 500 MB flat-all-month = 360/372 GB-hrs), reports **current-vs-accrued** storage per GitHub's billing model, and surfaces **retention/expiry** per repo. No new CLI flags or config keys — this is automatic behavior.

**Scope:** full private/public split + SKU classification + artifact storage lands in the **legacy report** (terminal, exports, TUI), which already fetches `repo_actions` and artifact scans for all scanned repos. The **email report** gets a lighter-weight `by_visibility` aggregate from `repo_consumers` (already iterates every repo; no SKU detail, no unattributed) plus an artifact-storage summary line — matching its existing "annotate, don't regroup" philosophy.

---

## Phase 1 — New module `src/github_usage/usage_split.py`  · **Done** 2026-07-30 (commit 6af1e0d)

Small, pure, dependency-light module (target: under ~150 lines). Imports only `report_helpers` helpers if needed.

### 1a. Runner-SKU classification

```python
STANDARD_RUNNER_SKUS = {
    "actions_linux",
    "actions_linux_slim",
    "actions_linux_arm",
    "actions_windows",
    "actions_windows_arm",
    "actions_macos",
}

def normalize_sku(sku: str) -> str:
    """Lowercase and strip a leading ``actions_``/``actions`` prefix so API
    and reference-table spellings compare equal. Also collapses digit-word
    boundaries (``4core`` → ``4_core``) as a defensive guard; the pricing
    reference always uses the underscore form."""
    ...

def is_standard_runner_sku(sku: str) -> bool:
    """True for the standard GitHub-hosted runner SKUs above."""

def classify_actions_sku(sku: str, item: dict | None = None) -> str:
    """Classify a billing SKU as ``"standard"``, ``"larger"``, or ``"storage"``.

    ``gigabyte-hours`` items are storage. Compute (minutes-unit) SKUs outside
    the documented standard set are treated as ``"larger"`` — larger runners
    are always billed, so a false ``"larger"`` is the safe direction.
    """
```

A `LARGER_RUNNER_ALIASES` map may hold human-readable names for display (e.g. `linux_4_core` → "Linux 4-core"). It is **display-only and best-effort**: the runner-pricing reference lists 30+ larger SKUs (x64, arm64, GPU, and macOS variants), and any larger SKU absent from the map falls back to its raw SKU string with the `*` marker. Only add entries documented in the runner-pricing reference.

### 1b. Visibility split aggregation

```python
def split_rows_by_visibility(
    rows: list[dict],
    *,
    minutes_key: str = "minutes",
    storage_key: str | None = "storage_gb_hours",
    sku_key: str | None = "sku",
) -> dict[str, dict]:
    """Aggregate per-repo rows by ``visibility`` into
    ``{visibility: {minutes, <storage_key>, skus: {sku: {grossQuantity,
    grossAmount, netAmount, unitType}}}}``. Visibility resolution delegates to
    the shipped ``visibility.repo_visibility(row)``; ``"internal"`` folds into
    ``"private"`` for billing purposes (the billing-relevant variant of the
    shipped ``group_by_visibility``, which keeps ``internal`` as its own
    group). Skips SKU aggregation when ``sku_key`` is ``None``.
    """

def finalize_actions_split(
    split: dict[str, dict],
    *,
    account_minutes: float,
    account_storage_gb_hours: float,
    filtered: bool = False,
) -> dict:
    """Add ``unattributed`` = ``max(0, account − scanned sum)`` for minutes and
    storage, plus ``private_minutes_percent`` (vs the private free-tier limit,
    param `private_minutes_limit=2000`), ``public_minutes``, and
    ``larger_runner_skus`` (from the aggregated per-visibility sku maps, which
    are the only place SKU detail exists). ``filtered`` marks reports built
    under ``--only-*`` so renderers can phrase output as "scanned repos".
    """
```

**Reconciliation rule:** account-level totals from the billing summary are authoritative. `unattributed` absorbs any remainder (repos beyond `max_repos`, measurement skew between the summary and per-repo endpoints). If scanned exceeds account (negative remainder), clamp to 0 and add a `reconciled: false` note rather than inventing negative usage.

**SKU split note:** per-repo `sku` dicts (from `get_actions_per_repo`, `billing.py:114`) carry per-repo SKU detail; aggregating them by visibility gives the private/public SKU matrix. Unattributed SKU usage is **not** computed per-SKU (avoid accounting gymnastics); the account-level SKU table in the summary section still shows totals.

---

## Phase 2 — Artifact storage & retention coverage  · **Done** 2026-07-31 (2a–2d/2g; 2e covered via Phase 4 limits/utilization; 2f email/exports deferred to Phases 5–6)

### 2a. Storage framing (constants + helpers)

Add storage-framing helpers to `usage_split.py` (kept together with the split logic):

```python
PRIVATE_STORAGE_LIMIT_GB = 0.5      # 500 MB free artifact storage, private repos
def storage_allowance_gb_hours(days_in_month: int) -> float:
    """Full private artifact allowance expressed as GB-hrs:
    0.5 GB flat all month = 0.5 * 24 * days (360 for 30 days, 372 for 31,
    336 for a 28-day February). Callers must pass
    ``days_in_month(reference_date)`` so a prior-month/``--as-of`` report
    matches the usage month."""
def flat_equivalent_gb_hours(gb_hours: float, days_in_month: int) -> float:
    """GB that would have to sit flat all month to produce ``gb_hours``
    (e.g. 165.29 GB-hrs ≈ 0.22 GB ≈ 230 MB flat all month). Assumes the
    input GB-hours accrued over a full billing cycle of ``days_in_month``
    days — a mid-month snapshot understates the flat-equivalent."""
```

Use `report_helpers.day_of_month`/`days_in_month` for the month length; these already exist. Sources: the "How storage billing works" section (hourly accrual, included amount converted to an hourly rate) and the free-tier table in [About billing for GitHub Actions](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions).

**Cache storage is out of scope for the private artifact framing:** GitHub also bills a separate 10 GB/repo Actions **cache** allowance that does not draw from the 500 MB artifact pool. If a cache SKU (e.g. `actions_cache_storage`) ever appears in the billing summary, `classify_actions_sku` labels it `"storage"` by unit type; the report must not merge cache into the private artifact framing. Confirm during implementation whether the summary surfaces a cache SKU for this account; if it does, surface it separately in the storage section and note it in the README.

### 2a-2. Release assets are NOT artifact storage

`get_storage_analysis()` (`storage.py:8`) currently sums **Actions artifacts + release assets** into one `total_storage`. These are billed differently:

- **Actions artifacts** consume the plan storage pool (500 MB private allowance; shared with GitHub Packages). Quota-relevant.
- **Release assets** are separate and effectively unlimited (≤2 GiB per file, no total-size or bandwidth charge — the doc cites no total cap) — [About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), "Storage and bandwidth quotas". Never quota-relevant, always free.

Concretely: `DICOMViewerV3`'s 49.4 GB-hrs of accrued Actions storage is separate from any release assets it hosts; the report must not imply release assets draw down the 500 MB allowance.

Plan change: keep the combined `total_storage` key for backward compatibility, but add `artifact_storage_gb` and `release_storage_gb` per repo, and in every renderer (artifact section, `_print_storage_breakdown`, TUI, exports) show the two separately with release assets labeled "free/unlimited (not quota-billed)". No API change — the scan already distinguishes `type == "Artifact"` vs `"Release Asset"` in each item.

### 2b. Data — artifact expiry/retention in `get_storage_analysis()` (`storage.py:8`)

The `/repos/{owner}/{repo}/actions/artifacts` response already includes `size_in_bytes`, `created_at`, `expires_at`, `expired` per artifact ([List artifacts for a repository](https://docs.github.com/en/rest/actions/artifacts?apiVersion=2022-11-28) — verified live). Record on each artifact item and roll up per repo:

- artifact item: add `expires_at` (ISO), `expired` (bool), `days_to_expiry` (int | None, from `expires_at` − today)
- repo entry: add `artifact_count`, `expired_count`, `expiring_soon_count` (expiring within 7 days), `earliest_expiry` (ISO | None), and `retention_days` (int | None) derived from `expires_at − created_at` of the **most recently created non-expired** artifact (a newest-but-expired artifact would report a retention window that no longer applies; fallback `None` when dates are missing). **No extra API calls** — all fields already come back on `/actions/artifacts`.

Do not try to compute accrual from the snapshot: scan data is "current storage"; accrued GB-hours comes only from billing (mirrors GitHub's current-vs-accrued distinction).

### 2c. Data wiring — storage summary keys on the legacy report

In `build_legacy_report_data` (`legacy_report_data.py:204`), after `storage_analysis` is fetched, attach to the report dict a `storage_summary` block:

```python
report["storage_summary"] = {
    "private_gb_hours": ...,   # from finalize_actions_split output
    "public_gb_hours": ...,
    "unattributed_gb_hours": ...,
    "allowance_gb_hours": storage_allowance_gb_hours(days_in_month(reference_date)),
    "private_avg_mb": ...,
    "public_avg_mb": ...,
    "retention_default_days": 90,
}
```

Populate `private_gb_hours`/`public_gb_hours` from the Phase 3b split on `report["actions"]` (single source of truth — do not recompute). Thread the report's `reference_date` (the billing month) into the allowance so a prior-month/`--as-of` report matches its usage month. Email path: email has no `storage_analysis`; its artifact summary line (Phase 5) uses `by_visibility.storage_avg_mb` plus a `retention_default_days` note.

### 2d. Rendering — "Artifact Storage & Retention" section

New renderer `render_artifact_storage_section(storage_analysis, actions, username)` — put it in `report_actions.py` if it fits the size budget, otherwise a new small `report_storage.py` module. Called from `render_legacy_report` (`legacy_terminal.py:30`) right after `render_actions_summary`. Legacy `show_*` path stays untouched (delegates to renderers).

Output shape:

```
  Artifact Storage & Retention
  ──────────────────────────────────────────────────────────────────────
  Private allowance: 500 MB of artifacts = 372 GB-hrs flat all month ({month year})
    Private accrued:  165.29 GB-hrs (44.4% of 372)  ≈ 229 MB flat all month
    Public accrued:    50.35 GB-hrs (free — no quota impact)
    Unattributed:       0.00 GB-hrs

  Per-repo (current scan)             CURRENT   ACCRUED   ARTIFACTS   EXPIRY
    kgrizz-git/SpotiBye [private]      194.6 MB  141.36 GB-hrs   12    ≤7d: 3
    kgrizz-git/WeekendDigestFreeAPIs   32.9 MB    23.88 GB-hrs    5    in 61d
    ...
  Retention: 90 days default; adjust per repo (Settings → Actions → General).
```

Per-repo rows merge `storage_analysis` (current MB, counts, expiry) with `repo_actions` (accrued GB-hrs, visibility). Keep it to top-10 by accrued GB-hrs; show `expired_count` when nonzero. Public rows labeled free. The allowance-line month name comes from the report's `reference_date` (e.g. "Jul 2026" for July) — never hardcoded.

### 2e. Storage limit/forecast semantics

- `_print_utilization` (`report_summary.py:258`) storage bar: keep **private avg MB vs 500 MB** as the headline (intuitive), and add a second line with **private accrued GB-hrs vs `allowance_gb_hours`** and the flat-equivalent: `"Private accrued 165.29 / 372 GB-hrs (44.4%) ≈ 229 MB flat all month"`.
- `render_limits_summary` (`report_actions.py:331`) storage block (from Phase 4b): same dual framing.
- Forecast (`report_forecast_data.py:16`): continue projecting **private avg MB** against 500; add `private_gb_hours_projected` and `flat_equivalent_mb` to the forecast extras when the actions split is present. `compute_forecast` stays pure.
- Public storage stays informational everywhere (free).

### 2f. Email / exports

- Email text+HTML (Phase 5 block): append an artifact-storage line — `"Private artifacts: 165.29 GB-hrs of 372 allowance (44.4%) · public 50.35 GB-hrs (free)"` — when `by_visibility` exists; plus a one-line retention note.
- JSON: automatic once `storage_analysis` entries and `storage_summary` carry the new fields. CSV/XLSX: add accrued-GB-hrs + expiry columns to the artifact/storage sections, and the allowance framing in the new "Actions Usage by Visibility" section. PDF: brief framing paragraph on the consumers page.

### 2g. Tests (see Phase 10 for the full map)

- `tests/test_storage.py`: artifact items and repo entries carry `expires_at`/`expired`/`days_to_expiry`/`retention_days`; `artifact_count`/`expired_count`/`expiring_soon_count` correct.
- `tests/test_usage_split.py`: `storage_allowance_gb_hours(30) == 360`, `(31) == 372`; `flat_equivalent_gb_hours` math.
- Renderer/export/forecast tests per Phase 10.

---

## Phase 3 — Data wiring  · **Done** 2026-07-31 (3a/3b/3d; 3c N/A as planned)

### 3a. Email path: `get_repo_consumers()` (`report_optional.py:22`)

Add a `by_visibility` key to the returned dict, computed via `split_rows_by_visibility(rows, storage_key="storage_avg_mb", sku_key=None)` (the rows built in the loop already carry `visibility`, `minutes`, `storage_avg_mb`). Email only needs minutes/avg-MB, so no SKU detail and no unattributed.

Do **not** attach `finalize_actions_split` here (no account reconcile in this function); the email renderers use the raw split.

### 3b. Legacy path: attach split to `actions` (`legacy_report_data.py:build_legacy_report_data`)

After `repo_actions` is fetched (line 240) and before the report dict is returned, compute:

```python
split = split_rows_by_visibility(repo_actions)          # minutes + storage_gb_hours + skus
actions = report["actions"]                              # after the loop at line 295-303
report["actions"] = finalize_actions_split(
    split,
    account_minutes=float(actions.get("minutes", 0.0)),
    account_storage_gb_hours=float(actions.get("storage_gb_hours", 0.0)),
    filtered=only_public or only_private,
)
```

This mutates `report["actions"]` to include: `private_minutes`, `public_minutes`, `unattributed_minutes`, `private_storage_gb_hours`, `public_storage_gb_hours`, `unattributed_storage_gb_hours`, `private_storage_avg_mb`, `public_storage_avg_mb`, `private_minutes_percent` (vs 2,000), `larger_runner_skus`, `filtered`. Add a small private helper `attach_actions_visibility_split(report, repo_actions, *, only_public, only_private)` in `usage_split.py` so the email path can reuse it if it later fetches `repo_actions`.

If `actions` is `None` (fetch error), skip attaching and record nothing new.

### 3c. `build_report_data()` (`report_data.py:284`)

Email path already gets `by_visibility` via `repo_consumers` (3a). No change needed to `_fetch_sections`. If `include_consumers` is off, email has no per-repo data — renderers must degrade gracefully (see Phase 5).

### 3d. Cache

The report dict shape changes. Bump `CACHE_VERSION` (`report_cache.py:27`) from `1` to `2` so old snapshots (no split keys) invalidate cleanly. No new cache params — filters already keyed.

---

## Phase 4 — Terminal rendering (legacy report)  · **Mostly done** 2026-07-31 (4a/4b/4c/4d/4f; 4e N/A)

### 4a. `render_actions_summary()` (`report_actions.py:212`) and legacy `show_actions_summary()` (`report_actions.py:16`)

After the Summary block, add a **"Usage by Visibility"** block:

```
  Private (billable):   2181.3 min  of 2000 free (109.1% of private quota) | 165.3 GB-hrs
  Public (free):        4392.0 min  | 50.4 GB-hrs
  Unattributed:         2185.0 min  | 0.0 GB-hrs   (repos beyond scan / measurement skew)
```

In the **Per-SKU Breakdown** table, annotate compute SKUs with a larger-runner marker: append ` *` (and a footnote `* = GitHub-hosted larger runner — always billed, not covered by free tier`) for any SKU where `classify_actions_sku(...) == "larger"`. Add the footnote line only when such a SKU exists.

Use `actions.get("private_minutes")` etc. with fallback to combined values when split keys are absent (old cached data / unit-test fixtures). Render the Private line as the fold of private+internal rows; when internal rows are present in the scan, append `(includes N internal repos)` (decision #1).

### 4b. `render_limits_summary()` (`report_actions.py:331`) and legacy `show_limits_summary()` (`report_actions.py:117`)

Base both the minutes and storage checks on the **private** bucket:

```
  Actions Minutes (private repos only):
    Used:         2181.3 / 2000 min (109.1% used)
    Public repos:  4392.0 min (free — no quota impact)
    Unattributed:  2185.0 min (best-effort attribution)

  Actions Storage (avg, private repos only):
    Used:         227.5 / 500 MB (45.5% used)
    Accrued:      165.3 / 372 GB-hrs (44.4%)  ≈ 229 MB flat all month
    Public repos:   69.3 MB / 50.4 GB-hrs (free)
    Unattributed:    0.0 MB
```

Show public/unattributed lines only when nonzero (keep output tight for the common all-private case). When `filtered` is set, prefix the section title with "(scanned repos)" and suppress the quota math when `private_minutes` is zero (e.g. `--only-public`) — do not present a partial slice as `0 / 2000 (0%)`. Leave the Copilot note block unchanged.

### 4c. `_print_utilization()` (`report_summary.py:258`)

Change the two bar charts to use `private_minutes` / `private_storage_avg_mb` against 2,000 / 500. Add an informational line under each bar when public usage exists; add the accrued GB-hrs line per Phase 2e:

```
    Actions Minutes:     2181.3 / 2000 min (109.1% of private free tier)
    ████████████████████████████████████████
    ⚠ HIGH USAGE — private repos past the free-tier minute limit!
    (+ 4392.0 min public, free)
```

Guard on split keys; fall back to combined behavior when absent. When `filtered` is set, label the bars "(scanned repos)" and skip the HIGH USAGE flag for a partial slice (same rule as 4b/4f).

### 4d. `render_final_summary_from_data()` (`report_summary.py:62`) and `show_final_summary()` (`report_summary.py:11`)

- Add a `_print_visibility_split(actions)` helper invoked right after `_print_cost_overview(...)`, printing a compact **"PRIVATE vs PUBLIC ACTIONS"** table (minutes, storage GB-hrs, % of private quota) with the same layout as 4a. Insert as subsection `2.5` or fold into `_print_top_consumers` — pick one, keep numbering consistent.
- `_print_recommendations()` (`report_summary.py:357`): the first recommendation currently keys off combined `user_minutes`. Rebase it on **private** minutes: when `private_minutes > 2000`, recommend "Private repos used all 2,000 free Actions minutes (X used) — review the private top-consumers below or move heavy workflows to public/self-hosted." Keep the "top 2 repos" recommendation but compute the share from private minutes when available. Add a storage recommendation when `private_gb_hours > 0.8 * allowance_gb_hours` (or when any repo's current artifact MB nears 500) suggesting artifact cleanup or retention reduction. When `filtered` is set and no private repos were scanned (`private_minutes == 0`), skip the private-quota recommendation — a partial slice is not evidence of quota pressure.
- `_print_impactful_findings()` (`report_summary.py:293`): when `larger_runner_skus` is non-empty, add a finding: "Larger-runner SKU(s) detected: X — always billed regardless of repo visibility." When a repo has `expiring_soon_count > 0` or `expired_count > 0`, add a storage finding: "N artifacts across R repo(s) expire within 7 days / are already expired."

### 4e. `render_actions_top_consumers()` (`report_actions.py:295`) / OS breakdown

No change — already visibility-annotated. (Optional: sort top-10 to prefer private repos on ties; defer — not required.)

### 4f. Forecast: `report_forecast_data.build_report_forecast()` (`report_forecast_data.py:16`) and `forecast.py:compute_forecast()`

`build_report_forecast` should feed **private** minutes/storage into `compute_forecast`:

```python
minutes = float(actions.get("private_minutes") or actions.get("minutes") or 0.0)
storage_avg_mb = float(actions.get("private_storage_avg_mb") or actions.get("storage_avg_mb") or 0.0)
```

Add an `extra` informational dict on the forecast result for public usage and the storage accrual (no limit/run-out): `report_forecast_data` appends `public_minutes`, `public_storage_avg_mb`, `private_gb_hours_projected`, `flat_equivalent_mb`; `render_forecast()` (`report_forecast.py:9`) and `_forecast_rows()` (`legacy_report_summary.py:165`) print a `public (free)` line when present. `compute_forecast` itself stays pure and unchanged. Guard: when `actions.get("filtered")` is true and `private_minutes == 0`, skip the projection or label it "scanned-private repos only — may understate"; never run a partial/empty private bucket against the 2,000 limit.

---

## Phase 5 — Email report

### 5a. `email_report_text.py` / `email_report_html.py` — "Private usage" + artifact summary

In the Actions consumers section (`_format_consumers_section` at `email_report_text.py:105`, `_format_html_consumers_section` at `email_report_html.py:127`), when `consumers.get("by_visibility")` exists, prepend a summary block **above the first visibility group header**:

```
Private repos:  2,181.3 min / 2,000 free (109%) · 227.5 MB avg storage
Public repos:   4,392.0 min (free)
Artifacts:      165.29 GB-hrs of 372 allowance (44.4%) · public 50.35 GB-hrs (free)
                (Retention: 90 days default; artifacts auto-expire.)
```

The consumers section already groups rows by visibility via `group_by_visibility` (shipped by the `2026-07-27-visibility-billing-docs` plan); the prepended block is a **totals summary above that grouped detail** — it does not replace the per-repo groups or double the visibility framing. HTML: small two-row table or muted `<span>`s, consistent with the existing `.visibility-tag` styling. Keep per-repo annotated lists as-is. When `by_visibility` is absent, render the current output unchanged.

### 5b. Insights

`get_key_insights()` (`report_data.py:198`) — when split keys are present on `actions`, prepend a private-focused insight when `private_minutes_percent >= 100`: e.g. `"Private repos used {percent:.0f}% of the 2,000 free Actions minutes this month."` (Keep existing top-consumer insight; both flow into `insights[:3]`.)

### 5c. Warnings

`_single_warning_state()` (`report_data.py:153`) percentage branch currently reads `actions["minutes_percent"]`. Switch to `private_minutes_percent` when present (fall back to `minutes_percent`). Dollar thresholds unchanged.

---

## Phase 6 — Exports

### 6a. CSV (`export_csv.py`)

Add an "Actions Usage by Visibility" section (rows: Private minutes / limit / %, Public minutes, Private storage avg MB, Public storage avg MB, Unattributed minutes) when `actions` has split keys. Artifact/storage sections gain accrued-GB-hrs and expiry columns per Phase 2f. SKU table rows gain a `larger_runner` marker column (or `*` suffix + legend).

### 6b. XLSX (`export_xlsx.py`)

Add a "Private Usage" sheet (or extend the existing Actions sheet) with the same rows plus a per-visibility SKU table (SKU, visibility, minutes, gross) when `repo_actions` sku data is available, and the artifact-retention fields from `storage_analysis`.

### 6c. PDF (`export_pdf.py`)

Add the visibility summary block and storage framing paragraph to `_write_consumers_page` (same data as CSV), annotate larger-runner SKUs in the SKU table if one exists there.

### 6d. JSON (`export_json.py`)

No transform needed — `actions` gains the split keys, `repo_consumers` gains `by_visibility`, and `storage_analysis`/`storage_summary` gain the artifact-retention fields automatically. Verify no export-time reshaping drops the new keys.

### 6e. Text (`export_text.py`)

Delegates to the email formatter — covered by Phase 5a.

---

## Phase 7 — TUI rows (`legacy_report_summary.py`)

- `_format_actions_minutes()` (`:27`): when `private_minutes` exists, format as `"Private 2,181.3 / 2,000 min (109.1%) · public 4,392.0 min (free)"` (keep combined fallback).
- `_format_actions_storage()` (`:41`): same private-first treatment, plus accrued GB-hrs framing when available.
- `_artifact_release_storage_rows()` (`:57`): annotate repo rows with expiry info (`"12 artifacts · 3 expire ≤7d"`) when `storage_analysis` carries it.
- `legacy_report_summary_rows()` / `legacy_report_detail_rows()` (`:376`, `:353`): no structural change; the formatters above feed them. Optionally add a `Public Actions minutes` row to the detail view when nonzero.

---

## Phase 8 — Report sources footer

Include a brief "Sources" summary with live-doc links so every report carries the authoritative references behind its claims.

### 8a. Data

Add a `sources` key to the report dict in `build_legacy_report_data` and `build_report_data`:

```python
report["sources"] = {
    "actions_billing": "https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions",
    "runner_pricing": "https://docs.github.com/en/billing/reference/actions-runner-pricing",
    "releases_storage": "https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases",
    "packages_billing": "https://docs.github.com/en/packages/learn-github-packages/about-github-packages",
}
```

(Constant dict `REPORT_SOURCES` in `usage_split.py` or `report_helpers.py`; reuse, don't duplicate.)

### 8b. Rendering

- **Legacy terminal:** a footer block in `render_legacy_report` (`legacy_terminal.py:30`) before the "End of Report v3" line:

  ```
  Sources:
    · Actions billing & free tier (private 2,000 min / 500 MB; public standard runners free; larger runners always billed):
      https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions
    · Runner pricing & larger-runner SKUs: https://docs.github.com/en/billing/reference/actions-runner-pricing
    · Release assets (separate, ≤2 GiB/file, no quota): https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
  ```

- **Email:** one-line "Sources" block at the end of both plain-text and HTML bodies (HTML: small muted list, reuse `.visibility-tag` styling).
- **Exports:** JSON includes `sources` automatically; CSV/XLSX/PDF add a trailing "Sources" section/sheet with the four URLs.

### 8c. Tests

- `tests/test_legacy_report_data.py` / `tests/test_report_data.py`: report dict contains `sources`.
- `tests/test_legacy_terminal.py`: sources footer rendered.
- `tests/test_email_report.py`: sources block present in text+HTML.
- `tests/test_export_*.py`: sources present in each export.

### 8d. Docs

CHANGELOG entry under `Added`: "Reports now include a Sources footer linking the GitHub billing, runner-pricing, and release-storage documentation behind the usage numbers." README: note the footer exists.

---

## Phase 9 — No config/CLI changes (unchanged)

No new flags, profile keys, workflow inputs, or wizard fields. This is automatic. Confirm `DEFAULT_EMAIL_REPORT` untouched, and that `scripts/docs-check` doesn't flag new undocumented user-visible options (there are none).

---

## Phase 10 — Tests

### 10a. New `tests/test_usage_split.py`

- `test_is_standard_runner_sku_standard` / `test_is_standard_runner_sku_larger` (e.g. `linux_4_core`, `actions_linux_4core`, `windows_8_core`)
- `test_normalize_sku_variants` — `actions_linux_4core` == `linux_4_core`
- `test_classify_actions_sku_storage` — `gigabyte-hours` unit
- `test_classify_actions_sku_unknown` — unknown compute SKU treated as larger
- `test_split_rows_by_visibility_aggregates_skus` — private/internal fold into private; sku quantities summed per visibility
- `test_split_rows_by_visibility_no_sku_key`
- `test_finalize_actions_split_reconciles_unattributed` — account > scanned; positive remainder
- `test_finalize_actions_split_clamps_negative_unattributed`
- `test_finalize_actions_split_larger_runner_skus_detected`
- `test_finalize_actions_split_filtered_flag`
- `test_storage_allowance_gb_hours` — 360 (30d) / 372 (31d)
- `test_flat_equivalent_gb_hours`

### 10b. Builder wiring

- `tests/test_legacy_report_data.py`: `test_build_legacy_report_data_attaches_visibility_split` — actions dict gains `private_minutes`/`public_minutes`/`larger_runner_skus`; `test_attach_actions_visibility_split_skips_when_actions_missing`; `storage_summary` block present with allowance framing.
- `tests/test_report_optional.py`: `get_repo_consumers` returns `by_visibility` with correct private/public totals.

### 10c. Renderers / summary / forecast

- `tests/test_report_actions.py`: limits summary uses private values + accrued GB-hrs line; summary section prints visibility block + `*` larger-runner footnote; `render_artifact_storage_section` output (allowance line, per-repo expiry annotations).
- `tests/test_report_actions_visibility.py` (already exists — covers the shipped visibility grouping): **extend**, don't duplicate its visibility assertions here; add the larger-runner annotation assertions to it.
- Larger-runner injection fixture: inject ≥2 larger SKUs (one x64 like `linux_4_core`, one arm64 like `linux_4_core_arm`) and assert (a) the `*` footnote renders in the legacy SKU table, (b) `_print_impactful_findings` emits the larger-runner finding, (c) the email artifact summary still renders.
- `tests/test_report_summary.py`: utilization bars from private values; visibility-split subsection; recommendation text when private minutes exceed quota; recommendation suppressed under `--only-public` (filtered guard); larger-runner finding; artifact expiry finding.
- `tests/test_report_forecast_data.py`: forecast fed from `private_minutes`/`private_storage_avg_mb`; public + accrual extras present; forecast skipped/labeled when `filtered` and `private_minutes == 0`.
- `tests/test_legacy_report_summary.py`: `_format_actions_minutes`/`_format_actions_storage` private-first strings; artifact rows annotated with expiry.
- `tests/test_storage.py`: Phase 2g additions.

### 10d. Email / warnings / insights / exports

- `tests/test_email_report.py`: text+HTML include the private-usage and artifact-storage block when `by_visibility` present; absent → unchanged output.
- `tests/test_report_data.py`: `_single_warning_state` uses private percent; `get_key_insights` private-quota insight.
- `tests/test_export_csv.py` / `test_export_xlsx.py` / `test_export_pdf.py`: new summary section/sheet present; JSON keeps split + storage keys.
- `tests/test_report_cache.py`: `CACHE_VERSION == 2` (update any assertion referencing version 1); additionally assert a stale v1 blob is **not** loaded even piecemeal (defensive against any path re-hydrating a single section). No cache-param change is needed — `legacy_cache_params`/`email_cache_params` already key the `--only-*` flags.

### 10e. Out of scope

- Live GitHub API calls.
- Per-SKU unattributed computation (documented best-effort remainder only).
- Calling `/actions/retention-settings` (retention derived from artifact `created_at`/`expires_at`; revisit if dates are absent in some environments).
- Cache-storage detail (separate 10 GB/repo pool, out of scope for the 500 MB artifact framing; surfaced separately only if the billing summary ever includes a cache SKU — see Phase 2a).

---

## Phase 11 — Documentation & changelog

### 11a. README

Document:

- Free-tier limits are reported against **private-repo usage** only; public usage shown as informational.
- Artifact-storage semantics: the 500 MB allowance is private-only, billed as GB-hours accrual (0.5 GB flat all month = 360/372 GB-hrs = full allowance); the report shows both accrued GB-hrs and a "flat all month" equivalent.
- Artifact retention defaults to 90 days (repo-adjustable via Settings → Actions → General); the report flags soon-to-expire / expired artifacts.
- Larger-runner SKUs are flagged as always-billed; attribution caveat (repos beyond `max_repos` land in "unattributed").

### 11b. CHANGELOG.md

Under `[Unreleased]`:

- **Added:** "Free-tier limit checks (Limits Summary, utilization bars, forecast) now measure **private-repo** Actions minutes/storage only; public-repo usage is shown separately as informational."
- **Added:** "Artifact storage is reported against the private 500 MB allowance as GB-hours accrual (0.5 GB flat all month = 360/372 GB-hrs), with current-vs-accrued per-repo data and artifact expiry/retention flags."
- **Added:** "Larger-runner SKUs (always billed, not covered by the free tier) are flagged in the Actions SKU breakdown and final summary."
- **Added:** "Reports include a **Sources footer** linking the GitHub billing, runner-pricing, and release-storage documentation behind the usage numbers."
- **Changed:** "Email reports include a private-vs-public Actions usage and artifact-storage summary; warnings and insights are computed from private usage."

### 11c. TO_DO.md

No completed items to remove (none in scope). No new items.

---

## Resolved decisions

1. **Private bucket = billable quota base.** `internal` folds into `private` in the billing aggregates (consistent with `filter_repos_by_visibility(only_private=True)`). The new "Usage by Visibility" blocks render **two** rows — Private (private+internal, annotated "(includes N internal repos)" when present) and Public — while the existing per-repo table keeps its three-group `group_by_visibility` rendering. This is a **deliberate, documented divergence**, not a silent inconsistency: billing rows show two buckets, the per-repo inventory keeps three groups.
2. **Account totals authoritative; per-repo split best-effort.** `unattributed = max(0, account − scanned)`, with a note; no per-SKU unattributed math.
3. **Larger-runner detection by exclusion.** Any compute (minutes-unit) SKU outside the documented standard set → "larger" (safe direction: larger runners are always billed). Normalized SKU matching (strip `actions_` prefix; `4core` ≡ `4_core` is a defensive guard, not a documented API variant). The `LARGER_RUNNER_ALIASES` map is display-only and best-effort — unmapped larger SKUs render as their raw SKU with the `*` marker.
4. **Split lives in `actions` dict** (legacy) and `repo_consumers.by_visibility` (email). Renderers fall back to combined values when split keys are absent (old fixtures/cache).
5. **No new CLI/config.** Automatic behavior. Cache version bumped to 2 for the new shape.
6. **`--only-*` filters** set `filtered=True`; renderers phrase as "scanned repos" and unattributed absorbs excluded usage. When `filtered` and `private_minutes == 0` (e.g. `--only-public`), quota math is suppressed or labeled — a partial/empty private slice is never presented as quota pressure.
7. **Forecast feeds private values**; `compute_forecast` stays pure; public shown as extras without run-out; forecast skipped or labeled "scanned-private repos only" under the decision-6 guard.
8. **Storage framing:** private artifact allowance = 500 MB expressed as `0.5 × hours` in GB-hrs (360 for 30-day, 372 for 31-day, 336 for 28-day February). Report shows accrued GB-hrs **and** the flat-all-month equivalent (which assumes full-cycle accrual). Public storage is free — always labeled as such. Cache storage (10 GB/repo, separate pool) is out of scope and never merged into the artifact framing.
9. **Current vs accrued kept separate.** Scan data (`storage_analysis`) is current storage; accrual comes only from billing. The artifact section explains both.
10. **Retention derived from artifact dates**, no extra API call. Default 90 days stated as a note, not fetched. `retention_days` uses the most recently created **non-expired** artifact so a stale retention window is never reported.

---

## Implementation order (recommended)

1. Phase 1 (`usage_split.py`) + 10a
2. Phase 3 data wiring (3a/3b/3d) + 10b
3. Phase 2 artifact storage (2b/2c data, 2d renderer, 2a-2 release split) + 2g + 10c (storage)
4. Phase 4 terminal + 10c
5. Phase 5 email + 5c warnings + 10d (email/insights/warnings)
6. Phase 6 exports + 10d (exports)
7. Phase 7 TUI + 10c (TUI)
8. Phase 8 sources footer + 8c/8d
9. Phase 9 confirmation + Phase 11 docs/changelog
10. `scripts/check`, `scripts/smoke`, `scripts/docs-check`

---

## Verification

Run after implementation:

- `scripts/check` — lint, type checks, tests, sizes (new module must stay under 150 lines; do not grow `report_actions.py`/`report_summary.py`/`storage.py` past budget — extract helpers into `usage_split.py` or a new `report_storage.py` as needed)
- `scripts/smoke` — CLI entrypoints unchanged, but run to confirm no parse regressions
- `scripts/docs-check` — README and changelog updated
- `./start.sh report` — confirm Limits Summary now shows private usage (~2,181/2,000, 109%) and public labeled free; artifact section shows the 372 GB-hr allowance framing, DICOMViewerV3's accrued storage marked free, release assets separated from artifacts, and the Sources footer links render at the end of the report
