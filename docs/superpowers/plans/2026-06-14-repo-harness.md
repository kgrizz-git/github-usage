# Repo Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the folder of scripts into a reusable Python CLI repository with tests, docs, local scripts, CI, security checks, and git ignore hygiene.

**Architecture:** Keep the current v3 report as `github_usage.legacy` for behavior preservation, then expose a small package CLI wrapper. Add repo harness files around that package before deeper modular refactors.

**Tech Stack:** Python standard library, unittest, setuptools, GitHub Actions, pre-commit, Gitleaks, pip-audit, Bandit, CodeQL.

---

## Tasks

- [x] Add failing tests for CLI help, missing-token behavior, and token resolution.
- [x] Move the v3 implementation into `src/github_usage/legacy.py`.
- [x] Add package entrypoints in `src/github_usage/cli.py` and `src/github_usage/__main__.py`.
- [x] Add `pyproject.toml` package metadata and console script.
- [x] Add local harness scripts under `scripts/`.
- [x] Add README, changelog, license, gitignore, AGENTS.md, pre-commit config, CI, security workflow, and Dependabot config.
- [ ] Run verification and initialize git.
