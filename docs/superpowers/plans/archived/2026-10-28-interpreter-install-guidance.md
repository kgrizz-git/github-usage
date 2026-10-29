# Interpreter-specific installation guidance

> **Status:** COMPLETE

**Done:** 2026-10-28 — Addressed CodeRabbit’s interpreter/PATH findings. Extracted help text into a focused module, retained the importable HELP snapshot, and render emitted guidance using the running interpreter. GUI dependency installation matches the sole dependency of the gui extra; checkout extra commands are retained.

- [x] Make setup invocations work without a console script on PATH.
- [x] Generate shell-safe install commands from the running interpreter for CLI/TUI help and export errors; retain checkout guidance.
- [x] Test interpreter paths containing spaces/quotes, missing dependencies, and both help routes; run repository/smoke/docs checks.
- [x] Archive and commit the implementation for the same Qoder agent to review before push.

Verification: `scripts/check` (754 tests and type/coverage/complexity gates), offline `scripts/smoke`, `scripts/docs-check`, 57 focused tests, and 46 local links/anchors passed. Regression cases cover current interpreter paths containing spaces/apostrophes, both help routes, missing GUI/XLSX/PDF dependencies, and no token resolution for help. The same Qoder DeepSeek reviewer must review this committed change before push.

**Done:** 2026-10-28 — CodeFactor reported B108 on synthetic `/tmp` interpreter strings in test fixtures. The tests now derive fake interpreter paths from a managed `TemporaryDirectory`, preserving spaces/apostrophes coverage without hardcoded temporary-directory paths or scanner suppressions.
