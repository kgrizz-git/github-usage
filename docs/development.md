# Development

[Back to README](../README.md)

Run these commands from the repository root. The check scripts use the repository-local `.venv` managed by `scripts/python`; install tools there before running checks. The `gui` extra is needed for the TUI tests.

Run the main verification script:

```sh
scripts/check
```

Run CLI smoke checks:

```sh
scripts/smoke
```

The invalid-token GitHub probe is skipped by default. Set `GITHUB_USAGE_LIVE_TESTS=1` only to opt into that live authentication check.

Install optional development tools:

```sh
scripts/python -m pip install -e '.[dev,gui]'
scripts/python -m pre_commit install
scripts/python -m pre_commit install --hook-type pre-push
```

Run `./start.sh setup` and choose **8** (Developer security hooks) to install commit and push hooks (including Gitleaks).

Run local security checks:

```sh
scripts/security
```

The public GitHub repository also uses GitHub code scanning with CodeQL default setup. The local `Security` workflow covers repository-level checks that can run without uploading SARIF: Gitleaks, `pip-audit`, Bandit, and a zizmor check that fails on GitHub Actions references with known security advisories (including SHA-pinned actions, which Dependabot alerts do not cover).

`scripts/security` audits the full locked dependency set from `uv.lock` (all extras) when `uv` is installed; without `uv` it audits the current Python environment instead.

Run documentation checks:

```sh
scripts/docs-check
```

## Repository Layout

- `src/github_usage/`: active package source
- `tests/`: tests and existing fixtures
- `scripts/`: canonical local automation commands
- `docs/`: user guides and maintainer guidance
- `backups/`: transient pre-modification backups (`*.bak`), pruned by `scripts/prune-backups`; not active code

## Maintainer reference

See [Repository harness guidance](repo-harness-guidance.md) for conventions and [AGENTS.md](../AGENTS.md) for repository instructions.

## Roadmap

See [TO_DO.md](../TO_DO.md) for planned work on deeper Actions analysis and platform-specific setup improvements. Historical email reports are blocked/indefinitely deferred until the billing API supports the required period queries. Export formats (CSV, XLSX, PDF, JSON, text) are implemented.
