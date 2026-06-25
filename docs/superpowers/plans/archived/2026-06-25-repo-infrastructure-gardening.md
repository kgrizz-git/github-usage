# Repo Infrastructure, Doc Gardening, and Agent Guidance

> **Status:** COMPLETE
> **Created:** 2026-06-25
>
> **Done (2026-06-25):** Implemented all 10 tasks. `AGENTS.md` now carries a full Documentation Lifecycle (plans/changelog/TO_DO/releases) with a canonical status-banner format; `CHANGELOG.md` sanctions the `Deferred` subsection; `TO_DO.md` trimmed to open items; six completed plans archived with normalized banners; two untimestamped archived plans renamed; `scripts/docs-check` gained an (anchored, warn-only) completed-plan check; `GEMINI.md` slimmed and `QWEN.md` created; `repo-harness-guidance.md` gained a Documentation Lifecycle section; the three bug-report assessments annotated as resolved; `api-discovery-month.md` annotated as a kept generated artifact. `scripts/check` (266 tests), `scripts/docs-check`, and `scripts/smoke` all pass. Deviations: (1) Task 3's TO_DO link-update step became moot because the `plan-repo-hygiene` links lived in completed sections that were removed; (2) Task 4's "Integration validation" box in `2026-06-21-bug-fixes.md` was intentionally left open with an explanatory note (unit coverage exists; no separate integration pass was run); (3) the docs-check regex was anchored to the blockquote (`^>`) to avoid matching prose that quotes the banner format.

**Goal:** Standardize agent guidance for documentation maintenance, plan lifecycle, and changelog hygiene. Establish `AGENTS.md` as the single source of truth for all coding agents. Clean up accumulated stale artifacts and define a repeatable workflow.

---

## Conventions used by this plan

- **Status banner format (canonical):** `> **Status:** COMPLETE` — colon *outside* the bold. Use this exact form for new banners so the Task 5 regex (`\*\*Status:\*\*\s*COMPLET`) detects it. Do not use `> **Status: COMPLETE**`.
- **Legacy `COMPLETED` banners are tolerated.** Some existing plans use the past-tense `> **Status:** COMPLETED ...` form. The Task 5 regex prefix-matches both, so they are detected. When a plan is being edited for another reason (see Task 4), normalize its banner to the canonical `COMPLETE` form; otherwise leave it.
- **Plan filenames:** `YYYY-MM-DD-<slug>.md`.

## Dependencies & ordering

1. **Task 1 lands first.** Tasks 2 and 3 implement conventions that Task 1 documents in `AGENTS.md`; Task 1 must land before or alongside them.
2. **Task 5 (new docs-check warnings) lands after Task 4.** Otherwise running `docs-check` mid-change warns about the completed plans that Task 4 is in the process of archiving.
3. **Task 10 (self-archive this plan) is last**, after every other task and the Verification checklist pass.

---

## Current State & Problems

- `AGENTS.md` lacks a single-place documentation lifecycle, explicit release instructions, and a stated status-banner format (Task 1).
- `CHANGELOG.md` uses an undocumented `### Deferred` subsection (Task 2); `TO_DO.md` mixes completed and open items (Task 3).
- Several plans are complete in practice but have missing/contradictory status banners or unchecked tasks, blocking clean archival (Task 4); `scripts/docs-check` does not flag completed-but-unarchived plans (Task 5).
- `GEMINI.md` carries unique guidance to reconcile with `AGENTS.md`; `QWEN.md` does not exist (Task 6).
- `docs/repo-harness-guidance.md` has no documentation-lifecycle section (Task 7).
- `archived/` holds untimestamped plans (`fix-a1-a6.md`, `plan-repo-hygiene.md`); two completed plans (`plan-email-report.md`, `plan-export-reports.md`) sit at the `docs/` root instead of the canonical plans dir; `docs/api-discovery-month.md` is a generated report kept intentionally (Task 8).

---

## Tasks

- [x] **1. Update AGENTS.md — Agent Workflow Section** (targeted edits; leave Code Style and Maintainer References unchanged)
  - [x] Edit the CHANGELOG bullet (the one beginning "After completing any user-visible feature or fix...") to match the `[Unreleased]` convention, replacing the "topmost release section" wording.
  - [x] Edit the TO_DO bullet (the one beginning "After completing a `TO_DO.md` item...") to match the new removal convention, replacing the "mark it `[x]` and keep it" wording.
  - [x] Add plan lifecycle instructions: create with a timestamped filename → work through tasks → mark items `[x]` → set the status banner to `> **Status:** COMPLETE` (canonical format above) → move to `docs/superpowers/plans/archived/`.
  - [x] Add release instructions: create a version section in `CHANGELOG.md`, move `[Unreleased]` items into it, and bump the version in **both** `src/github_usage/__init__.py` (`__version__`) and `pyproject.toml` (`version`) so the two stay in sync.
  - [x] Document the canonical status-banner format in `AGENTS.md` so all agents emit a form the docs-check can detect.

- [x] **2. Clean up CHANGELOG.md** (convention change: all in-progress work stays under `[Unreleased]`)
  - [x] Verify all unreleased items are under `[Unreleased]` in the correct subsections.
  - [x] Decide on the `### Deferred` subsection: sanction it by documenting `Deferred` as an allowed subsection (alongside `Added`, `Fixed`, `Changed`) in the format note, OR fold its entries into a clearly labeled location. Default: sanction and document it, since it is already in use and meaningful.
  - [x] Add a brief format note at the top referencing Keep a Changelog and listing the allowed subsections.
  - [x] Do not create a version section yet — remain on `[Unreleased]` until a release is tagged.

- [x] **3. Clean up TO_DO.md** (convention change: remove items when completed)
  - [x] Remove all items already marked `[x]` (completed).
  - [x] Consolidate sections where appropriate (e.g., merge related bug-fix sections).
  - [x] Add a note at the top: agents should remove items when completed.
  - [x] When removing completed items, preserve any still-relevant `[Plan]` links by confirming the linked plan still exists at the referenced path (see Task 8 for the `plan-repo-hygiene.md` rename, which affects four links here).

- [x] **4. Archive completed plans and fix statuses** (use the canonical banner format: `> **Status:** COMPLETE`)
  - [x] Fix `2026-06-14-repo-harness.md`: check off the last task (`Run verification and initialize git`) and add a `> **Status:** COMPLETE` banner.
  - [x] Fix `2026-06-16-bug-fixes.md`: add a top-level `> **Status:** COMPLETE` banner.
  - [x] Fix `2026-06-21-bug-fixes.md`: (a) correct the banner/body text that says the 7 bugs "are open" to state they are fixed (all 7 are `[x]`), resolving the contradiction; (b) decide the fate of the still-unchecked `- [ ] Integration validation (Fixes #3, #4)` item near the end of that file — check it off if the bug-fix PR covered it, or leave it unchecked with a one-line note explaining why it remains open. Do not archive a plan with an unexplained unchecked box.
  - [x] `2026-06-19-remaining-bug-fixes.md`: has a `> **Status:** COMPLETED 2026-06-19.` banner. No status *fix* needed, but normalize the banner to the canonical `> **Status:** COMPLETE` form (preserving the date/details on the same line) while archiving it (below).
  - [x] Fix `docs/plan-email-report.md` and `docs/plan-export-reports.md` (currently at the `docs/` root, not in `docs/superpowers/plans/`): add `> **Status:** COMPLETE` banners and done notes.
  - [x] Move `2026-06-14-repo-harness.md` → `archived/`.
  - [x] Move `2026-06-16-bug-fixes.md` → `archived/`.
  - [x] Move `2026-06-19-remaining-bug-fixes.md` → `archived/`.
  - [x] Move `2026-06-21-bug-fixes.md` → `archived/`.
  - [x] Move `docs/plan-email-report.md` → `docs/superpowers/plans/archived/plan-email-report.md` (implemented: `email_report.py` exists, CLI subcommand works).
  - [x] Move `docs/plan-export-reports.md` → `docs/superpowers/plans/archived/plan-export-reports.md` (implemented: all `export_*.py` modules exist, `--export` flag works).

- [x] **5. Enhance scripts/docs-check** (implement after Task 4 so the new warning does not fire on plans being archived in the same change)
  - [x] Add a check: warn (do not fail) if any non-archived `.md` plan in `docs/superpowers/plans/` contains a regex match for `\*\*Status:\*\*\s*COMPLET` (intentionally matches both `COMPLETE` and legacy `COMPLETED`). Include the filename and matching line in the warning.
  - [x] Verify the new warning actually fires: run `docs-check` against a temporary throwaway plan containing a COMPLETE banner (placed in an untracked temp dir or created then removed) and confirm the warning appears and that `docs-check` still exits 0. Document the manual verification step in the script comments or commit message.

- [x] **6. Create slim pointer files for other agents**
  - [x] Reconcile `GEMINI.md`'s three unique items — (a) "Research → Strategy → Execution" lifecycle, (b) "group bug-report fixes into logical phases," (c) "always add unit tests for bug fixes" — deciding per-item to migrate to `AGENTS.md` or drop as redundant. Note (a) is a superpowers concept not yet in `AGENTS.md`, so migrating it is a scope decision.
  - [x] Verify Gemini tooling does not require specific `GEMINI.md` content before slimming it.
  - [x] Rewrite `GEMINI.md` to point at `AGENTS.md` for all repo guidance, keeping only the minimum content required for tooling compatibility.
  - [x] Create `QWEN.md` with exactly this content:

```markdown
# QWEN.md

See `AGENTS.md` for all repository guidance and rules.
```

- [x] **7. Update repo-harness-guidance.md**
  - [x] Add a "Documentation Lifecycle" subsection documenting the plan → complete → archive workflow.
  - [x] Reconcile the overlap with the existing Periodic Maintenance Checklist, which already has a bullet "Review `docs/superpowers/plans/` — move completed or superseded plans to `docs/superpowers/plans/archived/`." Recommended: replace that bullet with a one-line cross-reference to the new "Documentation Lifecycle" subsection so the workflow is described in exactly one place.
  - [x] Document the CHANGELOG (including the `Deferred` subsection decision from Task 2) and TO_DO conventions.

- [x] **8. Audit loose and untimestamped artifacts**
  - [x] Rename `archived/fix-a1-a6.md` to a timestamped name (`YYYY-MM-DD-<slug>.md`). It has no inbound references, so no link updates are needed.
  - [x] Rename `archived/plan-repo-hygiene.md` to a timestamped name. **Update the four anchored links to it in `TO_DO.md`** (lines referencing `archived/plan-repo-hygiene.md#...`) so they continue to resolve.
  - [x] **Keep** `docs/api-discovery-month.md` in place and add a note (in the file and/or `docs/repo-harness-guidance.md`) explaining it is a generated/reference artifact. Do **not** move it: `src/github_usage/scripts/api_discovery_month.py` writes to that exact path, and it is referenced by `README.md`, `cli.py`, `CHANGELOG.md`, and `plan-export-reports.md`.

- [x] **9. Audit existing assessment files**
  - [x] Review the three files in `docs/assessments/` (`bug-report-20260616-143630.md`, `bug-report-20260620-235700.md`, `bug-report-20260621-000000.md`). For each, decide: keep (still relevant) or archive/annotate as resolved (superseded by a completed bug-fix plan). One-time content review — not an age sweep (none are >30 days old; the `docs-check` 30-day warning is retained for the future).

- [x] **10. Archive this plan** (final step)
  - [x] After all tasks above and the Verification checklist pass, mark every task `[x]`, prepend `**Done:**` notes per `AGENTS.md`, set this plan's banner to `> **Status:** COMPLETE` (note the merge commit), and move this file to `docs/superpowers/plans/archived/`.

---

## Verification

- [x] `scripts/check` passes (syntax, tests, smoke, sizes).
- [x] `scripts/docs-check` passes (exits 0), and the new completed-plan warning has been manually confirmed to fire on a throwaway COMPLETE-banner plan (Task 5).
- [x] `scripts/smoke` passes (no-op for this plan — no Python CLI entrypoint changes; the `scripts/docs-check` edits in Task 5 are covered by `docs-check` itself).
- [x] All completed plans live under `docs/superpowers/plans/archived/`; no completed plan remains in the non-archived plans directory (including this plan, per Task 10).
- [x] `docs/plan-email-report.md` and `docs/plan-export-reports.md` no longer exist at their original locations.
- [x] `AGENTS.md` contains explicit plan-lifecycle, release, and status-banner-format instructions.
- [x] `GEMINI.md` and `QWEN.md` point to `AGENTS.md` and are mutually consistent with it.
- [x] No internal links are broken — specifically, the `TO_DO.md` links to the renamed `plan-repo-hygiene.md` resolve, and `docs/api-discovery-month.md` references are unchanged.
- [x] A `CHANGELOG.md` `[Unreleased]` entry was added under the appropriate subsection describing this documentation/process change (per `AGENTS.md`).
