"""Orchestration for the legacy interactive report."""

from __future__ import annotations

import sys

from .api import GitHubAPI
from .auth import check_user_scope, resolve_token
from .billing import get_billing_summary, get_user_actions_billing
from .report_account import show_account_info, show_rate_limits, show_what_else
from .report_actions import (
    show_actions_os_breakdown,
    show_actions_per_repo,
    show_actions_summary,
    show_actions_top_consumers,
    show_limits_summary,
)
from .report_products import (
    show_base_costs,
    show_copilot_summary,
    show_full_billing_history,
    show_gitlfs_summary,
    show_monthly_costs,
)
from .report_summary import show_final_summary
from .storage import get_storage_analysis
from .terminal import print_header


def main():
    token = resolve_token()
    if not token:
        from .auth import print_missing_token_error

        print_missing_token_error()
        sys.exit(1)

    try:
        api = GitHubAPI(token)

        # Check for 'user' scope required for billing endpoints
        if not check_user_scope(api):
            print("Error: Your GitHub token is missing the 'user' scope.")
            print()
            print("  The billing endpoints require the 'user' scope.")
            print("  Fix: run 'gh auth refresh -h github.com -s user'")
            print()
            print("  Current token scopes:", end=" ")
            import http.client

            conn = http.client.HTTPSConnection("api.github.com")
            try:
                conn.request(
                    "GET", "/user", headers={**api.headers, "Authorization": f"token {token}"}
                )
                resp = conn.getresponse()
                scopes = resp.getheader("X-OAuth-Scopes", "none")
                print(scopes if scopes else "none")
                resp.read()
            finally:
                conn.close()
            sys.exit(1)

        # Account & rate limits
        print_header()
        username, user_type = show_account_info(api)
        show_rate_limits(api)

        # Actions
        user_minutes, user_storage_gb, actions_sku = get_user_actions_billing(api, username)
        actions_gross_total = sum(i.get("grossAmount", 0) for i in (actions_sku or {}).values())
        actions_discount_total = sum(
            i.get("discountAmount", 0) for i in (actions_sku or {}).values()
        )
        actions_net_total = sum(i.get("netAmount", 0) for i in (actions_sku or {}).values())
        if user_minutes is not None:
            show_actions_summary(api, username, user_minutes, user_storage_gb, actions_sku)

        # Repos
        repos = api.get_all_pages("/user/repos", {"type": "all"})
        repo_data = show_actions_per_repo(api, repos)
        show_actions_top_consumers(repo_data)
        show_actions_os_breakdown(api, repos)

        # Copilot
        show_copilot_summary(api, username)

        # Git LFS
        show_gitlfs_summary(api, username)

        # Cost estimate
        show_monthly_costs(repo_data, username, api)

        # Full billing history
        show_full_billing_history(api, username)

        # Limits
        show_limits_summary(username, user_minutes or 0, user_storage_gb or 0)

        # Base costs (v3 addition — standalone section)
        copilot_summary = get_billing_summary(api, username, "Copilot")
        lfs_summary = get_billing_summary(api, username, "git_lfs")
        if repos:
            show_base_costs(api, username, actions_sku, copilot_summary, lfs_summary)

        # Final summary (v3 addition)
        storage_analysis = get_storage_analysis(api, repos) if repos else {"repos": []}
        show_final_summary(
            username,
            user_minutes,
            user_storage_gb,
            actions_gross_total,
            actions_discount_total,
            actions_net_total,
            repo_data,
            copilot_summary,
            lfs_summary,
            storage_analysis,
            api,
        )

        # What else is available
        show_what_else(api, username)

        print("=" * 70)
        print("  End of Report v3")
        print("=" * 70)

    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
