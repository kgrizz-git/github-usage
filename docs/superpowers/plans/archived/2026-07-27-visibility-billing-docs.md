> **Status:** COMPLETE

# Visibility Billing Docs & Email Grouping

Three related changes: document the public-vs-private billing difference in the README and email reports, and add grouped-by-visibility sections to email reports (matching terminal behavior).

---

## Context

GitHub Actions minutes and storage are **free for public repos** but consume plan quotas for private repos. The codebase already distinguishes visibility (`--only-public`/`--only-private` flags, `[private]`/``[internal]` annotations), but:

1. The README doesn't explain *why* visibility matters for billing or link to the GitHub docs reference.
2. Email reports don't group repos by visibility into separate sections (only annotate tags).
3. Email reports contain no billing context note explaining the public/private difference.

---

## Phase 1 — README billing reference

**File:** `README.md` (near line 195)

Add a short paragraph after the existing visibility annotation sentence explaining that public repos have free Actions minutes and storage while private repos consume plan quotas, with a link to the GitHub Actions billing docs.

---

## Phase 2 — Email report billing context note

**Files:** `email_report_text.py`, `email_report_html.py`

Add a billing context note at the top of the email body (after the header, before the first data section) explaining:

- Public repos: Actions minutes and storage are free
- Private repos: minutes and storage count against your plan's monthly quota
- Link: https://docs.github.com/en/billing/concepts/product-billing/github-actions

### 2a. Plain-text (`email_report_text.py`)

Insert a new `_format_billing_context_section()` that returns the note as 3-4 lines. Add it to `_SECTION_FORMATTERS` at position 0 (first section after header).

### 2b. HTML (`email_report_html.py`)

Insert a matching `_format_html_billing_context_section()` with an `<h2>Billing Note</h2>` and `<p>` block. Add it to `_SECTION_HTML_FORMATTERS` at position 0.

---

## Phase 3 — Email report visibility grouping

**Files:** `email_report_text.py`, `email_report_html.py`

Change the consumer, artifact storage, and release asset section formatters from flat annotated lists to grouped-by-visibility sections with subtotals. Match the terminal report's "Private Repos:" / "Internal Repos:" / "Public Repos:" pattern.

### 3a. Plain-text (`email_report_text.py`)

Replace `_format_consumers_section()`:
- Use `group_by_visibility()` on `by_minutes` and `by_cost` lists
- If only 1 visibility group: render flat list (no regression for single-visibility accounts)
- If multiple groups: render each group with header, entries, and subtotal line
- Public repos get no tag (matching existing behavior); private/internal get `[private]`/`[internal]`

Same pattern for `_format_artifact_storage_section()` and `_format_release_assets_section()`.

### 3b. HTML (`email_report_html.py`)

Same grouping logic in `_format_html_consumers_section()`, `_format_html_artifact_storage_section()`, and `_format_html_release_assets_section()`. Use `<h3>` for group headers. Public repos get no visibility tag.

---

## Phase 4 — Tests

**File:** `tests/test_email_report.py`

- `test_billing_context_note_in_text_email()` — text body contains "Billing Note" and the GitHub docs link
- `test_billing_context_note_in_html_email()` — HTML body contains the same
- `test_consumers_grouped_by_visibility_text()` — mixed-visibility consumers produce "Private Repos:" / "Public Repos:" sections with subtotals
- `test_consumers_grouped_by_visibility_html()` — same for HTML
- `test_single_visibility_no_group_headers_text()` — all-public consumers render flat (no group headers)
- `test_single_visibility_no_group_headers_html()` — same for HTML
- `test_artifact_storage_grouped_by_visibility()` — text + HTML
- `test_release_assets_grouped_by_visibility()` — text + HTML

Update `tests/fixtures/email_report_data.json` with mixed-visibility repo entries (add `visibility` field to existing entries and add a second entry with different visibility).

---

## Phase 5 — Verification

- `scripts/check` — lint, type checks, tests
- `scripts/docs-check` — README and docs changes

---

## Implementation order

1. Phase 1 (README)
2. Phase 2 (billing context note in email)
3. Phase 3 (email visibility grouping)
4. Phase 4 (tests)
5. Phase 5 (verification)
