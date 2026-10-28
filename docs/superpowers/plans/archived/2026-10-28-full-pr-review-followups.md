# Full PR review follow-ups

> **Status:** COMPLETE

**Done:** 2026-10-28 — Addressed A1–A10 and related editorial findings from the full Qoder PR review. Clarified partial redaction instead of changing redaction behavior; gated the smoke script’s live invalid-token probe behind explicit opt-in.

## Documentation accuracy
- [x] Correct CLI examples, checkout interpreter installs, partial redaction, and filename privacy.
- [x] Restore cache/refresh guidance, document profiles and command options, and clarify local/remote configuration.
- [x] Resolve related stale defaults, template naming, and development guidance.

## Help and verification
- [x] Align token help/error text and the launchd reinstall reminder with implementation/menu behavior, with regression tests.
- [x] Run repository, smoke, documentation, and link checks; archive this plan and commit.

Delivery: obtain a read-only review of the committed follow-ups before pushing.

Verification: `scripts/check` passed (749 tests, type/coverage/complexity gates); offline `scripts/smoke`, `scripts/docs-check`, focused auth/CLI/setup/export tests, 46 README/guide/changelog links and anchors, and fake-data redaction checks passed. Existing stale-assessment warnings remain. Relevant auth, redaction, and config-writer docstrings now state token precedence and redaction/config-preservation limits. Review of the committed follow-up is required before delivery.
