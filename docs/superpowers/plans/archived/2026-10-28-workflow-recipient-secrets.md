# Workflow recipient secrets

> **Status:** COMPLETE

**Done:** 2026-10-28 — Removed recipient literals and manual overrides from Actions workflows; local recipient behavior retained. No deviations.

- [x] Audit published workflow branches and available history for literal email addresses without printing addresses.
- [x] Make rendered and checked-in workflow recipients use only REPORT_EMAIL secrets; remove manual recipient overrides.
- [x] Add regression coverage for default/named profiles and update recipient documentation.
- [x] Run repository and documentation checks, then archive this plan.

Verification: `scripts/check` and `scripts/docs-check` passed; documentation checks reported existing stale assessment warnings. Published-branch audit covered both current GitHub branches, 24 workflow-changing commits, and 36 distinct workflow blobs; no literal email addresses found. The audit did not examine Actions logs or deleted remote refs.
