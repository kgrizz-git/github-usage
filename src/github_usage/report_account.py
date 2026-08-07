"""Account and API metadata sections for the legacy report."""

from __future__ import annotations

from datetime import UTC, datetime

from .terminal import print_section, print_sep


def fetch_rate_limits(api) -> dict:
    """Return the full ``GET /rate_limit`` payload."""
    data = api.request("GET", "/rate_limit")
    return data if isinstance(data, dict) else {}


def _print_standard_rate_limits(resources: dict) -> None:
    """Print the core / GraphQL / search / code-scanning rate-limit rows."""
    print()
    for name, key in [
        ("Core API", "core"),
        ("GraphQL API", "graphql"),
        ("Search API", "search"),
        ("Code Scanning", "code_scanning_upload"),
    ]:
        r = resources.get(key, {})
        if not isinstance(r, dict):
            r = {}
        rem = r.get("remaining")
        if rem is None:
            rem = "?"
        lim = r.get("limit")
        if lim is None:
            lim = "?"
        reset_ts = r.get("reset", 0)
        reset_str = ""
        if reset_ts:
            reset_str = (
                f"  (resets {datetime.fromtimestamp(reset_ts, tz=UTC).strftime('%H:%M UTC')})"
            )
        print(f"  {name:<25} {rem:>6} / {lim:<6} remaining{reset_str}")


def _print_premium_rate_limits(resources: dict) -> None:
    """Print the high-tier (limit > 5000) rate-limit rows."""
    print()
    print("  Premium API tiers:")
    for name, res in resources.items():
        if not isinstance(res, dict):
            continue
        limit = res.get("limit")
        if limit is None:
            limit = 0
        used = res.get("used")
        if used is None:
            used = 0
        if limit > 5000:
            pct = (used / limit * 100) if limit else 0
            print(f"    {name:<35} {used:>6} / {limit:<6} ({pct:.1f}% used)")
    print()


def render_rate_limits(data: dict) -> None:
    """Print rate limits from a pre-fetched ``/rate_limit`` response."""
    print_sep("API Rate Limit")
    resources = data.get("resources", {})
    if not isinstance(resources, dict):
        resources = {}
    _print_standard_rate_limits(resources)
    _print_premium_rate_limits(resources)


def fetch_account_info(api) -> dict:
    """Return account metadata from ``GET /user``."""
    user = api.request("GET", "/user")
    if not isinstance(user, dict):
        user = {}
    plan = user.get("plan", {})
    if not isinstance(plan, dict):
        plan = {}
    return {
        "login": user.get("login", "?"),
        "type": user.get("type", "?"),
        "plan": plan,
    }


def render_account_info(account: dict) -> None:
    """Print account details from a pre-fetched account dict."""
    print_sep("Account Info")
    username = account.get("login", "?")
    user_type = account.get("type", "?")
    plan = account.get("plan") or {}

    print(f"  Username:   {username}")
    print(f"  Account:    {user_type}")
    if plan:
        plan_name = plan.get("name", "?")
        space = plan.get("space", "?")
        collaborators = plan.get("collaborators", "?")
        private_repos = plan.get("private_repos", "?")
        print(f"  Plan:       {plan_name}")
        if space and space != 0:
            if isinstance(space, int | float):
                space_gb = space / (1024 * 1024 * 1024)
                print(f"  Space:      {space_gb:.1f} GB available")
            else:
                print(f"  Space:      {space} available")
        if collaborators:
            print(f"  Collaborators: {collaborators}")
        if private_repos:
            print(f"  Private repos: {private_repos} allowed")
    print()


def show_rate_limits(api):
    """Print a breakdown of GitHub API rate limits for the authenticated token."""
    render_rate_limits(fetch_rate_limits(api))


def show_account_info(api):
    """Print account details, plan info, and collaborator seat counts."""
    account = fetch_account_info(api)
    render_account_info(account)
    return account["login"], account["type"]


def render_what_else(username: str) -> None:
    """Print static pointers to other available billing endpoints."""
    print_section("Other Available Data Points")
    print("  Products available via billing API:")
    print("    - actions        : GitHub Actions compute & storage")
    print("    - copilot        : Copilot Chat, Agent, Code Review, etc.")
    print("    - git_lfs        : Git LFS storage")
    print("    - codespaces     : GitHub Codespaces compute & storage")
    print("    - packages       : GitHub Packages (npm, Docker, etc.)")
    print("    - models         : GitHub Models (LLM API usage)")
    print()
    print("  Other endpoints available:")
    print(f"    - /users/{username}/settings/billing/usage")
    print("      Full billing history (all products, daily granularity)")
    print(f"    - /users/{username}/settings/billing/premium_request/usage")
    print("      Premium request usage by model (Claude Sonnet 4.6, GPT-5.4, etc.)")
    print()
    print("  Rate limits tracked:")
    print("    - Core API:       5000/hour (authenticated)")
    print("    - GraphQL API:    5000/hour (authenticated)")
    print("    - Search API:     30/minute (full text search)")
    print("    - Code Scanning:  5000/hour")
    print("    - Actions Runner: 10000/hour (registration)")
    print("    - SCIM:           15000/hour (enterprise)")
    print("    - Audit Log:      1750/hour")
    print("    - Dependency:     100/hour (snapshots + SBOM)")
    print()


def show_what_else(api, username):
    """Show info about other available data points."""
    del api  # static section; kept for backward-compatible signature
    render_what_else(username)
