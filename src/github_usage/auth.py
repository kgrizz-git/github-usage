"""Authentication helpers for github-usage."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from pathlib import Path

# Token discovery intentionally shells out to the GitHub CLI.


def print_missing_token_error(usage_command="github-usage"):
    """Print a human-readable error explaining how to supply a GitHub token."""
    print("Error: No GitHub token found.")
    print(f"  Usage: {usage_command} <token>")
    print("  Or set GITHUB_TOKEN env var.")
    print("  Or run: gh auth login")


def resolve_token(argv: Sequence[str] | None = None):
    """Return the GitHub token from argv, env, gh CLI, or config file; None if not found."""
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        return argv[0]
    token = (
        os.environ.get("GH_USAGE_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    )
    if token:
        return token
    try:
        # Fixed gh CLI invocation, no user-controlled executable.
        result = subprocess.run(  # nosec
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    config = Path.home() / ".config" / "github-cli" / "github.yaml"
    if config.exists():
        content = config.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("oauth_token:"):
                token = line.split(":", 1)[1].strip().strip("'\"")
                if token:
                    return token
    return None


def check_user_scope(api, user=None):
    """Return True if the token is accepted on a user-scoped endpoint
    (200 from GET /user), False otherwise."""
    if user is not None:
        return bool(user.get("login"))
    try:
        user = api.request("GET", "/user")
        return bool(user.get("login"))
    except RuntimeError:
        return False
