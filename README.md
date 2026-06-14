# github-usage

`github-usage` is a Python CLI for generating a GitHub monthly usage and billing report. It reports GitHub Actions usage, repository-level Actions usage, Copilot premium requests, Git LFS usage, billing history, limits, and a final summary of the largest consumers.

## Current Status

This repo is being converted from standalone scripts into a reusable Python package. The current packaged entry point wraps the v3 script behavior while the implementation is split into smaller modules over time.

## Requirements

- Python 3.11 or newer
- A GitHub token with the `user` scope for billing endpoints
- Optional: GitHub CLI (`gh`) for token discovery

## Run

From a source checkout:

```sh
PYTHONPATH=src python3 -m github_usage --help
PYTHONPATH=src python3 -m github_usage
```

Compatibility wrapper:

```sh
PYTHONPATH=src ./github-usage-v3
```

After installing the package:

```sh
python3 -m pip install -e .
github-usage
```

## Authentication

Token resolution order:

1. Command-line argument
2. `GITHUB_TOKEN` environment variable
3. `gh auth token`
4. `~/.config/github-cli/github.yaml`

Examples:

```sh
GITHUB_TOKEN=ghp_example github-usage
github-usage ghp_example
```

If `gh auth token` works in your terminal but not in a sandboxed agent session, rerun through an approved elevated command or pass `GITHUB_TOKEN` explicitly.

## Development

Run the standard checks:

```sh
scripts/check
```

Run smoke checks:

```sh
scripts/smoke
```

Install optional development tools:

```sh
python3 -m pip install -e '.[dev]'
pre-commit install
```

Run optional security checks:

```sh
scripts/security
```

## Repository Layout

- `src/github_usage/`: package source
- `tests/`: unit tests and future fixtures
- `scripts/`: canonical local automation commands
- `docs/`: maintainer guidance
- `backups/`: historical script versions, not active code

## Safety Notes

Do not commit tokens, raw private API responses, generated billing reports, or local environment files. Tests should use fake tokens and fixtures.
