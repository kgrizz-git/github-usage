> **Status:** COMPLETE

> Line numbers are accurate as of 2026-07-22; relocate by anchor (function name + dict key) if they drift.

# Public/Private Repo Visibility Separation

Add visibility awareness (public/private/internal) to all repo-level report sections. Per-repo tables split into grouped sub-tables by visibility, and top-consumer / annotated lists tag each entry with its visibility. Complementary `--only-public` / `--only-private` CLI flags allow filtering repos entirely. Grouping/annotation is on by default; filters are opt-in.

The GitHub API already returns `visibility` (`"public"`, `"private"`, `"internal"`) and `private` (boolean) on every repo object from `GET /user/repos`. No additional API calls are needed for enrichment. Filter flags may optionally narrow the list request via the `visibility` query param (see Phase 6c).

**Scope note:** Email/export paths do **not** have a full per-repo Actions table, so they get **annotations** (and a `visibility` column/key where tabular), not grouped sub-tables. Grouped sub-tables apply to the legacy terminal `render_repo_actions_table()` only.

---

## Phase 1 — Data layer: carry visibility through repo processing

### 1a. `_limited_repos()` (`report_data.py:147`)

No visibility enrichment needed — already returns raw repo dicts which include `visibility` and `private`. Phase 6 may extend this helper with an optional API `visibility` query param for filter efficiency; that is separate from enrichment.

### 1b. Shared resolver (use everywhere below)

Do **not** inline fallbacks independently. Phase 2's `repo_visibility()` is the single source of truth:

```python
"visibility": repo_visibility(repo),
```

Until `visibility.py` exists, implement Phase 2 first (or land a tiny stub in the same PR as Phase 1). Every enrichment site must call `repo_visibility()`, not `row.get("visibility", "public")` alone — the bare default loses the `private` boolean fallback.

### 1c. `fetch_repo_actions_table()` (`report_actions.py:147`)

Add `"visibility"` key to each row dict (lines 164–173, inside `rows.append({...})`):

```python
"visibility": repo_visibility(repo),
```

### 1d. `fetch_actions_os_breakdown()` (`report_actions.py:177`)

Add `"visibility"` to each `repo_rows` entry (line ~193). Note the name key is `"name"` (not `"repo"`) in this structure.

### 1e. `get_repo_consumers()` (`report_optional.py:21`)

Add `"visibility"` to each row dict (line ~35).

### 1f. `get_artifact_storage_details()` (`report_optional.py:53`)

Add `"visibility"` to each row dict (line ~67).

### 1g. `get_release_asset_details()` (`report_optional.py:78`)

Add `"visibility"` to each row dict (line ~96).

### 1h. `get_storage_analysis()` (`storage.py:6`)

Add `"visibility"` to each repo_storage entry (line ~63). Storage rows use `"name"` for the repo full name.

### 1i. `derive_repo_consumers()` / `derive_artifact_storage()` / `derive_release_assets()` (`legacy_report_data.py`)

These functions build consumer/storage dicts from `repo_actions` and `storage_analysis`. Since visibility is now carried in those upstream dicts, propagate it into the derived rows:

- `derive_repo_consumers()`: include `"visibility": repo_visibility(row)` in each consumer row (lines 48–55).
- `derive_artifact_storage()`: add `"visibility": repo_visibility(repo)` to row dict (line ~90). Upstream key is `repo["name"]`.
- `derive_release_assets()`: add `"visibility": repo_visibility(repo)` to row dict (line ~111).

---

## Phase 2 — Visibility helpers

Create `src/github_usage/visibility.py` with a small pure module (target: under ~60 lines):

```python
VISIBILITY_ORDER = ["private", "internal", "public"]

def repo_visibility(repo: dict, key: str = "visibility") -> str:
    """Resolve visibility from a GitHub repo or enriched row dict.

    Prefer an explicit ``visibility`` string. If missing, infer from the
    ``private`` boolean (``True`` → ``"private"``, else ``"public"``).
    On GHES without ``visibility``, internal repos may appear as private —
    best-effort (see Resolved decisions).
    """
    raw = repo.get(key)
    if isinstance(raw, str) and raw:
        return raw
    return "private" if repo.get("private") else "public"

def group_by_visibility(rows: list[dict], key: str = "visibility") -> dict[str, list[dict]]:
    """Group rows by visibility: private, internal, public, then any unknown keys."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        vis = repo_visibility(row, key=key)
        groups.setdefault(vis, []).append(row)
    result = {v: groups[v] for v in VISIBILITY_ORDER if v in groups}
    for vis, items in groups.items():
        if vis not in result:
            result[vis] = items
    return result

def visibility_label(visibility: str) -> str:
    """Return a display suffix like ``' [private]'``, or ``''`` for public."""
    if visibility == "public":
        return ""
    return f" [{visibility}]"

def filter_repos_by_visibility(
    repos: list[dict],
    *,
    only_public: bool = False,
    only_private: bool = False,
) -> list[dict]:
    """Filter repos by visibility. No-op when neither flag is set.

    ``only_private`` includes both ``private`` and ``internal``.
    Callers must not set both flags (CLI/GUI enforce mutual exclusion).
    """
    if only_public:
        return [r for r in repos if repo_visibility(r) == "public"]
    if only_private:
        return [r for r in repos if repo_visibility(r) in ("private", "internal")]
    return repos
```

**Label spacing:** `visibility_label` includes the leading space so callers can write `f"{full}{visibility_label(vis)}"` and get `owner/repo [private]` (not `owner/repo[private]`). Public returns `""` so no trailing space appears.

`filter_repos_by_visibility` lives here from the start (used in Phase 6); no need to split across phases.

---

## Phase 3 — Terminal rendering (group/split)

### 3a. `render_repo_actions_table()` (`report_actions.py:231`)

Replace the single flat table with grouped sub-tables:

```
  Per-Repository Actions Breakdown
  ─────────────────────────────────────────────────────────────

  Private Repos:
  REPO                                          MINUTES    GB-HRS     AVG MB      GROSS
  ───────────────────────────────────────────── ────────── ────────── ────────── ──────────
  owner/private-repo                               123.4     0.0012      15.2     $0.25
  ───────────────────────────────────────────── ────────── ────────── ────────── ──────────
  SUBTOTAL                                         123.4     0.0012      15.2     $0.25

  Internal Repos:
  REPO                                          MINUTES    GB-HRS     AVG MB      GROSS
  ───────────────────────────────────────────── ────────── ────────── ────────── ──────────
  org/internal-repo                                 25.0     0.0003       4.0     $0.05
  ───────────────────────────────────────────── ────────── ────────── ────────── ──────────
  SUBTOTAL                                           25.0     0.0003       4.0     $0.05

  Public Repos:
  REPO                                          MINUTES    GB-HRS     AVG MB      GROSS
  ───────────────────────────────────────────── ────────── ────────── ────────── ──────────
  owner/public-repo                                 50.0     0.0005       8.1     $0.10
  ───────────────────────────────────────────── ────────── ────────── ────────── ──────────
  SUBTOTAL                                           50.0     0.0005       8.1     $0.10

  ───────────────────────────────────────────── ────────── ────────── ────────── ──────────
  TOTAL                                            198.4     0.0020      27.3     $0.40
```

Use `group_by_visibility()` from Phase 2. If only one visibility group exists, skip the group header / SUBTOTAL rows and render the existing flat table (no visual regression for users with only one type). Groups appear in order: private, internal, public.

Extract a small private helper (e.g. `_print_repo_actions_group(rows, *, show_subtotal: bool)`) so the multi-group path does not duplicate the column-format loop.

### 3b. `render_actions_top_consumers()` (`report_actions.py:254`)

Annotate each entry with visibility tag (top-N list — annotate, do not regroup):

```
  Top 10 Repos by Actions Minutes

    123.4 min |    15.2 MB | owner/private-repo [private]
     50.0 min |     8.1 MB | owner/public-repo
```

### 3c. `render_actions_os_breakdown()` (`report_actions.py:264`)

Annotate repo names with visibility tags in the per-repo OS breakdown list (`row["name"]` + `visibility_label(repo_visibility(row))`). *(Depends on Phase 1d.)*

### 3d. `render_final_summary_from_data()` (`report_summary.py:61`)

This function builds `repo_data` as a list of **tuples** `(full, minutes, storage_gb_hours, avg_mb, gross, sku)` from `data["repo_actions"]` (lines 71–80). The tuples are then passed by positional index to `_print_top_consumers()`, `_print_impactful_findings()`, and `_print_recommendations()`.

**Approach:** Rather than changing the tuple shape (which would require updating every unpack site), build a `visibility_by_repo: dict[str, str]` lookup from `data["repo_actions"]` at the top of `render_final_summary_from_data()`, and pass it down to helpers that annotate Actions repo names:

```python
visibility_by_repo = {
    row["repo"]: repo_visibility(row)
    for row in (data.get("repo_actions") or [])
}
```

Pass `visibility_by_repo` to `_print_top_consumers()`, `_print_impactful_findings()`, and `_print_recommendations()`. Format as `f"{full}{visibility_label(visibility_by_repo.get(full, 'public'))}"`.

**Storage is different:** `_print_storage_breakdown()` should **not** rely on `visibility_by_repo` from Actions. Read `visibility` from each storage repo dict via `repo_visibility(r)` so storage-only repos (no Actions minutes) stay correct. Signature can stay storage-only; no need to thread the Actions lookup into this helper.

Apply the same optional lookup to the standalone `show_final_summary()` function (line 10): add `visibility_by_repo: dict[str, str] | None = None`; when `None`, skip annotation (backward compatible). *Note: `show_final_summary()` has no active call sites in `src/` (only legacy re-exports and unit tests); adding the optional param is defensive — verify with `rg 'show_final_summary\('` before adding. Prefer skipping the param entirely if tests are the only callers and can be updated later.*

Changes by helper function:

- **`_print_top_consumers()`** (line 143): Add `visibility_by_repo` param. In the "Actions Minutes" and "Actions Cost" loops (lines 150, 160), annotate repo names.
- **`_print_storage_breakdown()`** (line 200): Annotate from storage dicts via `repo_visibility(r)` in the storage table (line 211) and top consumer line (line 216). Do not take `visibility_by_repo`.
- **`_print_impactful_findings()`** (line 263): Add `visibility_by_repo` param. Annotate `top_repo[0]` (line 287) and `top_cost[0]` (line 294). Storage findings in this function should use storage-row visibility when present.
- **`_print_recommendations()`** (line 325): Add `visibility_by_repo` param. Annotate repo names in recommendation text.

### 3e. Legacy terminal sections (`legacy_terminal.py`)

No changes needed — it delegates to the renderers above.

### 3f. `legacy_report_summary.py` TUI rows

`_repo_rows()` (line 255) and `legacy_report_consumer_rows()` (line 387) read from `data["repo_consumers"]`, which carries `visibility` after Phase 1i. Annotate repo names in these functions:

- **`_repo_rows()`**: In the "by_minutes" loop (line 264–268) and "by_cost" loop (line 272–276), append `visibility_label(repo_visibility(item))` to the `repo` string. Also annotate `_repo_billed_storage_rows()` (line 83) and artifact storage entries (line 290–293).
- **`legacy_report_consumer_rows()`**: In the consumer loop (line 391–394), append the visibility label to the `repo` string.

Both functions produce `(label, value)` tuples for TUI tables, so the annotation goes into the label string.

### 3g. Key insights (`get_key_insights` in `report_data.py:197`)

When the insight string names a top consumer repo (line ~207), append `visibility_label(repo_visibility(top))` so email/terminal insight lines stay consistent with annotated lists.

---

## Phase 4 — Email report rendering

Email has no full per-repo Actions table — **annotate only** (no grouped sub-tables).

### 4a. Plain-text email (`email_report_text.py`)

In the section formatters (`_format_consumers_section()` line 82, `_format_artifact_storage_section()` line 104, `_format_release_assets_section()` line 119): annotate each repo entry with `visibility_label(...)` (public → no tag).

### 4b. HTML email (`email_report_html.py`)

Same annotation approach in `_format_html_consumers_section()` (line 98), `_format_html_artifact_storage_section()` (line 133), and `_format_html_release_assets_section()` (line 155). Wrap the tag in a muted span, e.g. `<span class="visibility-tag">[private]</span>` (HTML can omit the leading space and put spacing in CSS/`&nbsp;` as needed).

Add CSS to `_HTML_DOCUMENT_HEAD` styles (near `.meta`):

```css
.visibility-tag { color: #656d76; font-weight: normal; }
```

---

## Phase 5 — Export formats

### 5a. CSV (`export_csv.py`)

Add a `"visibility"` column to the "Top Repos by Minutes" and "Top Repos by Cost" sections (after `repo`, before `minutes`/`gross`). Also add to "Artifact Storage" and "Release Assets" sections (after `repo`).

### 5b. XLSX (`export_xlsx.py`)

Add `"visibility"` column to the same repo-level sheets/sections as CSV.

### 5c. PDF (`export_pdf.py`)

Add visibility annotation to repo names in `_write_consumers_page`, `_write_artifact_storage_page`, and the release-assets page helper (annotate labels; PDF has no separate visibility column today).

### 5d. JSON (`export_json.py`)

`export_json` largely serializes the report dict as-is. Once Phase 1 puts `"visibility"` on consumer/storage/release rows, JSON picks it up automatically — **verify** rather than adding a parallel transform. If any export-time reshaping drops unknown keys, preserve `visibility`.

### 5e. Text (`export_text.py`)

Delegates to text email formatter — handled by Phase 4a. Note: `export_text.write` calls `email_report.format_report_email`, which re-exports `email_report_text.format_report_email` (`email_report.py:12`). No additional code change is needed; verify the re-export still points at the modified function after Phase 4a.

---

## Phase 6 — Filter flags (`--only-public` / `--only-private`)

### 6a. CLI parsers (`cli_parsers.py`)

Add to `_email_parser()` via `add_mutually_exclusive_group()` (same pattern as `--api`/`--diff` in `_runs_parser()`):

- `--only-public` — include only public repos in repo-level sections
- `--only-private` — include only private + internal repos in repo-level sections

Add to `_legacy_parser()`: same mutually exclusive pair.

Also extend `_validate_email_flags()` (or equivalent) only if mutual exclusion is not fully handled by argparse (it should be). Document both flags in the module/CLI help text that `scripts/docs-check` / smoke cover.

### 6b. Filtering (already in `visibility.py` from Phase 2)

Use `filter_repos_by_visibility()`. No second copy of the filter logic.

### 6c. `build_report_data()` (`report_data.py:282`)

Accept `only_public: bool = False` and `only_private: bool = False` kwargs.

Apply filtering **after** `_limited_repos()` returns (line ~301):

```python
repos = filter_repos_by_visibility(
    repos, only_public=only_public, only_private=only_private
)
```

Do **not** thread the flags into `_fetch_sections()` — filtering the `repos` list before the call is sufficient.

**`max_repos` interaction (accepted limitation):** `_limited_repos` truncates first, then the filter runs on that slice. A user with `max_repos=100` and `--only-private` may get fewer than 100 private repos if the first 100 API results were mixed. Document this in README (Phase 9).

**Optional efficiency (same change set if small):** when `only_public` / `only_private` is set, teach `_limited_repos` to pass GitHub's `visibility=public` or `visibility=private` query param **instead of** `type=all` (GitHub rejects combining `type` with `visibility`). Client-side `filter_repos_by_visibility` remains as a safety net (`visibility=private` can still include internal in some enterprise responses). Skip this API tweak if it complicates `_limited_repos` beyond a few lines — client-side filter alone is correct under the documented limit caveat.

### 6d. Cache keys (`report_cache.py`)

Update the param builders (not ad-hoc dicts at call sites):

- `email_cache_params()` — add `only_public: bool = False`, `only_private: bool = False` to the returned params dict.
- `legacy_cache_params()` — same.

Then thread the flags into every caller of those helpers (`cli_email_report.py`, `legacy_report.py`, `gui_backend.py`, tests). Filtered reports must not collide with unfiltered cache entries.

### 6e. `build_legacy_report_data()` (`legacy_report_data.py:190`)

Accept the filter flags, apply after `_limited_repos()` returns (line ~206).

### 6f. Email CLI path (`cli.py`, `cli_email_report.py`)

Thread `only_public` / `only_private` from CLI args through `email_cache_params(...)` and `build_report_data(...)`.

### 6g. Legacy CLI path (`cli.py`, `legacy_report.py`)

- Add kwargs to `run_legacy_report_session(...)`.
- Pass them from `_run_legacy_report` via `getattr(args, "only_public", False)` / `only_private`.
- Include them in `legacy_cache_params(...)` and `build_legacy_report_data(...)`.

### 6h. Profile config (`setup_config.py`)

`setup_config.py` is already over the size budget (see `TO_DO.md`). Keep additions minimal — a few keys/lines only; do not expand into new abstractions unless extracting is already in scope.

1. Add to `DEFAULT_EMAIL_REPORT`:
   ```python
   "only_public": False,
   "only_private": False,
   ```
2. Emit in `_emit_email_report_block()` (TOML writer) — required so `write_config` / setup persist the keys:
   ```toml
   only_public = false
   only_private = false
   ```
3. Emit CLI flags from `_email_flags_from_dict()`:
   ```python
   if email.get("only_public"):
       args.append("--only-public")
   if email.get("only_private"):
       args.append("--only-private")
   ```
4. Emit the same from `profile_workflow_extra_args()` (line 389) — this function does **not** call `_email_flags_from_dict()`, so it must be updated separately (mirror `skip_actions` / `skip_copilot` / `skip_lfs` at lines 404–409).

`email_report_args()` automatically picks up (3) via `_email_flags_from_dict()` — no separate change.

If both config keys are somehow `true` (hand-edited TOML), prefer failing at CLI parse time when flags are expanded, or treat as invalid in wizard validation (`validate_options`). Do not silently prefer one.

### 6i. GUI / wizard

Correct targets (previous draft pointed at the wrong view for profile toggles):

- `gui/views/setup_profiles_panel.py` — add mutually exclusive-ish checkboxes (or a single select) for only-public / only-private; wire into `collect_options()` / `load_profile()` alongside existing include_* checkboxes.
- `gui/wizard/setup_wizard_flow.py` — add fields on `WizardData`; load/save via `save_options_step`; mention in `review_summary`; reject both-true in `validate_options`.
- `gui/wizard/setup_wizard_screen.py` — add UI controls on the options step; sync like other checkboxes.
- `gui/views/report_view.py` — **no new toggles** (it only reads profile defaults for forecast). Confirm `DEFAULT_EMAIL_REPORT` merge still works when new keys appear; no UI change required unless report-run options are later expanded.
- `gui_backend.py` — verify profile → CLI arg expansion via `email_report_args()` surfaces the new flags (lines ~165, 427, 447).
- `setup_wizard.py` — verify dry-run path still works once flags exist in config (line ~91).

UX: selecting both must be impossible or immediately rejected with a clear message (match CLI mutual exclusion).

### 6j. Workflow template

Update `.github/workflows/email-report.yml.template` with `only_public` / `only_private` `workflow_dispatch` inputs (default `false`) and shell blocks mirroring include_* flags. Mirror into the live `.github/workflows/email-report.yml` **or** regenerate via `setup_workflow.py` from the template — do not leave template and live workflow divergent.

Note: profile `__PROFILE_ARGS__` will also carry the flags once `profile_workflow_extra_args` is updated; workflow inputs are for one-off dispatch overrides. Prefer the same “inputs OR profile args” composition style used for include_* today — avoid emitting duplicate contradictory flags.

---

## Phase 7 — Configuration defaults (summary)

- Grouping/annotation (Phases 3–5) is always on. Single-visibility tables look unchanged (no group headers).
- `--only-public` / `--only-private` default to `False` (opt-in).
- Defaults live in `DEFAULT_EMAIL_REPORT` (Phase 6h); do not duplicate that block elsewhere in the plan/implementation notes.

---

## Phase 8 — Tests

Map each change to an existing test module where one already covers that surface. Prefer extending fixtures/assertions over parallel duplicate suites. Do **not** add heavy Textual GUI widget tests; cover wizard/config logic at the pure-function layer instead.

### 8a. Unit tests for `visibility.py` → new `tests/test_visibility.py`

- `test_repo_visibility_prefers_field()`
- `test_repo_visibility_falls_back_to_private_bool()`
- `test_group_by_visibility_mixed()` — three groups in order
- `test_group_by_visibility_all_public()` — single group
- `test_group_by_visibility_empty()`
- `test_group_by_visibility_unknown_value()` — unknown keys after standard groups
- `test_visibility_label_private()` — returns `" [private]"` (leading space)
- `test_visibility_label_public()` — returns `""`
- `test_filter_repos_by_visibility_only_public()`
- `test_filter_repos_by_visibility_only_private_includes_internal()`
- `test_filter_repos_by_visibility_neither()` — no-op
- `test_filter_repos_by_visibility_uses_private_fallback()` — repo missing `visibility` but `private=True` kept by only-private

### 8b. Data layer enrichment

| File | What to assert |
|---|---|
| `tests/test_report_actions.py` | `fetch_repo_actions_table` / `fetch_actions_os_breakdown` rows include `visibility` from the source repo |
| `tests/test_report_optional.py` | consumer / artifact / release row dicts include `visibility` |
| `tests/test_storage.py` | storage analysis repo entries include `visibility` |
| `tests/test_legacy_report_data.py` | extend `test_derive_repo_consumers_from_repo_actions` and `test_derive_artifact_storage_from_storage_analysis` (and release-assets derive if covered) so derived rows propagate `visibility` |

### 8c. Builder-level filter tests (not only CLI)

Add (or extend) cases that call the builders with mocked repos — do not rely solely on parser tests:

| File | Cases |
|---|---|
| `tests/test_report_data.py` | `test_build_report_data_only_public_filters_repos()` / `test_build_report_data_only_private_includes_internal()` — stub `_limited_repos` (or the API page) with mixed visibility; assert only matching repos reach consumers/artifact collectors |
| `tests/test_legacy_report_data.py` | `test_build_legacy_report_data_only_public_filters_repos()` / `test_build_legacy_report_data_only_private_includes_internal()` — same idea for `repo_actions` / storage inputs |

Also extend `test_get_key_insights_reports_top_repo_share_when_consumers_present` (or add sibling) so the insight string includes the visibility label when the top consumer is non-public.

### 8d. Renderer / terminal / TUI tests

| File | Cases |
|---|---|
| `tests/test_report_actions.py` | `test_render_repo_actions_table_groups_by_visibility()` — group headers + SUBTOTAL + TOTAL; `test_render_repo_actions_table_single_visibility()` — flat, no group headers/subtotals; `test_render_actions_top_consumers_annotates_visibility()`; `test_render_actions_os_breakdown_annotates_visibility()` — Phase 3c (`row["name"]` + label) |
| `tests/test_report_summary.py` | `test_final_summary_annotates_visibility()` — Actions paths via `visibility_by_repo`; storage lines via storage-row visibility (include a storage-only private repo with no Actions row) |
| `tests/test_legacy_report_summary.py` | `test_repo_rows_annotates_visibility()` / `test_legacy_report_consumer_rows_annotates_visibility()` (and billed-storage / artifact labels if those helpers are already tested) |

### 8e. CLI / parser / config / cache / workflow / wizard

| File | Cases |
|---|---|
| `tests/test_cli_parsers.py` | `test_email_only_public_and_only_private_mutually_exclusive()`; `test_legacy_only_public_and_only_private_mutually_exclusive()`; happy-path parse for each flag alone on both parsers |
| `tests/test_setup_config.py` | `_email_flags_from_dict` / `email_report_args` emit `--only-public` / `--only-private`; `profile_workflow_extra_args` emits them independently; `_emit_email_report_block` / `write_config` persist `only_public` / `only_private`; `DEFAULT_EMAIL_REPORT` defaults both to `False` |
| `tests/test_report_cache.py` | `email_cache_params` / `legacy_cache_params` include the flags; filtered vs unfiltered params produce **distinct** cache paths |
| `tests/test_workflow_templates.py` | Extend `test_email_report_workflow_uses_safe_secret_names_and_dispatch_inputs` (or sibling): template contains `only_public:` / `only_private:` inputs and `--only-public` / `--only-private` shell wiring |
| Wizard flow | Add focused unit tests for `gui/wizard/setup_wizard_flow.py` `validate_options` rejecting both-true, and for load/save of the new `WizardData` fields (new small test module or extend an existing GUI/helpers test — **not** a full Textual screen run). Pure `validate_options` is enough if save/load is covered via config round-trip. |

Skip full Textual checkbox interaction tests for `setup_profiles_panel.py` / `setup_wizard_screen.py` unless the repo already has a cheap pattern for that panel; config + `validate_options` + CLI flag emission cover the risk.

### 8f. Export tests

| File | Cases |
|---|---|
| `tests/test_export_csv.py` | `visibility` column present (after `repo`) in Top Repos by Minutes/Cost, Artifact Storage, and Release Assets sections; values match fixture rows |
| `tests/test_export_xlsx.py` | same columns on the corresponding sheets |
| `tests/test_export_pdf.py` | repo labels in consumers / artifact / release pages include ` [private]` / ` [internal]` where expected; public repos untagged |
| `tests/test_export_json.py` | repo-level consumer/storage/release objects retain `"visibility"` from the report dict (no silent key drop) |
| `tests/test_export_text.py` | only if it asserts body content today — otherwise covered by email formatter tests via the re-export |

### 8g. Email formatter tests → `tests/test_email_report.py`

- Text body: private/internal consumer (and artifact/release) lines include the visibility label; public lines do not
- HTML body: same annotations; output includes `class="visibility-tag"` (and the CSS rule is present in the document head)
- Prefer extending existing `test_format_report_email_renders_plain_text_sections` / `test_format_html_report_renders_html_sections` fixtures with mixed-visibility repos rather than only adding isolated micro-tests

### 8h. Out of scope for this plan’s tests

- Optional API `visibility=` query param on `_limited_repos` (nicety) — if implemented, one small unit test on the request params is enough; not required for merge
- Live GitHub API calls
- Full GUI screenshot / Textual pilot runs for the new checkboxes

---


## Phase 9 — Documentation and changelog

### 9a. README

Document:

- Visibility grouping is automatic for the legacy per-repo Actions table; lists elsewhere annotate `[private]` / `[internal]`
- `--only-public` and `--only-private` filter flags (mutually exclusive)
- Config equivalents in `[email_report]`
- Caveat: filters apply to the post-`max_repos` slice (may return fewer than `max_repos` matches)

### 9b. Example config

Update `.github-usage/config.example.toml` with `only_public` and `only_private`.

### 9c. CHANGELOG.md

Add under `[Unreleased] > Added`:

- "Per-repo Actions tables now group entries by visibility (public/private/internal) with subtotals"
- "Repo lists annotate non-public visibility; CSV/XLSX/JSON include a visibility field"
- "Added `--only-public` and `--only-private` flags to filter repos in repo-level report sections"

### 9d. TO_DO.md

No visibility items currently exist in `TO_DO.md` — nothing to remove unless one is added during implementation. Do not invent a completed checkbox.

---

## Resolved decisions

1. **Grouping always on** — No `--group-by-visibility` toggle. When only one visibility type exists, the Actions table matches today's flat layout (no group headers / subtotals).
2. **Internal repos distinct in rendering** — Own "Internal Repos:" sub-table. **`--only-private` includes `"internal"`** (filter semantics). Matches `VISIBILITY_ORDER`.
3. **Visibility tag on public repos** — No tag. Only `[private]` and `[internal]` (with leading space in text UIs).
4. **Mutually exclusive filters** — argparse `add_mutually_exclusive_group`. Config/GUI must not allow both true.
5. **Visibility field fallback** — Centralized in `repo_visibility()`. Missing `visibility` → infer from `private` bool. GHES without `visibility` may bucket internal under private — acceptable / best-effort.
6. **Subtotals in grouped tables** — Per-group SUBTOTAL; grand TOTAL at bottom. Omitted when only one group (flat table).
7. **Summary annotation via lookup** — Actions helpers use `visibility_by_repo`; storage helpers read visibility from storage dicts.
8. **Email/exports annotate, legacy Actions table groups** — Email has no full per-repo Actions table.
9. **Filter vs `max_repos`** — Filter after limit. Documented caveat; optional API `visibility=` query is a nicety, not required for correctness.
10. **Cache keys** — Always via `email_cache_params` / `legacy_cache_params`.
11. **Label helper owns spacing** — `visibility_label` returns `" [private]"` or `""`.

---

## Implementation order (recommended)

1. Phase 2 (`visibility.py`) + Phase 8a tests
2. Phase 1 enrichment + 8b
3. Phase 6 filter wiring in builders (6c/6e minimally) + 8c builder filter tests — can land ahead of full CLI/GUI if kwargs are present
4. Phase 3 terminal/TUI + 8d renderer tests (+ insights assertion in 8c)
5. Phase 4 email + Phase 5 exports + 8f/8g
6. Phase 6 remainder (parsers, config, cache, GUI, workflow) + 8e
7. Phase 7 confirmation + Phase 9 docs/changelog
8. `scripts/check`, `scripts/smoke` (after 6a), `scripts/docs-check` (after 9)

---

## Verification

Run after implementation:

- `scripts/check` — lint, type checks, tests, sizes (`setup_config.py` is already over budget; avoid growing it more than the few lines this feature needs)
- `scripts/smoke` — after CLI entrypoint/parser changes (Phase 6a)
- `scripts/docs-check` — after README, CLI help text, docs, and workflow template changes (Phase 9)
