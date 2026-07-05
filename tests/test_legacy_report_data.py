"""Tests for legacy single-fetch data collection."""

from __future__ import annotations

import unittest

from github_usage.billing import BillingFetchError
from github_usage.legacy_report_data import (
    build_legacy_report_data,
    derive_artifact_storage,
    derive_repo_consumers,
    estimate_legacy_api_request_count,
)
from tests._fakes import FakeAPI


def _repo(name: str) -> dict:
    return {"name": name, "owner": {"login": "octocat"}, "full_name": f"octocat/{name}"}


class LegacyReportDataTests(unittest.TestCase):
    def test_derive_repo_consumers_from_repo_actions(self) -> None:
        rows = [
            {"repo": "octocat/a", "minutes": 10.0, "gross": 1.0, "avg_mb": 1.0},
            {"repo": "octocat/b", "minutes": 50.0, "gross": 2.0, "avg_mb": 2.0},
        ]
        consumers = derive_repo_consumers(
            rows,
            {},
            max_repos=100,
            truncated=False,
            scanned_repo_count=2,
        )
        self.assertEqual(consumers["by_minutes"][0]["repo"], "octocat/b")
        self.assertEqual(consumers["by_cost"][0]["repo"], "octocat/b")

    def test_derive_artifact_storage_from_storage_analysis(self) -> None:
        storage = {
            "repos": [
                {
                    "name": "octocat/a",
                    "items": [
                        {"type": "Artifact", "storage": 1.0},
                        {"type": "Release Asset", "storage": 0.5},
                    ],
                }
            ]
        }
        derived = derive_artifact_storage(
            storage, max_repos=100, truncated=False, scanned_repo_count=1
        )
        self.assertEqual(len(derived["top_repos"]), 1)
        self.assertEqual(derived["top_repos"][0]["repo"], "octocat/a")
        self.assertGreater(derived["top_repos"][0]["artifact_bytes"], 0)

    def test_estimate_legacy_counts_storage_once_per_repo(self) -> None:
        estimate = estimate_legacy_api_request_count(
            100,
            max_repos=100,
            include_release_assets=False,
            core_limit=5000,
            core_remaining=5000,
        )
        self.assertEqual(estimate["repos_considered"], 100)
        self.assertGreater(estimate["estimated_incremental_requests"], 100)

    def test_build_legacy_report_data_keys(self) -> None:
        repos = [_repo("a"), _repo("b")]
        api = FakeAPI(
            request_responses={
                ("GET", "/user", ()): {"login": "octocat", "type": "User", "plan": {}},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 5000}}
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                ("GET", "/users/octocat/settings/billing/usage", ()): {"usageItems": []},
            },
            pages_responses={
                "/user/repos": repos,
            },
        )
        account = {"login": "octocat", "type": "User", "plan": {}}
        rate_limits = {"resources": {"core": {"limit": 5000, "remaining": 5000}}}
        data = build_legacy_report_data(
            api,
            "octocat",
            max_repos=100,
            account=account,
            rate_limits=rate_limits,
        )
        for key in (
            "account",
            "rate_limits",
            "repo_actions",
            "repo_consumers",
            "artifact_storage",
            "storage_analysis",
            "actions_os_breakdown",
            "billing_history",
            "actions",
        ):
            self.assertIn(key, data)

    def test_per_repo_billing_error_does_not_abort(self) -> None:
        repos = [_repo("ok"), _repo("bad")]

        def _request(method, path, params=None):
            api.requests.append((method, path, params or {}))
            if path.endswith("/settings/billing/usage/summary") and params:
                repo = params.get("repository", "")
                if repo.endswith("/bad"):
                    raise BillingFetchError("octocat/bad: denied")
            if (method, path) == ("GET", "/user"):
                return {"login": "octocat", "type": "User", "plan": {}}
            if (method, path) == ("GET", "/rate_limit"):
                return {"resources": {"core": {"limit": 5000, "remaining": 5000}}}
            if path.endswith("/settings/billing/usage"):
                return {"usageItems": []}
            if "premium_request" in path:
                return {"usageItems": []}
            if "usage/summary" in path:
                return {"usageItems": []}
            return None

        api = FakeAPI()
        api.request = _request  # type: ignore[method-assign]
        api.get_all_pages = lambda path, params=None, limit=None: (
            repos if path == "/user/repos" else []
        )  # type: ignore[method-assign]
        data = build_legacy_report_data(
            api,
            "octocat",
            max_repos=100,
            account={"login": "octocat", "type": "User", "plan": {}},
            rate_limits={"resources": {"core": {"limit": 5000, "remaining": 5000}}},
        )
        self.assertIn("bad", str(data["repo_consumers"]["errors"]))

    def test_artifact_endpoint_not_doubled(self) -> None:
        repos = [_repo("only")]
        artifact_calls: list[str] = []

        def _pages(path, params=None, limit=None):
            del params, limit
            if "/actions/artifacts" in path:
                artifact_calls.append(path)
            if path == "/user/repos":
                return repos
            return []

        api = FakeAPI(
            request_responses={
                ("GET", "/user", ()): {"login": "octocat", "type": "User", "plan": {}},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 5000}}
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (
                        ("product", "Actions"),
                        ("repository", "octocat/only"),
                    ),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                ("GET", "/users/octocat/settings/billing/usage", ()): {"usageItems": []},
            },
        )
        api.get_all_pages = _pages  # type: ignore[method-assign]
        build_legacy_report_data(
            api,
            "octocat",
            max_repos=100,
            account={"login": "octocat", "type": "User", "plan": {}},
            rate_limits={"resources": {"core": {"limit": 5000, "remaining": 5000}}},
        )
        self.assertEqual(len(artifact_calls), 1)
