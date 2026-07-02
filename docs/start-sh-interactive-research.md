# Research: Adapting CI and Tests to an Interactive `start.sh`

This document contains research and evaluation on adapting the project's CI and automated tests to accommodate an interactive `start.sh` options menu or setup wizard.

---

# GEMINI SYNTHESIS

## 1. Executive Summary & Accuracy Review

A comprehensive review of the existing research materials against the active `github-usage` codebase confirms that **Option A (Python Unit/Integration Mocking)** is the most robust, maintainable, and architecturally aligned strategy for testing interactive CLI flows.

### Accuracy of Existing Findings
* **Original Analysis (Sections 1–2)**: Correctly identifies the TTY requirement in `setup_wizard.py` and the stdlib `unittest` mocking patterns in `test_setup_wizard.py`. However, its stated disadvantage for Option A—that it does not test the `./start.sh` wrapper—is negligible because `./start.sh setup` invokes `scripts/setup.sh`, which is simply a one-line execution wrapper (`python -m github_usage setup "$@"`).
* **DeepSeek Flash Findings**:
  * *Accurate & Critical Insights*: Correctly identified that there are **four distinct `isatty()` call sites** across the codebase (not just one), noted that `setup_prompts.py` demonstrates a graceful fallback pattern (`getpass.getpass("")`), highlighted that `--non-interactive` is already defined in the argument parser, and confirmed that the project maintains zero runtime dependencies and uses stdlib `unittest`.
  * *Inaccurate Claim*: DeepSeek Flash incorrectly asserted that *"No CI Workflow Exists"* and that there is *"no `.github/` directory in this repository"*. In reality, `.github/workflows/ci.yml` exists and actively runs `scripts/check` across Python 3.11, 3.12, and 3.13 on GitHub Actions.
* **North Mini Code Next Findings**: Correctly notes the benefits of explicit CLI test flags (Option D), but its suggestions regarding pseudo-terminal (PTY) emulation, Docker testcontainers, and third-party test frameworks (`pytest-asyncio`, `pexpect`) conflict with the repository's zero-dependency design and lightweight stdlib testing conventions.

---

## 2. Comprehensive TTY Audit

Any interactive testing strategy must account for all four `sys.stdin.isatty()` call sites across the codebase:
1. `setup_wizard.py:457`: Blocks the interactive setup wizard if no TTY is detected.
2. `cli.py:104` (`_confirm_release_assets`): Gates the confirmation prompt for release asset inventory scanning when `--include-release-assets` is passed without `--yes-include-release-assets`.
3. `cli.py:333` (`main`): Gates the interactive export-format selection prompt when no format is specified via `--export` and `--no-interactive` is not set.
4. `setup_prompts.py:29` (`_prompt_secret`): Gracefully falls back to standard `getpass.getpass("")` without character echoing when not attached to a TTY.

---

## 3. Best Recommendations & Implementation Roadmap

To maintain the repository's strict "zero runtime dependencies" rule and fast CI execution via `scripts/check`, implement interactive testing using the following approach:

### Primary Strategy: Standard Library Unit & Mock Testing (Option A + Option D)
1. **Extend Stdlib `unittest` Coverage**: Continue mocking `sys.stdin.isatty` (returning `True`) and patching `builtins.input` / `getpass.getpass` in unit tests. Expand `tests/test_setup_wizard.py` and add targeted tests for `cli.py` (`_confirm_release_assets` and export format prompting) to ensure all four interactive paths are tested.
2. **Evolve `--non-interactive` / Test Mode**: Instead of introducing arbitrary environment variables (Option B) or complex PTY emulation (Option C), extend the existing `--non-interactive` flag or add an explicit `--test-input` parameter to accept structured canned responses for automated scripting or integration smoke tests.
3. **Adopt Graceful Non-TTY Fallbacks**: Where appropriate, follow the resilient design pattern from `_prompt_secret()` by falling back to non-interactive defaults or clear error messages rather than unhandled aborts.
4. **Avoid Heavy CI Infrastructure**: Reject PTY wrappers, `expect`/`pexpect`, and Docker-based terminal emulation in CI. These add unnecessary maintenance overhead and external dependencies without providing meaningful coverage advantages over well-structured unit integration mocks.

---

## 1. Current State of Interactive Logic & Testing

- **Interactive Wizard**: The interactive setup wizard is implemented in [setup_wizard.py](file:///Users/kevingrizzard/MyCode/github-usage/src/github_usage/setup_wizard.py) (called via `./start.sh setup`). It uses `sys.stdin.isatty()` to ensure it only runs in interactive terminal sessions. If no TTY is detected, it exits with an error:
  `Error: interactive setup requires a TTY. Use --status or --verify.`
- **Unit Testing**: Unit tests in [test_setup_wizard.py](file:///Users/kevingrizzard/MyCode/github-usage/tests/test_setup_wizard.py) successfully test the interactive logic by mocking `sys.stdin.isatty` to return `True` and patching `builtins.input` with mock inputs/return values.
- **CI / Smoke Checks**: The GitHub Actions workflow ([ci.yml](file:///Users/kevingrizzard/MyCode/github-usage/.github/workflows/ci.yml)) runs non-interactively. Script checks like [check](file:///Users/kevingrizzard/MyCode/github-usage/scripts/check) and [smoke](file:///Users/kevingrizzard/MyCode/github-usage/scripts/smoke) do not test the interactive wizard paths end-to-end because CI environments do not allocate a TTY.

---

## 2. Adaptation Options & Complexity

If `start.sh` is adapted to present an interactive options menu, we must ensure CI and test checks do not hang or fail. Below are three approaches to handle interactive testing in CI:

### Option A: Python Unit / Integration Mocking (Low Complexity - Recommended)
Expand the existing unit tests in [test_setup_wizard.py](file:///Users/kevingrizzard/MyCode/github-usage/tests/test_setup_wizard.py) to cover new interactive paths.
* **Implementation**: Patch `builtins.input` with sequence iterators or predefined mocks to test menu navigation.
* **Complexity**: Low.
* **Pros**: No changes needed to shell script infrastructure, fast execution, completely robust.
* **Cons**: Does not verify the actual bash script interface (`./start.sh`) wrapper, only the Python implementation.

### Option B: TTY Bypass Environment Variable (Low Complexity)
Introduce a testing bypass flag inside the Python entry point to skip `sys.stdin.isatty()` checks when a specific environment variable is set.
* **Implementation**: Modify [setup_wizard.py](file:///Users/kevingrizzard/MyCode/github-usage/src/github_usage/setup_wizard.py) to allow input redirection under a test environment variable (e.g., `FORCE_INTERACTIVE=1`):
  ```python
  if not sys.stdin.isatty() and not os.environ.get("FORCE_INTERACTIVE"):
      # error out
  ```
  Then, shell scripts like [smoke](file:///Users/kevingrizzard/MyCode/github-usage/scripts/smoke) can run the interactive scripts using standard input redirection:
  ```bash
  FORCE_INTERACTIVE=1 ./start.sh setup <<EOF
  1
  y
  q
  EOF
  ```
* **Complexity**: Low.
* **Pros**: Very easy to test end-to-end interactive CLI flows directly from bash scripts.
* **Cons**: Requires a minor change to the source code to support the environment variable.

### Option C: Pseudo-Terminal (PTY) Emulation in CI (Medium Complexity)
Run the script inside a pseudo-terminal wrapper in CI to satisfy `sys.stdin.isatty()`.
* **Implementation**: Write a helper Python script utilizing Python's built-in `pty` and `subprocess` modules to allocate a PTY, execute `./start.sh`, write inputs to the master descriptor, and verify stdout/stderr. Alternatively, use standard tools like `expect` or `pexpect`.
* **Complexity**: Medium.
* **Pros**: Tests the exact code without any source modifications or test env vars.
* **Cons**: More complex test harness logic, harder to debug if tests hang, and adds dependencies/complexity to the CI runner.

# NORTH MINI CODE NEXT FINDINGS

## 4. Alternative Approaches & Considerations

### Option D: Subprocess-based TTY Simulation (Low-Medium Complexity)
Instead of Option B's environment variable approach, consider adding a dedicated `--test-mode` CLI flag that internally sets `FORCE_INTERACTIVE` and simulates user inputs. This provides better traceability than environment variables and allows for more complex test scenarios.

### Option E: Mock TTy / CI Integration (Custom Approach)
Rather than mocking `sys.stdin.isatty` in unit tests, create a CI-level integration test that uses Docker containers with pseudo-terminals to test the complete end-to-end flow. This provides the most realistic testing environment while maintaining separation between unit and integration concerns.

## 5. Cross-Reference Analysis

### Missing Reference: Testing Infrastructure
The document does not address how to use modern test frameworks like pytest-asyncio or testcontainers for interactive testing. These approaches could simplify Option C's PTY emulation and provide better isolation.

### Missing Reference: Logging & Validation
No explicit mention of adding logging or validation checkpoints in interactive flows. Consider adding structured logging to capture user decisions and validate expected state transitions in CI.

## 6. Code Quality Considerations

### Missing Reference: Error Handling
When bypassing TTY checks, ensure robust error handling for missing inputs or invalid choices. The current approaches do not explicitly address edge cases like malformed user inputs or unexpected EOF conditions in test environments.

### Missing Reference: Documentation
There's no explicit documentation on how to maintain test consistency across different CI runners or platforms. Interactive tests may produce different outputs based on terminal capabilities, requiring additional documentation and normalization.

## 7. Recommendation
Option A (Python Unit/Integration Mocking) appears to be the most pragmatic starting point, but incorporating elements of Option B's environment variable approach could provide the most balance of testing completeness and implementation simplicity. The TTY bypass approach with a clear test-mode flag would enable end-to-end testing while maintaining source code integrity and test isolation.

# DEEPSEEK FLASH FINDINGS

## 1. The Document Misses Two Additional `isatty()` Sites

The document focuses exclusively on `setup_wizard.py:457`, but the codebase has **three** distinct `isatty()`-gated interactive paths:

- `setup_wizard.py:457` — blocks the entire interactive menu.
- `cli.py:104` — `_confirm_release_assets()` gates a confirmation prompt for release asset inventory; errors out with a message instead of prompting.
- `cli.py:333` — `main()` gates the export-format menu prompt, but **only** when `--no-interactive` is not set and no format was resolved from `--export`.
- `setup_prompts.py:29` — `_prompt_secret()` falls back to `getpass.getpass("")` when not a TTY (graceful, no error).

Any testing strategy that aims for end-to-end CLI coverage must account for all four sites, not just the wizard.

## 2. No CI Workflow Exists

The document states "The GitHub Actions workflow ([ci.yml](file:///Users/kevingrizzard/MyCode/github-usage/.github/workflows/ci.yml)) runs non-interactively." There is no `.github/` directory in this repository. The pipeline is `scripts/check` and `scripts/smoke`, run locally or via the user's own CI. This inflates Options C and E (PTY emulation, Docker-based CI tests) — they would require inventing a CI infrastructure that does not exist, making them significantly higher complexity than stated.

## 3. The `--non-interactive` Flag Already Exists But Was Ignored

`setup_wizard.py:70-73` already defines `--non-interactive` as a parser argument. Currently it only errors if used without `--status` or `--verify` (`setup_wizard.py:453-455`). The document's Option B (introducing `FORCE_INTERACTIVE`) reinvents a wheel that's half-built. A more natural evolution would be to extend `--non-interactive` to also work with `--test-mode` or an env var to supply canned inputs, rather than adding a separate env var.

## 4. No Test Dependencies Exist

`pyproject.toml` has no `[project.optional-dependencies] test` section — no `pytest`, no `pexpect`, no `pytest-asyncio`. The project uses only `unittest` from stdlib. Option C (PTY emulation) and the document's "Cross-Reference Analysis" suggestion of pytest-asyncio/testcontainers would introduce new third-party dependencies with no existing precedent in the project. This raises the complexity bar considerably.

## 5. The Bash Layer Is Already Testable Via `run_setup()`

The document says Option A "does not verify the actual bash script interface (`./start.sh`) wrapper." However, `scripts/setup.sh` is a one-liner that calls `python -m github_usage setup "$@"`, which invokes `run_setup()` — the same function the unit tests already call. The bash wrapper adds zero logic beyond setting `PYTHONPATH`. Option A already covers the actual entry point.

## 6. `_prompt_secret()` in `setup_prompts.py` Handles Non-TTY Gracefully

`setup_prompts.py:29` checks `not sys.stdin.isatty()` and falls back to `getpass.getpass("")` rather than erroring out. This is a more resilient pattern than the hard error in `setup_wizard.py:457-459`. The document's Option B (env-var bypass) could learn from this pattern: instead of always erroring, `setup_wizard.py` could fall back to reading from a test-input environment variable or file descriptor.

## 7. Section Numbering / Structure Issues

The document has structural quirks: Option C is never numbered in the text, there is a dangling "NORTH MINI CODE NEXT FINDINGS" header between the options and the alternatives section, and Options D/E use numeric labels that collide with the A/B/C scheme. The "Cross-Reference Analysis" and "Code Quality Considerations" sections read as generic LLM-generated suggestions rather than grounded observations about this specific codebase.

## Summary

The document's core recommendation (Option A + elements of B) is sound, but its argument is weakened by missing the other `isatty()` sites, incorrectly asserting CI infrastructure exists, ignoring the already-existing `--non-interactive` flag, and suggesting dependency-heavy approaches (PTY, Docker, pytest-asyncio) that contradict the project's zero-test-dependency convention. A simpler, more accurate path forward: extend `--non-interactive` to support a `--test-input` file or env var that feeds canned responses, and add a `_confirm_release_assets` mock test for the `cli.py` path.
