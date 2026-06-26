"""Local email-report secret management for the setup wizard.

Lifted out of ``setup_wizard`` so the wizard file stays focused on
orchestration. Reads, writes, and applies ``.env.email-report`` and
resolves the ``GITHUB_TOKEN`` from existing env, ``gh auth token``,
or a fresh prompt.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404

from .setup_config import SetupPaths, read_env_file, write_env_file
from .setup_prompts import _prompt_value, _prompt_yes_no


def _resolve_github_token(existing: dict[str, str]) -> str:
    token = existing.get("GITHUB_TOKEN", "").strip()
    if token and _prompt_yes_no("Keep existing GITHUB_TOKEN in .env.email-report?", True):
        return token
    if shutil.which("gh"):
        try:
            result = subprocess.run(  # nosec
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if (
                result.returncode == 0
                and result.stdout.strip()
                and _prompt_yes_no("Use token from `gh auth token`?", True)
            ):
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        if _prompt_yes_no("Run `gh auth refresh -h github.com -s user` now?", True):
            refresh = subprocess.run(["gh", "auth", "refresh", "-h", "github.com", "-s", "user"])  # nosec
            if refresh.returncode == 0:
                result = subprocess.run(  # nosec
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
    token = _prompt_value("GitHub token", secret=True)
    return token.strip()


def _configure_env_secrets(paths: SetupPaths) -> None:
    existing = read_env_file(paths.env_file)
    print("\nLocal email secrets (stored in .env.email-report, mode 600):")
    values = dict(existing)
    values["GITHUB_TOKEN"] = _resolve_github_token(existing)
    for key in ("RESEND_API_KEY", "REPORT_EMAIL", "RESEND_FROM"):
        current = existing.get(key, "")
        if current and _prompt_yes_no(f"Keep existing {key}?", True):
            values[key] = current
            continue
        secret = key != "REPORT_EMAIL"
        values[key] = _prompt_value(key, current, secret=secret).strip()
    write_env_file(paths.env_file, values)
    print(f"Wrote {paths.env_file.name} (permissions 600)")


def _apply_env(paths: SetupPaths) -> None:
    for key, value in read_env_file(paths.env_file).items():
        os.environ[key] = value
