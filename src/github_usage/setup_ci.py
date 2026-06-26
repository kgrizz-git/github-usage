"""CI secret configuration for the setup wizard.

Pushed via ``gh secret set`` so the scheduled GitHub Actions workflow
can authenticate against the GitHub API. Lifted out of
``setup_wizard`` so the wizard file stays focused on orchestration.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404

from .setup_prompts import _prompt_yes_no

CI_SECRETS = (
    (
        "GH_USAGE_TOKEN",
        (
            "GitHub PAT that can read your personal repos and billing "
            "(classic: `repo` scope; fine-grained: `Metadata: Read-only` + "
            "`Plan: Read-only` on your user account)"
        ),
    ),
    ("RESEND_API_KEY", "Resend API key"),
    ("REPORT_EMAIL", "Recipient email address"),
    ("RESEND_FROM", "Sender address on your verified Resend domain"),
)


def _set_ci_gh_token() -> subprocess.CompletedProcess:
    """Set GH_USAGE_TOKEN, offering to pipe the current gh auth token."""
    try:
        gh_result = subprocess.run(  # nosec
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if (
            gh_result.returncode == 0
            and gh_result.stdout.strip()
            and _prompt_yes_no("Use token from `gh auth token`?", True)
        ):
            return subprocess.run(  # nosec
                ["gh", "secret", "set", "GH_USAGE_TOKEN"],
                input=gh_result.stdout.strip(),
                text=True,
                check=False,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return subprocess.run(["gh", "secret", "set", "GH_USAGE_TOKEN"], check=False)  # nosec


def _configure_ci_secrets() -> None:
    if not shutil.which("gh"):
        print("Install GitHub CLI (`gh`) and authenticate to set repository secrets.")
        return
    print("\nGitHub Actions secrets (stored in GitHub, not in this repo):")
    for name, description in CI_SECRETS:
        print(f"  {name}: {description}")
    if not _prompt_yes_no("Set secrets with `gh secret set` now?", False):
        print("Skipped CI secret setup.")
        print("Manual test after setting secrets: gh workflow run email-report.yml")
        return
    for name, description in CI_SECRETS:
        print(f"\n{name} — {description}")
        if not _prompt_yes_no(f"Set {name}?", True):
            continue
        if name == "GH_USAGE_TOKEN":
            result = _set_ci_gh_token()
        else:
            result = subprocess.run(["gh", "secret", "set", name], check=False)  # nosec
        if result.returncode != 0:
            print(f"Failed to set {name}.")
            return
    print("\nCI secrets updated.")
    print("Enable Secret Scanning and Push Protection in GitHub: Settings > Code security.")
    print("Manual test: gh workflow run email-report.yml")


def _configure_dev_hooks() -> None:
    if not shutil.which("pre-commit"):
        print("Install dev tools first: python3 -m pip install -e '.[dev]'")
        return
    print("\nDeveloper hooks:")
    if _prompt_yes_no("Install pre-commit hooks (commit + push)?", True):
        for args in (
            ["pre-commit", "install"],
            ["pre-commit", "install", "--hook-type", "pre-push"],
        ):
            result = subprocess.run(args, check=False)  # nosec
            if result.returncode != 0:
                print(f"Failed: {' '.join(args)}")
                return
        print("Installed pre-commit hooks for commit and push.")
    if shutil.which("gitleaks"):
        print("Gitleaks is available for local secret scanning.")
    else:
        print("Install gitleaks for local secret scanning (also bundled in pre-commit).")
