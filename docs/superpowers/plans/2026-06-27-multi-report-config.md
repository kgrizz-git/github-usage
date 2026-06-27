> **Status:** Ready for implementation

**Date:** 2026-06-27

## Objective

Extend the current single-report configuration so users can define **N named report profiles**, each with its own schedule, recipient, subject, section toggles, and warning thresholds. This enables use cases like:

- A **weekly digest** to the team (summary sections only, low threshold) and a **monthly deep-dive** to finance (all sections, high max-repos).
- Different reports for different GitHub orgs (each with its own token).
- A "critical thresholds only" alert with a different frequency than the main report.

## Current State

| Component | Limitation |
|---|---|
| `config.toml` | Single `[email_report]`, `[schedule]`, and `[github_actions]` section |
| `.env.email-report` | One recipient, one from-address, one token |
| `send-email-report.sh` | Runs one config; no way to select which profile |
| `setup_launchd.py` | Generates one plist with one `StartCalendarInterval`; `SetupPaths.launchd_plist`, `launch_agent_dest()`, and `LAUNCH_AGENT_NAME` are single-valued |
| `setup_workflow.py` | Renders one `.github/workflows/email-report.yml`; `workflow_path`, `diff_workflow`, `_render_and_offer_commit` assume one fixed file |
| `cli.py:_run_email_report` | Parses one set of CLI flags; no profile selector; requires `REPORT_EMAIL` in env; does not read `config.toml` |
| CLI parser | No `--profile`, `--to`, or `--subject` flag |
| `_send_email` in `cli_email_report.py` | Reads subject/recipient/from from `os.environ` only; no parameter path for profile-scoped values |
| GitHub Actions workflow | `concurrency.group` is a fixed literal; only bakes the three `include_*` toggles + cron; recipient comes solely from the `REPORT_EMAIL` secret/input |

### Constraint that shapes the design

`.github-usage/` is **gitignored** (only `config.example.toml` is tracked), so a
CI checkout has **no `config.toml`**. Any feature that depends on reading the
profile config *at runtime in GitHub Actions* cannot work. The existing GA flow
already side-steps this by baking options into the committed workflow at render
time. This plan keeps that property: profiles reach CI only through **baked
workflow content**, never through a runtime config read.

## Definition of Done

- Config file supports `[[reports]]` array-of-tables (TOML) — each entry has its own options, local schedule, GitHub Actions schedule, and target.
- CLI accepts `--profile NAME` (default unset). When omitted, behavior is unchanged from today. When set, the named profile's options are expanded as the baseline; explicit CLI flags are layered on top.
- CLI accepts `--to ADDR` (recipient override) and `--subject TEXT` (subject override).
- `_send_email` accepts explicit `subject`, `recipient`, `from_addr` parameters so profile-scoped values reach the dispatch without env-var manipulation.
- `email_report_args(config, profile_name)` emits the full flag set for a profile, **including** `--to` and `--subject` when the profile sets them.
- `_run_email_report` no longer hard-requires `REPORT_EMAIL` when a recipient is supplied via `--to` (or an expanded profile).
- `send-email-report.sh` accepts a `--profile` argument and uses `--print-args --profile NAME` to expand the full flag set; it does **not** rely on `email-report` reading config at runtime.
- Setup wizard gains a "manage report profiles" menu option.
- `setup --print-args` and `setup --verify` are profile-aware (`_setup_parser()` declares `--profile`).
- Launchd installs one profile-named plist per profile and migrates away from the old single plist.
- GitHub Actions renders one workflow per profile, with each profile's options, recipient, cron, and concurrency group **baked at render time** (no runtime config read, no `--profile` flag in CI).
- `scripts/check`, `scripts/smoke`, `scripts/docs-check` pass.
- Existing tests pass; new/extended tests cover multi-profile config loading, profile expansion, `_send_email` parameterized delivery, per-profile workflow rendering, and backward compatibility.
- `CHANGELOG.md` updated under `[Unreleased] > Added`.
- The `TO_DO.md` item is **removed** on completion (per `AGENTS.md`; the changelog and archived plan are the record).

## Design Decisions

1. **Backward-compatible TOML schema.** When the `[[reports]]` array is absent, the legacy top-level `[email_report]` + `[schedule]` + `[github_actions]` sections are loaded and treated as an implicit profile named `"default"`. When `[[reports]]` is present, the top-level sections are **ignored entirely** (not merged). On write, a single profile is written in the legacy top-level format; multiple profiles are written as `[[reports]]` with per-profile sub-tables. Existing config files round-trip safely.

2. **Per-profile schedule, sections, *and* GitHub Actions config.** Each profile is self-contained and carries its own `email_report` options, local `schedule` (launchd, local TZ), and `github_actions` block (cron in UTC + section defaults). This is what makes "weekly to the team, monthly to finance" possible and resolves the earlier conflict where a single top-level `[github_actions]` block would have forced every profile's workflow to share one cron/section set. There is **no** "inherit from base" layer — composability adds complexity with little benefit at the expected 2–3 report scale.

3. **Non-secret overrides in config, secrets stay in `.env`.** Profile-specific `target_email` and `target_subject` go in `config.toml`. Secrets (`GITHUB_TOKEN`, `RESEND_API_KEY`, `RESEND_FROM`) stay in `.env.email-report`. A profile cannot override secrets from TOML; if a different `RESEND_API_KEY` is needed, users source a different env file (handled out of band). Because `target_email` is non-secret, it may be **baked into the committed GA workflow** (see Decision 6); users who prefer not to commit an address leave it blank and rely on the `REPORT_EMAIL` secret.

4. **Profiles are resolved by argv expansion, in one place.** `--profile NAME` does not introduce a parallel code path through the email pipeline. Instead, when `--profile` is present, `_run_email_report` loads `config.toml`, resolves the profile, expands it to a flag list via `email_report_args(config, NAME)` (which now includes `--to`/`--subject`), and prepends those flags so the user's explicit flags (parsed last) win for scalar options. Boolean (`store_true`) and append (`--warn-over`) flags are **additive** on top of the profile baseline — documented behavior, and a non-issue for the automated entry points (which pass only the expanded set). When `--profile` is omitted, no config is read and behavior is identical to today.

5. **`_send_email` gains explicit parameters.** Instead of reading `os.environ` directly, `_send_email` accepts optional `subject`, `recipient`, and `from_addr` keyword arguments. If a value is provided it is used; otherwise the function falls back to `os.environ` (existing callers don't break). `_run_email_report` resolves recipient as `--to` > env `REPORT_EMAIL`, and subject as `--subject` > env `REPORT_SUBJECT` > default, then passes the resolved values explicitly. The `REPORT_EMAIL` env var is required **only** when no recipient is otherwise supplied.

6. **GitHub Actions bakes everything at render time; no runtime config read.** Because CI has no `config.toml`, each profile renders to its own committed workflow file with the profile's full option set expanded into the run step's `args=()` array, the recipient baked into the `REPORT_EMAIL` env (falling back to the secret when `target_email` is blank), the cron baked into the schedule, and a profile-scoped `concurrency.group`. The CI invocation is plain `email-report "${args[@]}"` — **no `--profile` flag**. Default profile keeps the filename `email-report.yml`, the literal name `GitHub Usage Report`, and the unsuffixed concurrency group `github-usage-email-report` for a minimal diff; non-default profiles use `email-report-<profile>.yml` and a `-<profile>` suffix.

7. **Launchd gets multiple profile-named plists.** Every profile (including `default`) installs `com.github.github-usage.email-report.<profile>.plist` with label `com.github.github-usage.email-report.<profile>`. On install/uninstall, the old single `com.github.github-usage.email-report.plist` is removed to prevent duplicate deliveries. `SetupPaths` gains a `launchd_plist_for(profile_name)` helper; `launch_agent_dest(profile_name)` and the label become profile-aware. The legacy `SetupPaths.launchd_plist` attribute is retained only to locate/migrate the old plist.

8. **`start.sh` needs no changes.** It already passes `"$@"` through to `python -m github_usage email-report "$@"`. The `--profile` flag (for manual runs) reaches the parser automatically.

## Proposed Implementation

### Phase 1: Config schema and loading

**Files:** `setup_config.py`

- Add new fields to the email-report defaults context: profiles also carry `target_email: str = ""` and `target_subject: str = ""` (stored at the profile level, not inside `DEFAULT_EMAIL_REPORT`).
- Add a `REPORT_PROFILE` dataclass (or typed dict) with fields: `name`, `email_report` (dict), `schedule` (dict), `github_actions` (dict), `target_email` (str), `target_subject` (str).
- Add `load_report_profiles(config: dict) -> list[dict]`:
  - If `"reports"` (array) is present: for each entry, merge `email_report` with `DEFAULT_EMAIL_REPORT`, `schedule` with `DEFAULT_SCHEDULE`, and `github_actions` with `DEFAULT_WORKFLOW_CONFIG`; read `name`, `target_email`, `target_subject` from the entry (`name` required and non-empty).
  - Else (legacy): build a single profile named `"default"` from top-level `config["email_report"]`, `config["schedule"]`, `config["github_actions"]`.
  - Validate that profile names are unique and non-empty (`ValueError` on duplicate/empty; `KeyError` if a `[[reports]]` entry omits `name`).
- Update `load_config()` to add a `"profiles"` key (the list from `load_report_profiles()`) alongside the legacy top-level keys. Legacy top-level keys remain populated **only** for the single/legacy case so existing callers keep working; in multi-profile configs they reflect the first profile for display convenience.
- Update `email_report_args(config, profile_name="default")`:
  - Resolve the named profile from `config["profiles"]`.
  - Translate its `email_report` sub-dict to CLI flags as today.
  - **Additionally** append `--to <target_email>` and `--subject <target_subject>` when those profile fields are non-empty.
- Rewrite `write_config()`:
  - **Single profile (or legacy call):** emit the existing `[email_report]` + `[schedule]` + `[github_actions]` top-level format, unchanged.
  - **Multiple profiles:** emit repeated `[[reports]]` blocks. Each block hand-emits scalar profile fields (`name`, `target_email`, `target_subject`) first, then the dotted sub-tables `[reports.email_report]`, `[reports.schedule]`, `[reports.github_actions]`. The `warn_over` list is emitted as a multi-line array inside `[reports.email_report]`. (These are dotted **sub-tables**, not inline `{...}` tables — inline tables cannot cleanly hold the multi-line `warn_over` array.)
  - Example of multi-profile output:
    ```toml
    # Generated by github-usage setup. Safe to edit locally; do not commit secrets here.

    [[reports]]
    name = "weekly"
    target_email = "team@example.com"
    target_subject = "Weekly GitHub Usage Digest"

    [reports.email_report]
    include_consumers = false
    include_artifact_storage = false
    include_release_assets = false
    max_repos = 100
    email_format = "text"
    warn_over = [
      "25",
      "80%",
    ]
    skip_actions = false
    skip_copilot = false
    skip_lfs = false

    [reports.schedule]
    weekday = 1
    hour = 9
    minute = 0

    [reports.github_actions]
    cron = "0 9 * * 1"
    include_consumers = false
    include_artifact_storage = false
    include_release_assets = false

    [[reports]]
    name = "monthly"
    target_email = "finance@example.com"
    target_subject = "Monthly GitHub Usage Deep-Dive"
    # ... sub-tables ...
    ```
- Update `_load_or_create_config()` to initialize a single `default` profile (and keep legacy top-level keys for the single-profile case).
- **Legacy → profile migration:** add a helper `ensure_profiles(config)` (used by the wizard when adding a second profile) that, if `config` is in legacy top-level form, wraps the existing `email_report`/`schedule`/`github_actions` as the `"default"` entry of a new `reports` list before any new profile is appended.
- Update `status_lines()` to list each profile (name, `target_email`, local schedule, GA cron, and per-profile workflow/plist presence).

### Phase 2: CLI `--profile`/`--to`/`--subject` flags and email pipeline

**Files:** `cli_parsers.py`, `cli.py`, `cli_email_report.py`

- In `_email_parser()`:
  - Add `--profile NAME` with default `None` (omitted ⇒ no config read, current behavior).
  - Add `--to ADDR` (recipient override) with default `None`.
  - Add `--subject TEXT` (subject override) with default `None`.
- Add a helper `_expand_profile_argv(argv) -> list[str]` (in `cli.py`):
  - Peek for `--profile NAME` in `argv`. If absent, return `argv` unchanged.
  - If present: load `config.toml` via `setup_config.load_config()`; if the profile is not found, print an error and signal failure. Otherwise compute `email_report_args(config, NAME)` and return `[*profile_flags, *argv_without_profile]` (user flags last so scalars win; booleans/`--warn-over` are additive — see Design Decision 4).
- In `_run_email_report()`:
  1. Expand the profile via `_expand_profile_argv()` **before** parsing; bail out with exit code 1 if expansion reports an unknown profile.
  2. Parse the (possibly expanded) argv.
  3. Validate flags as today.
  4. Resolve recipient: `args.to` > env `REPORT_EMAIL`.
  5. Resolve subject: `args.subject` > env `REPORT_SUBJECT` > `email_report.default_subject(...)`.
  6. Adjust the env precheck: require `REPORT_EMAIL` **only** when the resolved recipient is empty (i.e. no `--to`/profile recipient). `RESEND_API_KEY` and `RESEND_FROM` remain required for live sends.
  7. Pass the resolved `recipient` and `subject` explicitly to `_send_email`.
- In `_send_email()` (in `cli_email_report.py`):
  - Add optional `subject: str | None = None`, `recipient: str | None = None`, `from_addr: str | None = None` parameters.
  - Use each parameter when provided, else fall back to `os.environ.get(...)`; `from_addr` falls back to `os.environ["RESEND_FROM"]`.
  - Existing callers that pass nothing keep current behavior.

### Phase 3: `send-email-report.sh` profile support

**Files:** `scripts/send-email-report.sh`

- Parse a `--profile NAME` argument early from `"$@"`; default `PROFILE="default"`. Remove it from the args forwarded to `email-report` (it is consumed for expansion only).
- Expand the profile's full flag set (including `--to`/`--subject`) via `--print-args`:
  ```bash
  while IFS= read -r arg; do
    CONFIG_ARGS+=("$arg")
  done < <(PYTHONPATH=src scripts/python -m github_usage setup --print-args --profile "$PROFILE")
  ```
- Invoke `email-report` with the **expanded** flags plus any remaining user args; do **not** pass `--profile` to `email-report` (no runtime config read needed):
  ```bash
  PYTHONPATH=src scripts/python -m github_usage email-report "${CONFIG_ARGS[@]}" "$@"
  ```
- Embed the profile name in the log file: `LOG_FILE="$LOG_DIR/email-report-${PROFILE}-${STAMP}.log"`.

### Phase 4: Setup wizard — "Manage report profiles"

**Files:** `setup_wizard.py`, `setup_email_config.py`

**Depends on:** Phases 1–2 (config schema, profile loading, CLI flags).

- Add a menu option (e.g. `m`) — "Manage report profiles".
- When selected:
  1. List existing profiles with name, target email, local schedule, and GA cron.
  2. Offer: **a**dd new profile, **e**dit existing (by name), **d**elete profile, **s**kip.
  3. On the first **add** against a legacy config, call `ensure_profiles(config)` (Phase 1) to migrate the existing top-level config into the `"default"` profile entry before appending the new one.
  4. Add/edit prompts reuse existing helpers, made profile-aware:
     - `_configure_email_options(paths, profile_name=None)` — writes into the named profile's `email_report` sub-dict (or top-level for the legacy single-profile path).
     - `_configure_schedule(paths, profile_name=None)` — writes into the named profile's `schedule`.
     - `_configure_github_actions(paths, profile_name=None)` — writes into the named profile's `github_actions`.
     - New prompts for `target_email` and `target_subject`.
  5. On save, regenerate launchd plists and GA workflow files for **all** profiles.
- The optional `profile_name` parameter keeps the existing single-profile call sites working unchanged (default `None` ⇒ top-level behavior).

### Phase 5: Multi-profile launchd

**Files:** `setup_launchd.py`, `setup_config.py`

- `setup_config.SetupPaths` gains `launchd_plist_for(profile_name: str) -> Path` returning `config_dir / "launchd" / f"com.github.github-usage.email-report.{profile_name}.plist"`. Retain the existing `launchd_plist` attribute pointing at the legacy single plist (used for migration detection only).
- `LABEL`/`LAUNCH_AGENT_NAME` become profile-aware helpers: `label_for(profile_name)` and `launch_agent_dest(profile_name)`.
- `generate_plist(paths, profile_name)` writes a profile-named plist using that profile's `schedule`, and passes `--profile <name>` to `send-email-report.sh` in `ProgramArguments` so the scheduled run targets the right profile. Per-profile stdout/stderr log paths include the profile name.
- `install_launch_agent(paths)` loops over all profiles, installing each plist, and removes the legacy single plist if present.
- `uninstall_launch_agent()` removes every `com.github.github-usage.email-report.*.plist` (all profiles) and the legacy `com.github.github-usage.email-report.plist`.
- `launch_agent_status()` reports per-profile install state.
- Update call sites that referenced the single plist: `_configure_launchd`, `_schedule_only`, `_full_setup`, and `status_lines` iterate over profiles.

### Phase 6: Multi-profile GitHub Actions

**Files:** `setup_workflow.py`, `.github/workflows/email-report.yml.template`

CI never reads `config.toml`, so **all** per-profile values are baked at render time and the CI invocation carries no `--profile` flag.

- Extend the template:
  - Add a `__PROFILE_SUFFIX__` token for the `name:` and `concurrency.group` (empty for `default`, `-<profile>` otherwise). Example: `concurrency:\n  group: github-usage-email-report__PROFILE_SUFFIX__`.
  - Add a `__PROFILE_ARGS__` token appended to the `args=()` array after the existing dispatch-controlled `include_*` toggles. It carries the profile's remaining baked flags (`--max-repos`, `--email-format`, repeated `--warn-over`, `--skip-actions`/`--skip-copilot`/`--skip-lfs`, `--subject`).
  - Add a `__TARGET_EMAIL__` token: render the `REPORT_EMAIL` env as `${{ inputs.report_email || '<target_email>' || ... }}` when `target_email` is set; otherwise keep the existing `${{ inputs.report_email || secrets.REPORT_EMAIL }}`.
  - The final run line stays `python -m github_usage email-report "${args[@]}"` (no `--profile`).
- `render_workflow(config, root=None, profile_name="default")`:
  - Render cron + the three `include_*` defaults from the **profile's** `github_actions` block.
  - Render `__PROFILE_ARGS__` from the profile's `email_report` via a shared helper (reuse the non-`include_*` portion of `email_report_args`).
  - Render `__PROFILE_SUFFIX__` and `__TARGET_EMAIL__`.
  - `profile_name` is keyword-optional with a `"default"` default so existing positional callers/tests keep working.
- `workflow_path(root, profile_name="default")`: returns `email-report.yml` for `default`, `email-report-<profile>.yml` otherwise. Keyword-optional default preserves existing call sites.
- `write_workflow(root, text, profile_name="default")` and `diff_workflow(root, new_text, profile_name="default")`: profile-aware filenames; keyword-optional.
- `_render_and_offer_commit(paths, profile_name=None)`: when `profile_name` is `None`, iterate every profile, render/diff/offer each.

### Phase 7: `setup --print-args` and `setup --verify` profile awareness

**Files:** `setup_wizard.py`

- Add `--profile NAME` (default `"default"`) to `_setup_parser()` so `run_setup`'s strict argparse accepts the flag that `send-email-report.sh` passes. (Without this, `setup --print-args --profile X` raises `SystemExit(2)`.)
- The `--print-args` handler forwards the parsed `--profile` to `email_report_args(config, profile_name=...)`.
- `_verify_setup(paths, profile_name=None)`: when `profile_name` is `None`, iterate over all profiles and run `email-report --dry-run` (using each profile's expanded args) for each; when a specific `--profile NAME` is passed, verify only that profile. The dry-run path needs no live secrets.

### Phase 8: Tests

**Status of test files:** `tests/test_setup_config.py` and `tests/test_cli_email_report.py` are **new**. `tests/test_cli.py` and `tests/test_setup_workflow.py` **already exist** and must be **extended**, not recreated. All new `profile_name` parameters on `render_workflow` / `write_workflow` / `workflow_path` / `diff_workflow` are keyword-optional with `"default"` defaults so the existing positional-call tests in `test_setup_workflow.py` keep passing.

- New `tests/test_setup_config.py` for `load_report_profiles()` / `write_config()`:
  - Legacy single config (no `[[reports]]`) yields a single `"default"` profile.
  - Multi-profile config yields all profiles with merged defaults.
  - A `[[reports]]` entry missing `name` raises `KeyError`.
  - Duplicate or empty profile names raise `ValueError`.
  - Round-trip: single profile → legacy top-level format → re-reads as one profile; multi-profile → `[[reports]]` → re-reads identically (including `warn_over` arrays).
  - `ensure_profiles()` migrates a legacy config into a `default` entry.
  - `email_report_args(config, name)` includes `--to`/`--subject` only when the profile sets them.
- Extend `tests/test_cli.py`:
  - `--profile` expansion with valid/invalid names (invalid ⇒ exit 1, clear message).
  - Explicit CLI scalar flags override expanded profile values; `--warn-over`/booleans are additive (documented).
  - `--to` satisfies the recipient requirement so a missing `REPORT_EMAIL` no longer fails (dry-run-safe assertions, mocked send).
  - Bare `email-report` (no `--profile`) does not read `config.toml` (behavior unchanged).
- New `tests/test_cli_email_report.py`:
  - `_send_email` honors explicit `subject`/`recipient`/`from_addr`.
  - `_send_email` falls back to `os.environ` when parameters are `None`.
- Extend `tests/test_setup_workflow.py`:
  - Default profile renders `email-report.yml`, unsuffixed concurrency group, no `--profile` in the run step.
  - Non-default profile renders `email-report-<name>.yml`, `-<name>` concurrency suffix, baked `__PROFILE_ARGS__`, and baked recipient.
  - Existing positional-call render/write/diff tests still pass.
- All previously passing tests must remain green (backward compat).

### Phase 9: Verification and smoke test updates

- Update `scripts/smoke` to:
  - Grep for `--profile`, `--to`, and `--subject` in `email-report --help` output.
  - Verify `setup --print-args --profile default` works with a single-profile config.
  - Verify multi-profile `setup --print-args --profile <name>` works.
- Run `scripts/check`, `scripts/smoke`, `scripts/docs-check`.
- Run the full test suite.
- Manual smoke test: `python -m github_usage email-report --profile default --dry-run` with a single-profile config, then with a multi-profile config; confirm `send-email-report.sh --profile <name> --dry-run` expands the right flags.
- Update `CHANGELOG.md` under `[Unreleased] > Added`.
- **Remove** the corresponding item from `TO_DO.md` (per `AGENTS.md`, completed items are removed, not marked `[x]`).

## Out of Scope

- Per-profile GitHub tokens. Each profile uses the same `GITHUB_TOKEN` from the env file. Multi-org support would require a separate feature.
- Web-based config UI. All profile management happens through the CLI setup wizard or direct TOML editing.
- Report retention/archival configuration. That's a separate TO_DO.md item.
- Month-over-month comparison. Blocked by GitHub API limitations, per the Blocked section of TO_DO.md.
- Per-profile `RESEND_API_KEY` or other secrets. Secrets stay in `.env.email-report`; per-profile secrets would require a separate feature.

## Cross-Module Dependencies

```
setup_config.py
  └─> load_report_profiles() — reads config, returns list of profile dicts
  └─> ensure_profiles() — migrates legacy top-level config into a "default" entry
  └─> email_report_args(config, profile_name) — profile-aware; emits --to/--subject
  └─> write_config() — emits [[reports]] sub-tables when multi-profile
  └─> status_lines() — lists each profile (schedule, cron, workflow/plist state)
  └─> SetupPaths.launchd_plist_for(profile_name) — profile-named plist path

cli_parsers.py
  └─> _email_parser() — adds --profile NAME, --to ADDR, --subject TEXT

cli.py
  └─> _expand_profile_argv() — expands --profile into a flag list before parsing
  └─> _run_email_report() — resolves recipient/subject, relaxes REPORT_EMAIL,
                            passes explicit values to _send_email

cli_email_report.py
  └─> _send_email() — gains subject/recipient/from_addr keyword args

setup_wizard.py
  └─> "Manage report profiles" menu option
  └─> _setup_parser() — adds --profile NAME
  └─> --print-args / --verify — profile-aware
  └─> setup_email_config.py — profile-aware prompts (email/schedule/GA/target)

setup_launchd.py
  └─> generate_plist(paths, profile_name) — profile-named plist, --profile in args
  └─> install/uninstall_launch_agent() — loop over profiles, migrate old plist
  └─> label_for()/launch_agent_dest(profile_name)/launch_agent_status()

setup_workflow.py
  └─> render_workflow(config, root, profile_name) — bakes args/recipient/cron/suffix
  └─> workflow_path/diff_workflow/write_workflow(root, ..., profile_name)
  └─> _render_and_offer_commit(paths, profile_name) — iterates profiles

scripts/send-email-report.sh
  └─> --profile NAME → print-args expansion (incl --to/--subject); no runtime config read
  └─> profile name in log filename
```
