"""Authentication helpers for github-usage."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from pathlib import Path

# Token discovery intentionally shells out to the GitHub CLI.


def resolve_token():
    if len(sys.argv) > 1:
        return sys.argv[1]
    token = os.environ.get("GITHUB_TOKEN", "").strip()
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


def check_user_scope(api):
    """Check if the token has the 'user' scope required for billing endpoints.
    Returns True if scope is present, False otherwise."""
    import http.client

    conn = http.client.HTTPSConnection("api.github.com")
    conn.request("GET", "/user", headers=api.headers)
    resp = conn.getresponse()
    scopes_header = resp.getheader("X-OAuth-Scopes", "")
    resp.read()  # consume response
    scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
    return "user" in scopes
