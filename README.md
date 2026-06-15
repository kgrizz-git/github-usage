# github-usage

[![CI](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/ci.yml)
[![Security](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml/badge.svg)](https://github.com/kgrizz-git/github-usage/actions/workflows/security.yml)

`github-usage` is a Python command-line tool for reviewing GitHub billing and usage data from your account. It reports GitHub Actions minutes and storage, repository-level Actions usage, Copilot premium requests, Git LFS usage, billing history, limits, and the largest current-month resource consumers.

The project started as a personal reporting script and is being shaped into a reusable Python package. The packaged CLI currently preserves the v3 report behavior while the internals are split into smaller, testable modules.

## Features

- Account and plan summary
- GitHub Actions minutes, storage, and per-SKU cost breakdown
- Per-repository Actions usage
- Copilot premium request usage by model
- Git LFS usage
- Current-month net/gross cost estimate
- Full billing history summary from the GitHub billing API
- Local smoke, security, and documentation checks for maintainers

## Requirements

- Python 3.11 or newer
- A GitHub token with the `user` scope for billing endpoints
- Optional: GitHub CLI (`gh`) for token discovery

## Install

From a checkout:

```sh
python3 -m pip install -e .
```

Then run:

```sh
github-usage --help
github-usage
```

You can also run without installing:

```sh
PYTHONPATH=src python3 -m github_usage --help
PYTHONPATH=src python3 -m github_usage
```

The root-level `github-usage` file is a compatibility wrapper for the packaged CLI.

## Authentication

The CLI resolves a token in this order:

1. Command-line argument
2. `GITHUB_TOKEN` environment variable
3. `gh auth token`
4. `~/.config/github-cli/github.yaml`

Recommended setup:

```sh
gh auth login -h github.com -s user
github-usage
```

You can also pass a token through the environment:

```sh
GITHUB_TOKEN="<token>" github-usage
```

Passing a token as a command-line argument is supported, but it can expose the token through shell history or process listings. Prefer `gh auth login` or `GITHUB_TOKEN`.

## Privacy

This tool prints account, repository, billing, and usage details to stdout. Treat generated output as sensitive unless you have reviewed and redacted it. Do not commit tokens, raw private API responses, generated billing reports, or local environment files.

## Development

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
```

Run local security checks:

```sh
scripts/security
```

The public GitHub repository also uses GitHub code scanning with CodeQL default setup. The local `Security` workflow covers repository-level checks that can run without uploading SARIF: Gitleaks, `pip-audit`, and Bandit.

Run documentation checks:

```sh
scripts/docs-check
```

## Repository Layout

- `src/github_usage/`: active package source
- `tests/`: unit tests and future fixtures
- `scripts/`: canonical local automation commands
- `docs/`: maintainer guidance
- `backups/`: historical script versions, not active code

## Roadmap

See [TO_DO.md](TO_DO.md) for planned work, including export formats, JSON output, report fixtures, and modularizing the current legacy implementation.
