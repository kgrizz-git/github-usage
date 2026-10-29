# Simplify README

> **Status:** COMPLETE

**Done:** 2026-10-28 — Reduced README from 533 to 69 lines and moved detailed guidance into five linked guides; no application behavior changes.

- [x] Keep the README focused on overview, first report, scheduled email, and guide navigation.
- [x] Move detailed reference into setup, email, reports, scheduled runs, and development guides; preserve privacy and scheduling guidance.
- [x] Check documentation and relative links, then archive the plan before committing.

Verification: `scripts/docs-check` and `git diff --check` passed. Checked all 29 local Markdown links/anchors across the README and five guides; all 33 previously documented command flags remain covered. Existing stale-assessment warnings remain.
