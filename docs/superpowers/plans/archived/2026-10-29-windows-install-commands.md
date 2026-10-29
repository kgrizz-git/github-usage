# Windows installation command rendering

> **Status:** COMPLETE

**Done:** 2026-10-29 — Added native Windows shell-specific command rendering, preserved POSIX output, removed trailing command punctuation, and added portable and native Windows-only tests.

- [x] Preserve POSIX rendering and add explicit cmd.exe/PowerShell command forms.
- [x] Show labeled Windows alternatives without guessing the calling shell; quote interpreter paths and requirement operators.
- [x] Cover rendering, help/error integration, and optional native Windows execution against fake pip; verify checks and archive before commit.

Delivery: the same Qoder reviewer must review committed changes before pushing.

Verification: `scripts/check` passed (763 tests; two native Windows tests skipped on macOS), offline `scripts/smoke`, `scripts/docs-check`, focused rendering/integration tests, and 46 local links/anchors passed. The Windows-native tests run generated commands against a temporary fake pip module rather than installing packages; actual Windows shell execution remains unverified on this host. Rendering is based on Microsoft’s cmd.exe and PowerShell operator/quoting documentation.

**Done:** 2026-10-29 — Follow-up review approved the renderer and identified uneven Windows missing-GUI message indentation. The message now indents all alternatives consistently, with a win32-mocked output regression test. Native Windows execution remains unverified on this host; no scanner suppressions were added.
