# Certifi security update

> **Status:** COMPLETE

- [x] Confirm alert #18 and its first fixed version, certifi 2026.10.19.
- [x] Upgrade only certifi in uv.lock and document the change.
- [x] Audit the locked dependencies, run repository checks, and review the candidate.

The vulnerable version was 2026.6.17. The vulnerable trust bundle is used by requests, a transitive development-tool dependency; application GitHub requests use the standard library. Preserve TLS verification and all other locked package versions.

**Done:** 2026-10-20 — Updated certifi 2026.6.17 to 2026.10.19, including matching artifacts/hashes; no other package versions changed. No deviations.

Validation: `uv sync --locked --all-extras --python 3.11`, lockfile version comparison, requests/certifi import and SSL context load with certificate/hostname verification enabled, `scripts/security` (no known vulnerabilities; no secret or Bandit findings), `scripts/check`, `scripts/docs-check`, and `git diff --check` passed. Independent OpenCode DeepSeek V4.1 Flash Free investigation and candidate review confirmed transitive development-tool scope, consistent lock export, removal of emSign ECC Root CA - G3, and no concrete bypass/regression. No new source functions or tests were needed for the dependency-only change.

GitHub alert #18 can close after this update reaches the default branch and GitHub refreshes its dependency graph; branch publication alone does not establish alert closure.
