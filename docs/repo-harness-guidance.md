# Repo Harness Guidance

This document captures guidance for turning this repository from a folder of scripts into a reusable, maintainable Python CLI project. The emphasis is repo harness engineering: the project structure, scripts, checks, automation, and maintenance conventions that make future code changes easier to run, verify, review, and ship.

## Research Summary

OpenAI's Codex best-practices docs frame a good repository harness as durable context plus repeatable verification. They recommend using `AGENTS.md` for repo layout, run commands, build/test/lint commands, engineering conventions, constraints, and "done" criteria, while keeping it short and updating it only when repeated mistakes show a real need. Source: [OpenAI Codex Best Practices](https://developers.openai.com/codex/learn/best-practices).

OpenAI's OSS maintenance article gives a useful split between model judgment and deterministic repo mechanics: interpretation, comparison, and reporting can stay with the model, while repeated shell work belongs in `scripts/`. The article specifically recommends scripts for fixed-order verification, log collection, reruns, release diffing, and helper commands such as `start`, `stop`, `status`, `logs`, `collect`, and `rerun`. Source: [Using skills to accelerate OSS maintenance](https://developers.openai.com/blog/skills-agents-sdk).

OpenAI's cloud environment docs reinforce that setup should be explicit and repeatable. Codex checks out the repo, runs setup or maintenance scripts, then uses `AGENTS.md` to find project-specific lint and test commands. Secrets are available only during setup in Codex cloud, which is a useful reminder to design scripts so normal test and verification paths do not depend on persistent secret access. Source: [Codex Cloud Environments](https://developers.openai.com/codex/cloud/environments).

The Python Packaging User Guide recommends a conventional package layout with `pyproject.toml`, `README.md`, `LICENSE`, `src/`, and `tests/`. It also notes that `pyproject.toml` is where build system and project metadata belong. Source: [Packaging Python Projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/).

The PyPA discussion of `src/` layout says it helps prevent accidental use of the in-development copy of the code by separating import packages from the repository root. For a CLI that should behave the same when installed and when tested, this is worth adopting. Source: [src layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).

GitHub's Python Actions guide shows the standard CI shape: check out the repo, set up Python, install dependencies, run tests, optionally cache dependencies, and use a Python version matrix when compatibility matters. Source: [Building and testing Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).

GitHub's security docs recommend layered repository protection: secret scanning, push protection, code scanning with CodeQL, Dependabot alerts/updates, dependency review, and explicit workflow hardening. Source: [GitHub Secret Scanning](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning), [GitHub Push Protection](https://docs.github.com/en/code-security/concepts/secret-security/push-protection), [CodeQL Code Scanning](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning), [GitHub Actions Secure Use](https://docs.github.com/en/actions/reference/security/secure-use), and [Dependabot Options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).

For local hooks, `pre-commit` is the standard harness for running checks before commits. Secret detection can be wired locally and in CI with tools such as Gitleaks, while Python dependency auditing can use `pip-audit`, and Python static security scanning can use Bandit. Source: [pre-commit](https://pre-commit.com/), [Gitleaks](https://github.com/gitleaks/gitleaks), [pip-audit](https://pypi.org/project/pip-audit/), and [Bandit](https://bandit.readthedocs.io/en/latest/).

Keep a Changelog recommends a human-readable changelog grouped by change type: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`. Source: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Semantic Versioning recommends declaring the public API and using `MAJOR.MINOR.PATCH`: patch for compatible bug fixes, minor for backward-compatible additions, and major for incompatible changes. For this repo, the public API is primarily the CLI interface, config/env behavior, output contract, and importable Python functions once we expose them. Source: [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## Guidance For This Repo

### Target Shape

Move toward this structure:

```text
github-usage/
├── AGENTS.md
├── CHANGELOG.md
├── LICENSE
├── README.md
├── pyproject.toml
├── .pre-commit-config.yaml
├── .github/
│   ├── dependabot.yml
│   └── workflows/
│       ├── ci.yml
│       └── security.yml
├── docs/
│   └── repo-harness-guidance.md
├── scripts/
│   ├── check
│   ├── format
│   └── smoke
├── src/
│   └── github_usage/
│       ├── __init__.py
│       ├── __main__.py
│       ├── api.py
│       ├── auth.py
│       ├── billing.py
│       ├── cli.py
│       ├── models.py
│       └── report.py
├── tests/
│   ├── fixtures/
│   ├── test_auth.py
│   ├── test_cli.py
│   └── test_report.py
└── backups/
```

Keep `backups/` for historical reference only. New development should happen in `src/github_usage/`, with a console entry point such as `github-usage = "github_usage.cli:main"`.

### Harness Principles

Make common actions deterministic:

- `scripts/check`: run formatting check, lint/type checks if configured, tests, and a no-token CLI smoke test.
- `scripts/format`: apply formatter only.
- `scripts/smoke`: run commands that prove the package imports, the CLI starts, `--help` works, and auth failure messages remain clear.
- `scripts/security`: run local security checks that do not require cloud-only GitHub features.
- `scripts/docs-check`: check links, required docs, and README/CLI drift where practical.
- CI should call the same scripts humans and agents call locally.

Design tests so most do not need GitHub credentials:

- Unit test token resolution without printing or requiring real tokens.
- Unit test API request construction with mocked HTTP responses.
- Snapshot or golden-file test report rendering from fixtures.
- Include one optional live test path gated behind an explicit env var, for example `GITHUB_USAGE_LIVE_TESTS=1`.

Keep agent guidance concise:

- Put durable repo instructions in `AGENTS.md`: layout, commands, token safety rules, and done criteria.
- Do not put broad philosophy in `AGENTS.md`; link to this document for background.
- Update `AGENTS.md` only after repeated friction or a stable workflow decision.

Treat secrets as runtime inputs:

- Never commit tokens, raw API responses containing private data, or generated reports with sensitive account details.
- Prefer `GITHUB_TOKEN`, a CLI argument, or `gh auth token`.
- Tests should use fake tokens and fixtures.
- Document when elevated/local keychain access is needed, because sandboxed runs may not see `gh` keyring tokens.

### CI, Hooks, Security, And Hygiene

Use a layered setup. No single check catches everything, and some checks belong in different places.

Local hooks:

- Add `.pre-commit-config.yaml` and document `pre-commit install`.
- Run cheap, deterministic checks before commit: whitespace, EOF newline, YAML/TOML validity, Python formatting, Python linting, and secret scanning.
- Include Gitleaks as a local hook so obvious tokens are caught before they reach Git.
- Keep hooks fast. Heavier scans should be in `scripts/security` and CI.

CI:

- `.github/workflows/ci.yml` should run on pull requests and pushes to the main branch.
- CI should install the package, run `scripts/check`, and test against the supported Python version range.
- Set minimal workflow permissions by default, for example `contents: read`.
- Avoid printing environment variables, tokens, GitHub API responses, or full billing reports in CI logs.
- Use pinned major versions for common GitHub Actions initially, and let Dependabot update Actions dependencies.

Security workflow:

- `.github/workflows/security.yml` should run on pull requests, pushes to main, and a scheduled cadence.
- Run `scripts/security`, including at least Gitleaks, `pip-audit`, and Bandit once the package exists.
- Enable GitHub secret scanning and push protection in repository settings when available.
- Enable CodeQL code scanning for Python.
- Add Dependabot config for both Python dependencies and GitHub Actions.
- Consider an Actions workflow linter such as `zizmor` once workflows become non-trivial.

Suggested `scripts/security` contents:

```sh
gitleaks detect --source . --redact
pip-audit
bandit -r src
```

Adjust these commands after the package and dependency manager are chosen. For example, if the repo uses `uv`, run audits against the locked environment rather than an ad hoc install.

Doc gardening:

- Treat docs as part of the public API for this project.
- Keep `README.md` focused on users: what it does, install, run, auth, examples, troubleshooting.
- Keep `docs/` focused on maintainers: architecture, harness guidance, release checklist, API notes.
- Update docs in the same change as CLI flag, output, auth, or installation changes.
- Add a docs checklist to PR/release review: README examples still run, CLI help matches docs, changelog mentions user-visible changes, and troubleshooting covers common auth failures.

Repo hygiene:

- Add `.gitignore` for virtualenvs, caches, build outputs, coverage files, generated reports, and local secret files.
- Keep generated output out of source control unless it is a curated fixture under `tests/fixtures/`.
- Keep `backups/` out of normal package discovery and CI except for explicit historical-reference checks.
- Prefer one canonical command per task. If humans and agents need the same recipe twice, move it into `scripts/`.
- Schedule a monthly maintenance pass: update dependencies, prune stale docs, review ignored files, run the security workflow, and verify the release checklist still reflects reality.

### Release And Maintenance

Adopt `CHANGELOG.md` before publishing packages or tags. Use Keep a Changelog categories and keep entries user-facing.

Use SemVer once the CLI has a documented contract:

- Patch: bug fix, clearer error message, internal refactor.
- Minor: new report section, new output format, new optional flag.
- Major: breaking CLI flags, changed default output contract, removed auth method, incompatible config behavior.

Before release, run a release check:

- Compare current branch against the previous tag.
- Confirm CLI help and README examples match.
- Confirm changelog mentions behavior changes.
- Run `scripts/check`.
- Run optional live smoke test if credentials are available.

## Initial Implementation Checklist

1. Add `README.md` with purpose, install/run examples, auth methods, and safety notes.
2. Add `pyproject.toml` with package metadata, dependencies, console script, formatter, and test config.
3. Move the v3 script into `src/github_usage/` modules without changing behavior first.
4. Add `tests/` with auth, CLI, and report-rendering fixtures.
5. Add `scripts/check`, `scripts/format`, and `scripts/smoke`.
6. Add `scripts/security` and `.pre-commit-config.yaml` with basic hygiene and secret-detection hooks.
7. Add GitHub Actions CI that runs `scripts/check` on supported Python versions.
8. Add GitHub Actions security workflow plus Dependabot config.
9. Add `AGENTS.md` with the concise operational instructions.
10. Add `CHANGELOG.md` and start at `0.1.0` while the CLI contract is still settling.
11. Add `.gitignore` and docs/release hygiene checklists before the first tagged release.
