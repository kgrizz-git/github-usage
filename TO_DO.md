# To Do

- [ ] Add report export support. Let the user create a CSV, XLSX, PDF, or similar report artifact. The CLI should support an explicit flag, for example `--export csv`, `--export xlsx`, `--export pdf`, or `--export none`; if no export option is provided in an interactive terminal, prompt the user whether they want an export file.
- [ ] Split `src/github_usage/legacy.py` into focused modules such as `auth.py`, `api.py`, `billing.py`, `report.py`, and `cli.py`.
- [ ] Add `--json` output for machine-readable reporting.
- [ ] Add `--output PATH` alongside `--export FORMAT`.
- [ ] Add `--no-interactive` so scripts and CI never hang on prompts.
- [ ] Add fixture-based tests for report rendering.
- [ ] Add a `--month YYYY-MM` flag so users can query a specific billing period.
- [ ] Add a redaction layer before writing export files, especially for usernames, repository names, and billing details.
