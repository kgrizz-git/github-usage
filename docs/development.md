# Development

[Back to README](../README.md)

Run these commands from the repository root.

Run the main verification script:

```sh
scripts/check
```

Run CLI smoke checks:

```sh
scripts/smoke
```

Install optional development tools:

```sh
python3 -m pip install -e '.[dev]'
pre-commit install
pre-commit install --hook-type pre-push
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
- `tests/`: unit tests and future fixtures
- `scripts/`: canonical local automation commands
- `docs/`: user guides and maintainer guidance
- `backups/`: transient pre-modification backups (`*.bak`), pruned by `scripts/prune-backups`; not active code

## Maintainer reference

See [Repository harness guidance](repo-harness-guidance.md) for conventions and [AGENTS.md](../AGENTS.md) for repository instructions.

## Roadmap

See [TO_DO.md](../TO_DO.md) for planned work, including historical email reports, deeper Actions analysis, and platform-specific setup improvements. Export formats (CSV, XLSX, PDF, JSON, text) are implemented.
