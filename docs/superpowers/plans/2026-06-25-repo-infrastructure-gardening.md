# Repo Infrastructure, Doc Gardening, and Agent Guidance

> **Status:** NEEDS REVIEW
> **Created:** 2026-06-25
> **Revised:** 2026-06-25 (incorporated review findings; see `tmp/2026-06-25-155100-repo-infrastructure-gardening-review.md`)

**Goal:** Standardize agent guidance for documentation maintenance, plan lifecycle, and changelog hygiene. Establish `AGENTS.md` as the single source of truth for all coding agents. Clean up accumulated stale artifacts and define a repeatable workflow.

---

## Conventions used by this plan

- **Status banner format (canonical):** `> **Status:** COMPLETE` — colon *outside* the bold. Use this exact form everywhere so the Task 5 regex (`\*\*Status:\*\*\s*COMPLET`) detects it. Do not use `> **Status: COMPLETE**`.
- **Plan filenames:** `YYYY-MM-DD-<slug>.md`.

## Dependencies & ordering

1. **Task 1 lands first.** Tasks 2 and 3 implement conventions that Task 1 documents in `AGENTS.md`; Task 1 must land before or alongside them.
2. **Task 5 (new docs-check warnings) lands after Task 4.** Otherwise running `docs-check` mid-change warns about the completed plans that Task 4 is in the process of archiving.
3. **Task 10 (self-archive this plan) is last**, after every other task and the Verification checklist pass.

---

## Current State & Problems

- `AGENTS.md` covers done criteria for plan checkboxes, archiving, `CHANGELOG.md`, and `TO_DO.md`, but does not spell out the full documentation lifecycle in one place, and lacks explicit release instructions and a stated status-banner format.
- `CHANGELOG.md` follows Keep a Changelog with an `[Unreleased]` section (plus a released `[0.1.0]`). It also uses a non-standard `### Deferred` subsection that is currently undocumented.
- `TO_DO.md` mixes completed (`[x]`) and open items and needs cleanup, not a rewrite.
- `docs/repo-harness-guidance.md` has broad harness guidance and a Periodic Maintenance Checklist, but no documentation-lifecycle section.
- Several plans in `docs/superpowers/plans/` are complete in practice but have missing or contradictory status banners and unchecked tasks, so they cannot be cleanly archived.
- `GEMINI.md` carries unique guidance that should be reconciled with `AGENTS.md`; `QWEN.md` does not exist.
- `scripts/docs-check` does not flag completed-but-unarchived plans.
- `docs/` holds loose artifacts (`api-discovery-month.md`), and `docs/superpowers/plans/archived/` holds untimestamped plans (`fix-a1-a6.md`, `plan-repo-hygiene.md`).

---

## Tasks

- [ ] **1. Update AGENTS.md — Agent Workflow Section** (targeted edits; leave Code Style and Maintainer References unchanged)
  - [ ] Edit the CHANGELOG bullet (the one beginning "After completing any user-visible feature or fix...") to match the `[Unreleased]` convention, replacing the "topmost release section" wording.
  - [ ] Edit the TO_DO bullet (the one beginning "After completing a `TO_DO.md` item...") to match the new removal convention, replacing the "mark it `[x]` and keep it" wording.
  - [ ] Add plan lifecycle instructions: create with a timestamped filename → work through tasks → mark items `[x]` → set the status banner to `> **Status:** COMPLETE` (canonical format above) → move to `docs/superpowers/plans/archived/`.
  - [ ] Add release instructions: create a version section in `CHANGELOG.md`, move `[Unreleased]` items into it, and bump the version in **both** `src/github_usage/__init__.py` (`__version__`) and `pyproject.toml` (`version`) so the two stay in sync. (Note: consider making `pyproject.toml` derive the version dynamically from `__init__.py` in a future change to remove the dual source; out of scope here.)
  - [ ] Document the canonical status-banner format in `AGENTS.md` so all agents emit a form the docs-check can detect.

- [ ] **2. Clean up CHANGELOG.md** (convention change: all in-progress work stays under `[Unreleased]`)
  - [ ] Verify all unreleased items are under `[Unreleased]` in the correct subsections.
  - [ ] Decide on the `### Deferred` subsection: sanction it by documenting `Deferred` as an allowed subsection (alongside `Added`, `Fixed`, `Changed`) in the format note, OR fold its entries into a clearly labeled location. Default: sanction and document it, since it is already in use and meaningful.
  - [ ] Add a brief format note at the top referencing Keep a Changelog and listing the allowed subsections.
  - [ ] Do not create a version section yet — remain on `[Unreleased]` until a release is tagged.

- [ ] **3. Clean up TO_DO.md** (convention change: remove items when completed)
  - [ ] Remove all items already marked `[x]` (completed).
  - [ ] Consolidate sections where appropriate (e.g., merge related bug-fix sections).
  - [ ] Add a note at the top: agents should remove items when completed.
  - [ ] When removing completed items, preserve any still-relevant `[Plan]` links by confirming the linked plan still exists at the referenced path (see Task 8 for the `plan-repo-hygiene.md` rename, which affects four links here).

- [ ] **4. Archive completed plans and fix statuses** (use the canonical banner format: `> **Status:** COMPLETE`)
  - [ ] Fix `2026-06-14-repo-harness.md`: check off the last task (`Run verification and initialize git`) and add a `> **Status:** COMPLETE` banner.
  - [ ] Fix `2026-06-16-bug-fixes.md`: add a top-level `> **Status:** COMPLETE` banner.
  - [ ] Fix `2026-06-21-bug-fixes.md`: correct the banner/body text that says the 7 bugs "are open" to state they are fixed (all 7 are `[x]`), resolving the contradiction.
  - [ ] `2026-06-19-remaining-bug-fixes.md`: already has a COMPLETE banner — no status fix needed; archive only (below).
  - [ ] Fix `docs/plan-email-report.md` and `docs/plan-export-reports.md`: add `> **Status:** COMPLETE` banners and done notes.
  - [ ] Move `2026-06-14-repo-harness.md` → `archived/`.
  - [ ] Move `2026-06-16-bug-fixes.md` → `archived/`.
  - [ ] Move `2026-06-19-remaining-bug-fixes.md` → `archived/`.
  - [ ] Move `2026-06-21-bug-fixes.md` → `archived/`.
  - [ ] Move `docs/plan-email-report.md` → `docs/superpowers/plans/archived/plan-email-report.md` (implemented: `email_report.py` exists, CLI subcommand works).
  - [ ] Move `docs/plan-export-reports.md` → `docs/superpowers/plans/archived/plan-export-reports.md` (implemented: all `export_*.py` modules exist, `--export` flag works).

- [ ] **5. Enhance scripts/docs-check** (implement after Task 4 so the new warning does not fire on plans being archived in the same change)
  - [ ] Add a check: warn (do not fail) if any non-archived `.md` plan in `docs/superpowers/plans/` contains a regex match for `\*\*Status:\*\*\s*COMPLET`. Include the filename and matching line in the warning.
  - [ ] Verify the new warning actually fires: run `docs-check` against a temporary throwaway plan containing a COMPLETE banner (placed in an untracked temp dir or created then removed) and confirm the warning appears and that `docs-check` still exits 0. Document the manual verification step in the script comments or commit message.
  - [ ] (Removed) The previously proposed "warn if CHANGELOG has no `[Unreleased]` entries when TO_DO has open items" check is dropped: open TO_DO items are unstarted future work and do not imply missing changelog entries (which record *completed* changes), so the check would only produce false positives.

- [ ] **6. Create slim pointer files for other agents**
  - [ ] Reconcile `GEMINI.md`'s unique guidance with `AGENTS.md`. Its unique content is: (a) the "Research → Strategy → Execution" development lifecycle, (b) "group bug-report fixes into logical phases," and (c) "always add unit tests for any bug fixes." Decide explicitly for each: migrate to `AGENTS.md`, or drop as redundant. Note that the Research/Strategy/Execution lifecycle is a superpowers concept not currently in `AGENTS.md`, so migrating it is a deliberate scope decision.
  - [ ] Verify Gemini tooling does not require specific `GEMINI.md` content before slimming it.
  - [ ] Rewrite `GEMINI.md` to point at `AGENTS.md` for all repo guidance, keeping only the minimum content required for tooling compatibility.
  - [ ] Create `QWEN.md` with exactly this content:

```markdown
# QWEN.md

See `AGENTS.md` for all repository guidance and rules.
```

- [ ] **7. Update repo-harness-guidance.md**
  - [ ] Add a "Documentation Lifecycle" subsection documenting the plan → complete → archive workflow. State whether it supplements (default) or replaces the existing Periodic Maintenance Checklist.
  - [ ] Document the CHANGELOG (including the `Deferred` subsection decision from Task 2) and TO_DO conventions.

- [ ] **8. Audit loose and untimestamped artifacts**
  - [ ] Rename `archived/fix-a1-a6.md` to a timestamped name (`YYYY-MM-DD-<slug>.md`). It has no inbound references, so no link updates are needed.
  - [ ] Rename `archived/plan-repo-hygiene.md` to a timestamped name. **Update the four anchored links to it in `TO_DO.md`** (lines referencing `archived/plan-repo-hygiene.md#...`) so they continue to resolve.
  - [ ] **Keep** `docs/api-discovery-month.md` in place and add a note (in the file and/or `docs/repo-harness-guidance.md`) explaining it is a generated/reference artifact. Do **not** move it: `src/github_usage/scripts/api_discovery_month.py` writes to that exact path, and it is referenced by `README.md`, `cli.py`, `CHANGELOG.md`, and `plan-export-reports.md`.

- [ ] **9. Audit existing assessment files**
  - [ ] Review the three files in `docs/assessments/` (`bug-report-20260616-143630.md`, `bug-report-20260620-235700.md`, `bug-report-20260621-000000.md`). For each, decide: still relevant (keep), or superseded by a completed/archived bug-fix plan (archive or annotate as resolved). The existing `scripts/docs-check` 30-day age warning is retained for future staleness; this task is a one-time content review, not an age sweep (none are currently >30 days old).

- [ ] **10. Archive this plan** (final step)
  - [ ] After all tasks above and the Verification checklist pass, mark every task `[x]`, prepend `**Done:**` notes per `AGENTS.md`, set this plan's banner to `> **Status:** COMPLETE` (note the merge commit), and move this file to `docs/superpowers/plans/archived/`.

---

## Verification

- [ ] `scripts/check` passes (syntax, tests, smoke, sizes).
- [ ] `scripts/docs-check` passes (exits 0), and the new completed-plan warning has been manually confirmed to fire on a throwaway COMPLETE-banner plan (Task 5).
- [ ] `scripts/smoke` passes (no-op for this plan — no CLI changes).
- [ ] All completed plans live under `docs/superpowers/plans/archived/`; no completed plan remains in the non-archived plans directory (including this plan, per Task 10).
- [ ] `docs/plan-email-report.md` and `docs/plan-export-reports.md` no longer exist at their original locations.
- [ ] `AGENTS.md` contains explicit plan-lifecycle, release, and status-banner-format instructions.
- [ ] `GEMINI.md` and `QWEN.md` point to `AGENTS.md` and are mutually consistent with it.
- [ ] No internal links are broken — specifically, the `TO_DO.md` links to the renamed `plan-repo-hygiene.md` resolve, and `docs/api-discovery-month.md` references are unchanged.
- [ ] A `CHANGELOG.md` `[Unreleased]` entry was added under the appropriate subsection describing this documentation/process change (per `AGENTS.md`).
