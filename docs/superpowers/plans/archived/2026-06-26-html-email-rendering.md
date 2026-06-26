# Plan: HTML email rendering for `--email-format html`

> **Status:** COMPLETE
>
> Implemented and merged 2026-06-26 (commit `f0b71a6`).

**Date:** 2026-06-26

## Objective

Unblock the `--email-format html` option by adding an HTML rendering path to the email report system. The `--email-format` flag already accepts `"html"` as a choice; the CLI currently rejects it with `"html is not yet supported."` This plan implements a full HTML email body renderer and wires it through the email dispatch flow.

## Motivation

The `--email-format text|html` flag was added to `cli_parsers.py` with HTML rendering deferred. The plain-text formatter in `email_report.format_report_email()` is stable. Users want rich HTML emails for better readability in email clients.

## Current State

- `cli_parsers.py:52` — `--email-format` accepts `("text", "html")` with default `"text"`.
- `cli.py:153-155` — `_validate_email_flags()` blocks `html` with an error message.
- `cli.py:42` — HELP string says `html deferred`.
- `email_report.py` — Contains `format_report_email()` (plain-text) and `send_email()` (Resend, sends `text` field only).
- Resend API supports both `text` and `html` fields on the email payload.

## Definition of Done

- `scripts/check` exits 0
- `scripts/smoke` exits 0
- `scripts/docs-check` exits 0
- All new tests pass; no existing tests start failing (the planned `test_email_report_html_format_errors` → `test_email_report_html_format_success` rename in Phase 2a is the only allowed change to an existing test, and the renamed test must pass)
- Manual dry-run produces an HTML body for `--email-format html`
- Manual dry-run produces a plain-text body for the default format
- `./start.sh setup --print-args` includes `--email-format html` (or `text`) when the persisted `config.toml` sets `email_format` accordingly, confirming the setup wiring round-trips
- `CHANGELOG.md` and `TO_DO.md` are updated; the plan is archived with the canonical `> **Status:** COMPLETE` banner

## Design Decisions

### Wrapper vs section formatters

Mirroring `format_report_email()`, the `format_html_report()` wrapper handles three things directly (outside `_SECTION_HTML_FORMATTERS`):
1. The report header (username, generated date, period)
2. Warnings (styled as a highlighted alert box)
3. REST API Quota Notes (footnote-style)

The per-section formatters in `_SECTION_HTML_FORMATTERS` handle only the individual data sections. Their element order **must match** `_SECTION_FORMATTERS`.

### Period text

The data dict carries `period: "current_month"` (with an underscore; see `report_data.py:255`). The plain-text formatter hardcodes the literal string `"Period: current month"` (with a space) — `format_html_report()` must match this literal to stay consistent with the plain-text body, not surface the raw `current_month` value.

### Helper-function strategy

- **Reuse as-is:**
  - `_bytes_to_mb()` (line 29) — the HTML formatter wraps its return value in a `<td>`.
  - `fmt_price()` (from `report_helpers`) — output is inherently safe to insert into HTML without additional escaping.
- **Add HTML counterpart:**
  - `_cost_line()` (line 33) — the HTML path needs a corresponding `_html_cost_line()` helper that returns a table row string fragment (called by `_format_html_monthly_costs_section()`).
- **Inline in wrapper:**
  - `_generated_line()` (line 17) — used directly by `format_report_email()` (the wrapper), not inside a section formatter. Its HTML equivalent is inlined directly inside `format_html_report()` (wrapping the output in a `<span class="meta">` element), not extracted into a separate helper.

### Size budget

`email_report.py` is currently 248 lines. The nine `_format_html_*_section()` functions plus the wrapper and tuple will add roughly 120-160 lines, keeping the file well under the 500-line soft limit. If a section formatter exceeds ~30 lines, factor a small inner helper rather than letting one function balloon. `cli.py` grows by only a handful of lines and stays under 400.

`setup_wizard.py` is currently 534 lines and already over the 500-line soft limit (the broader refactor is tracked as a `TO_DO.md` item — split into focused submodules). The new `email_format` prompt in `_configure_email_options()` adds only ~5-10 lines and lives at the natural home for the email-report knobs. Do not extract a new module as part of this plan; the prompt is small enough to inline. The plan intentionally does not address the broader `setup_wizard.py` split — that is a separate, pre-existing concern with its own scope.

### HTML escaping — required

All user-supplied and untrusted data interpolated into the HTML output must be escaped using `html.escape()` from Python's standard library (default `quote=True`, which escapes `<`, `>`, `&`, `"`, and `'`). This includes:
- `username` (header)
- `repo` names (consumers, artifact storage, release assets)
- `insight` strings (key insights)
- `warning` strings
- `model` names (copilot by-model breakdown)
- `section` / `message` strings (unavailable data errors)
- `note` strings (REST API quota notes)

Without escaping, a repo name like `org/foo&bar` would produce invalid HTML. Add `import html` to `email_report.py` for `html.escape()`.

### Email-client CSS

Some email clients (Gmail mobile app, Outlook on Windows) strip `<style>` blocks in `<head>`. For production, use inline `style` attributes on elements (e.g., `<td style="padding: 6px 10px; border: 1px solid #d0d7de;">`) or run the output through a CSS-inliner like `premailer`. For this first pass, the `<style>` block in `<head>` is acceptable for most modern clients.

### HTML5 void elements in the well-formed-HTML test

The plan renders `<meta charset="utf-8">` (and may render other void elements like `<br>`, `<hr>`, `<link>`, `<img>`, `<input>` if any future section uses them). Python's stdlib `html.parser.HTMLParser` does **not** know about HTML5 void elements by default — `handle_startendtag` is only called for XHTML-style `<foo />` self-closing tags, not HTML5 void elements. The `test_format_html_report_well_formed_html` test must therefore use a custom `HTMLParser` subclass that maintains a tag stack and treats the standard HTML5 void set as self-closing (no push to the stack on `handle_starttag`, no expectation of a matching `handle_endtag`):

```python
from html.parser import HTMLParser

VOID_ELEMENTS = frozenset({"area", "base", "br", "col", "embed", "hr",
                            "img", "input", "link", "meta", "source",
                            "track", "wbr"})

class _WellFormedHTMLValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str):
        if tag in VOID_ELEMENTS:
            return
        if not self.stack:
            raise AssertionError(f"Unexpected close tag: </{tag}>")
        expected = self.stack.pop()
        if expected != tag:
            raise AssertionError(f"Mismatched tag: expected </{expected}>, got </{tag}>")
```

The test feeds `format_html_report(data)`'s output to this validator; if parsing raises (or the stack is non-empty at end-of-input), the test fails. Without the void-element allowlist the test would fail on its own example output (`<meta charset="utf-8">` in the `<head>` of every report).

## Proposed Implementation

### 1. Add `format_html_report()` to `email_report.py`

Create a new function `format_html_report(data: dict) -> str` that renders the same report data as an HTML document. The HTML should be self-contained (inline styles, no external CSS) and responsive.

Each `_format_*_section()` function in `email_report.py` should get a corresponding `_format_html_*_section()` that returns a list of HTML string fragments. A new `_SECTION_HTML_FORMATTERS` tuple drives the generation — its element order **must match** `_SECTION_FORMATTERS`.

The HTML structure mirrors the plain-text sections:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>GitHub Usage Report</title>
  <style>
    /* inline-friendly: minimal, self-contained */
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; margin: 0; padding: 20px; color: #24292f; }
    h1 { font-size: 20px; border-bottom: 1px solid #d0d7de; padding-bottom: 8px; }
    h2 { font-size: 16px; margin-top: 20px; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; }
    th, td { text-align: left; padding: 6px 10px; border: 1px solid #d0d7de; }
    th { background: #f6f8fa; }
    ul { padding-left: 20px; }
    .warning { background: #fff8c5; border: 1px solid #d4a72c; padding: 8px; border-radius: 4px; }
    .meta { color: #656d76; font-size: 14px; }
  </style>
</head>
<body>
  ...
</body>
</html>
```

Key sections to render:
- Header (username, generated date, period) — handled directly by `format_html_report()`
- Warnings (styled as a highlighted alert box) — handled directly by `format_html_report()`
- Actions (table with minutes, storage, cost)
- Copilot (list with by-model breakdown)
- Git LFS (cost line)
- Monthly Costs (table with gross/discount/net per category)
- Repo Consumers (tables for by-minutes and by-cost)
- Artifact Storage (list of repos with MB)
- Release Assets (list of repos with MB)
- Key Insights (bullet list)
- Unavailable Data (list of errors)
- REST API Quota Notes (footnote-style) — handled directly by `format_html_report()`

### 2. Wire HTML through `send_email()`

Update `send_email()` to accept an optional `html: str | None` parameter. When `html` is provided, the Resend payload includes both `text` and `html` fields. The Resend API renders the HTML version in clients that support it while preserving plain-text fallback.

```python
def send_email(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    html: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> None:
    ...
    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }
    if html:
        payload["html"] = html
    # Then json.dumps(payload) and pass to http_retry.request_with_retries, as today.
    ...
```

### 3. Update `_run_email_report()` in `cli.py`

In the `_run_email_report()` function, after generating the plain-text body, define `html_body` unconditionally to avoid scoping issues (`NameError`) in the dry-run and send paths:

```python
        body = email_report.format_report_email(data)
        html_body = email_report.format_html_report(data) if args.email_format == "html" else None
```

Update the `email_report.send_email()` call in the dispatch flow to include `html=html_body` (cli.py lines 243-251):

```python
        email_report.send_email(
            os.environ["RESEND_API_KEY"],
            os.environ["RESEND_FROM"],
            os.environ["REPORT_EMAIL"],
            subject,
            body,
            html=html_body,
            timeout=args.timeout,
            max_retries=args.max_retries,
        )
```

Update the dry-run block to print the HTML body when format is `html`:

```python
        if args.dry_run:
            print(html_body if args.email_format == "html" else body, end="")
            return 0
```

The change in `_validate_email_flags()` should remove the HTML blocking logic.

> **Export interaction (no change needed):** The export path (lines 227-236) uses `body` (plain-text) for `--export text` and `data` for other formats. This behavior is correct regardless of `--email-format` — the `html_body` variable is only for email delivery, never for export. Do not change the export path.

### 4. Surface the option in the guided setup

The CLI unblocks `--email-format html` once sections 1-3 land, but a user who configures their scheduled email via the wizard (and the launchd / GitHub Actions schedules driven by it) would still receive plain-text unless we wire the format into the persisted config. The wizard already collects every other email-report knob in `config.toml`; `email_format` must join that list.

- **`src/github_usage/setup_config.py`:**
  - Add `"email_format": "text"` to `DEFAULT_EMAIL_REPORT` (line 22) so first-run configs include the new key.
  - In `email_report_args()` (line 185), append `["--email-format", str(email.get("email_format", "text"))]` to the returned args. Emit the flag unconditionally rather than only on non-default values, so the user's explicit choice round-trips through `--print-args`, the `verify-setup` dry-run, and any out-of-band inspection of the rendered command line.
  - In `write_config()` (line 143), add `email_format = "{email.get('email_format', 'text')}"` to the rendered `[email_report]` template (placement: after `max_repos` and before `warn_over`, matching the existing field order in the source). Without this, the on-disk TOML would be missing the key even though `load_config()` still resolves it from `DEFAULT_EMAIL_REPORT` — round-tripping works but the file is not self-describing for users editing it directly or for tools that read the TOML without merging defaults.
- **`src/github_usage/setup_wizard.py`:**
  - In `_configure_email_options()` (line 88), add a prompt after `max_repos` (before the `skip_*` group) asking `"Email body format (text | html)? [text]"` with the current value as the default. Re-prompt on invalid input; accept `text` and `html` only (case-insensitive comparison, then store the canonical lowercase form).
- **Example config:** The `[email_report]` section in `.github-usage/config.example.toml` (and any rendered config the wizard produces) should include `email_format = "text"` with a one-line comment explaining the choice and that `html` requires the new renderer (this plan).
- **Tests:**
  - Extend the existing `SetupConfigTests` class in `tests/test_setup_wizard.py` (which is where the `DEFAULT_EMAIL_REPORT` / `email_report_args` / `write_config` round-trip tests already live — see `test_email_report_args_from_config` at line 74 and `test_write_and_load_config_round_trip` at line 59): add assertions for the new `email_format` key — `DEFAULT_EMAIL_REPORT["email_format"] == "text"`, `email_report_args(...)` emits `--email-format html` when the config sets `email_format: "html"`, `--email-format text` when set to `"text"`, and `--email-format text` when the key is absent (default fallback). Also extend the round-trip test to assert the rendered TOML contains `email_format = "..."` and that `load_config()` reads it back. Do **not** create a separate `tests/test_setup_config.py` — keeping all config-unit tests in `test_setup_wizard.py::SetupConfigTests` matches the existing convention and avoids a second home for the same surface.
  - Extend `tests/test_setup_wizard.py` (the wizard-prompt tests, separate from `SetupConfigTests`): add cases for the new `_configure_email_options` prompt — empty input keeps the current value, `"html"` is stored as `"html"`, `"txt"` (or any other value) is rejected and the user is re-prompted.

### 5. Update module docstring and CLI text

Update the module docstring in `email_report.py:1` from:
```
"""Plain-text email report formatting and Resend delivery."""
```
to:
```
"""Email report formatting (plain-text and HTML) and Resend delivery."""
```

Update the email-report parser description in `cli_parsers.py:38` from:
```python
description="Send or preview a scheduled plain-text GitHub usage email report.",
```
to:
```python
description="Send or preview a scheduled GitHub usage email report.",
```

Update the HELP string in `cli.py:42` from:
```
--email-format FMT      Email body format: text | html (html deferred)
```
to:
```
--email-format FMT      Email body format: text | html
```

### 6. Tests

#### A. Unit Tests in `tests/test_email_report.py`

HTML rendering:
- `test_format_html_report_renders_html_sections` — verify HTML output contains expected sections
- `test_format_html_report_contains_valid_html_structure` — verify `<!DOCTYPE html>`, `<html>`, `<body>`, `<style>` tags
- `test_format_html_report_renders_minimal_data` — passes a minimal data dict (matching `test_format_report_email_renders_today_when_generated_at_missing`) and verifies no exceptions and valid HTML structure
- `test_format_html_report_escapes_special_chars` — inject `<`, `>`, `&`, `"` into repo names, warnings, and insights; assert they appear as `&lt;`, `&gt;`, `&amp;`, `&quot;` in the output (validates that the default `html.escape()` `quote=True` is in effect, not just the three-char `<`/`>`/`&` form)
- `test_format_html_report_well_formed_html` — feeds the HTML output through a custom `HTMLParser` subclass (see "HTML5 void elements in the well-formed-HTML test" design decision for the void-element allowlist) that maintains a tag stack, asserts that all opened tags are matched in the correct order, and treats HTML5 void elements (`meta`, `br`, `hr`, `link`, `img`, `input`, etc.) as self-closing. The test fails if the stack is non-empty at end-of-input or if any close tag doesn't match its open.

HTML formatter ordering:
- `test_section_html_formatters_order_matches_text_formatters` — verifies that `_SECTION_HTML_FORMATTERS` and `_SECTION_FORMATTERS` have the same length and that each HTML formatter name maps to its text counterpart (e.g., `_format_actions_section` ↔ `_format_html_actions_section`)

send_email payload:
- `test_send_email_posts_html_payload_when_provided` — verify that the Resend payload contains both `text` (the original body) and `html` (the provided HTML) fields, the `to`/`from`/`subject` fields are unchanged, and `conn.close()` is still called once
- `test_send_email_posts_text_only_when_html_none` — backward compatibility: no `html` field when `html=None`, payload matches the pre-change shape exactly

#### B. CLI and Integration Tests in `tests/test_export_cli.py`

CLI dry-run and integration:
- Update `test_email_report_html_format_errors` to `test_email_report_html_format_success` — verifies that running `email-report` with `--email-format html` succeeds (returns code 0 and prints HTML) under a dry-run. Requires mock infrastructure:
  - Mock `os.environ` to include a fake GITHUB_TOKEN
  - Mock `github_usage.cli.GitHubAPI` and its return value for `/user`
  - Mock `check_user_scope` to return `True`
  - Mock `report_data.build_report_data` to return a valid dummy report dictionary
  - Assert that stdout contains the generated HTML (`<!DOCTYPE html>`) and the exit code is `0`
- `test_email_report_default_format_sends_text_only` — regression test to verify that running `email-report` without `--email-format html` (defaulting to text) sends a text-only payload. This must exercise the real send path (no `--dry-run`), so the test must:
  - Set `RESEND_API_KEY`, `RESEND_FROM`, and `REPORT_EMAIL` in the mocked `os.environ` so `_missing_env` passes.
  - Mock `github_usage.cli.email_report.send_email` to a `mock.Mock()` that captures the call args.
  - Assert `send_email.call_args.kwargs["html"] is None`. The `html` kwarg is always present (the caller passes `html=html_body` unconditionally, per the `_run_email_report` change), so the assertion is on the value being `None`, not on the kwarg being absent.
  - The default format path also generates `html_body = None` (per the `_run_email_report` change), so this test is the regression guard for that wiring.

## Implementation Order

Phases are sequential — do them in order.

### Phase 1: HTML rendering function

**Done:** 2026-06-26 — HTML renderer. Added `format_html_report()`, `_html_cost_row()`, 9 `_format_html_*_section()` formatters, `_SECTION_HTML_FORMATTERS` tuple, `_HTML_DOCUMENT_HEAD` / `_HTML_DOCUMENT_TAIL` constants, and `import html` to `email_report.py`. Tests: 6 new in `test_email_report.py` (sections, structure, minimal data, escape coverage with `quote=True`, void-element-aware `HTMLParser` well-formedness, formatter-order parity).

### Phase 2a: Wire HTML through dispatch (code & test changes)

**Done:** 2026-06-26 — CLI + dispatch wiring. `send_email()` gained `html` kwarg emitting `text` + `html` in the Resend payload when provided. `cli._run_email_report()` defines `html_body` unconditionally, threads it into `send_email`, and switches the dry-run print. `cli._validate_email_flags()` no longer rejects `html`. Tests: 2 new `send_email` payload tests in `test_email_report.py`, renamed `test_email_report_html_format_errors → test_email_report_html_format_success` and added `test_email_report_default_format_sends_text_only` in `test_export_cli.py`, plus 5 new `SetupConfigTests` in `test_setup_wizard.py` (default, html, text, default fallback, write_config round-trip) and 6 new wizard-prompt tests in a new `EmailFormatWizardTests` class. Setup integration: `setup_config.DEFAULT_EMAIL_REPORT["email_format"] = "text"`, `email_report_args()` always emits `--email-format <value>`, `write_config()` writes the new key into TOML, `setup_wizard._configure_email_options()` now prompts for the format with a `_prompt_email_format` helper that re-prompts on invalid input.

### Phase 2b: User-visible text updates

**Done:** 2026-06-26 — Documentation + smoke. `cli.py:HELP` no longer says `(html deferred)`. `cli_parsers._email_parser` description dropped "plain-text". `email_report.py` module docstring updated. `.github-usage/config.example.toml` `[email_report]` includes the new `email_format` key with a comment. `CHANGELOG.md` `[Unreleased] → Added` entry rewritten. `scripts/smoke` now greps for `--email-format` alongside `--timeout` / `--max-retries`.

### Phase 3: Verification

**Done:** 2026-06-26 — Verification + TO_DO cleanup. `scripts/check` (with `scripts/check-sizes` advisory) passes — `email_report.py` is 515 lines and `setup_wizard.py` is 545 lines, both over the 500-line soft limit; both are pre-existing or noted overshoots (email_report is 15 over due to underestimating the CSS block + section-formatter verbosity; setup_wizard is 11 over due to the new prompt) and `check` is explicitly advisory. `scripts/smoke` passes (exit 0). `scripts/docs-check` passes. Manual dry-runs verified end-to-end: `email-report --email-format html --dry-run` prints a well-formed HTML body starting with `<!DOCTYPE html>`; `email-report --dry-run` prints plain text. `./start.sh setup --print-args` includes `--email-format text` from the default config, confirming setup wiring round-trips. `TO_DO.md` line removed per AGENTS.md.

### Phase 4: Plan close-out

**Done:** 2026-06-26 — Plan archived. Status banner set to canonical `> **Status:** COMPLETE`. Done notes added per phase. Plan moved to `docs/superpowers/plans/archived/`. Implementation merged in commit `f0b71a6`.

## Out of Scope

- Template file (e.g., a `.html` file on disk) — inline generation keeps dependencies minimal.
- CSS frameworks or external stylesheets — inline styles only for email client compatibility.
- HTML-to-text conversion — plain-text renderer already exists and is used as the fallback.
