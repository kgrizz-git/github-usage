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
            {
                "repo": "octocat/a",
                "minutes": 10.0,
                "gross": 1.0,
                "avg_mb": 1.0,
                "visibility": "private",
            },
            {
                "repo": "octocat/b",
                "minutes": 50.0,
                "gross": 2.0,
                "avg_mb": 2.0,
                "visibility": "public",
            },
        ]
        consumers = derive_repo_consumers(
            rows,
            {},
            max_repos=100,
            truncated=False,
            scanned_repo_count=2,
        )
        self.assertEqual(consumers["by_minutes"][0]["visibility"], "public")
        self.assertEqual(consumers["by_cost"][0]["visibility"], "public")

    def test_derive_repo_consumers_returns_private_and_storage_ranking_keys(self) -> None:
        rows = [
            {
                "repo": "octocat/private",
                "minutes": 40.0,
                "gross": 4.0,
                "avg_mb": 8.0,
                "visibility": "private",
            },
            {
                "repo": "octocat/public",
                "minutes": 100.0,
                "gross": 10.0,
                "avg_mb": 50.0,
                "visibility": "public",
            },
            {
                "repo": "octocat/internal",
                "minutes": 30.0,
                "gross": 3.0,
                "avg_mb": 6.0,
                "visibility": "internal",
            },
        ]
        consumers = derive_repo_consumers(
            rows,
            {},
            max_repos=100,
            truncated=False,
            scanned_repo_count=3,
        )
        for key in (
            "by_storage",
            "by_minutes_private",
            "by_storage_private",
        ):
            self.assertIn(key, consumers)
        private_repos = {row["repo"] for row in consumers["by_minutes_private"]}
        self.assertEqual(private_repos, {"octocat/private", "octocat/internal"})
        self.assertNotIn("octocat/public", private_repos)
        self.assertEqual(consumers["by_storage"][0]["repo"], "octocat/public")

    def test_derive_artifact_storage_from_storage_analysis(self) -> None:
        storage = {
            "repos": [
                {
                    "name": "octocat/a",
                    "visibility": "internal",
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
        self.assertEqual(derived["top_repos"][0]["visibility"], "internal")
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

    def test_build_legacy_report_data_attaches_visibility_split(self) -> None:
        """Phase 3b: attach_actions_visibility_split populates split keys on actions."""
        repos = [
            {**_repo("private1"), "visibility": "private"},
            {**_repo("public1"), "visibility": "public"},
        ]
        actions_summary = {
            "usageItems": [
                {
                    "sku": "actions_linux",
                    "unitType": "minutes",
                    "grossQuantity": 3000.0,
                    "grossAmount": 0.0,
                },
                {
                    "sku": "actions_artifact",
                    "unitType": "gigabyte-hours",
                    "grossQuantity": 100.0,
                    "grossAmount": 0.0,
                },
            ]
        }
        private_summary = {
            "usageItems": [
                {
                    "sku": "actions_linux",
                    "unitType": "minutes",
                    "grossQuantity": 1000.0,
                    "grossAmount": 0.0,
                },
                {
                    "sku": "actions_artifact",
                    "unitType": "gigabyte-hours",
                    "grossQuantity": 60.0,
                    "grossAmount": 0.0,
                },
            ]
        }
        public_summary = {
            "usageItems": [
                {
                    "sku": "actions_linux",
                    "unitType": "minutes",
                    "grossQuantity": 2000.0,
                    "grossAmount": 0.0,
                },
                {
                    "sku": "actions_artifact",
                    "unitType": "gigabyte-hours",
                    "grossQuantity": 40.0,
                    "grossAmount": 0.0,
                },
            ]
        }
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
                ): actions_summary,
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
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/private1")),
                ): private_summary,
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/public1")),
                ): public_summary,
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                ("GET", "/users/octocat/settings/billing/usage", ()): {"usageItems": []},
            },
            pages_responses={"/user/repos": repos},
        )
        data = build_legacy_report_data(
            api,
            "octocat",
            max_repos=100,
            account={"login": "octocat", "type": "User", "plan": {}},
            rate_limits={"resources": {"core": {"limit": 5000, "remaining": 5000}}},
        )
        actions = data["actions"]
        self.assertEqual(actions["minutes"], 3000.0)
        self.assertEqual(actions["private_minutes"], 1000.0)
        self.assertEqual(actions["public_minutes"], 2000.0)
        self.assertEqual(actions["unattributed_minutes"], 0.0)
        self.assertEqual(actions["private_minutes_percent"], 50.0)
        self.assertFalse(actions["filtered"])
        self.assertIn("storage_summary", data)
        self.assertEqual(
            data["storage_summary"]["private_gb_hours"], actions["private_storage_gb_hours"]
        )
        self.assertIn("sources", data)
        self.assertIn("actions_billing", data["sources"])

    def test_attach_actions_visibility_split_skips_when_actions_missing(self) -> None:
        """When the actions fetch errors, actions stays None and no split keys are added."""
        from unittest import mock

        repos = [_repo("a")]
        api = FakeAPI(
            request_responses={
                ("GET", "/user", ()): {"login": "octocat", "type": "User", "plan": {}},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 5000}}
                },
                # Per-repo billing summary succeeds with zero usage so repo_actions is non-empty
                # but the account-level actions fetch will be mocked to raise below.
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/a")),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                ("GET", "/users/octocat/settings/billing/usage", ()): {"usageItems": []},
            },
            pages_responses={"/user/repos": repos},
        )
        with (
            mock.patch(
                "github_usage.legacy_report_data.get_actions_usage",
                side_effect=RuntimeError("actions fetch failed"),
            ),
            mock.patch("github_usage.legacy_report_data.get_copilot_usage", return_value={}),
            mock.patch("github_usage.legacy_report_data.get_gitlfs_usage", return_value={}),
            mock.patch(
                "github_usage.legacy_report_data.get_monthly_costs",
                return_value={
                    "actions": ({"gross": 0.0, "discount": 0.0, "net": 0.0}),
                    "copilot": ({"gross": 0.0, "discount": 0.0, "net": 0.0}),
                    "git_lfs": ({"gross": 0.0, "discount": 0.0, "net": 0.0}),
                    "total": ({"gross": 0.0, "discount": 0.0, "net": 0.0}),
                },
            ),
            mock.patch(
                "github_usage.legacy_report_data.get_premium_request_usage",
                return_value={"usageItems": []},
            ),
            mock.patch(
                "github_usage.legacy_report_data.get_billing_summary",
                return_value={"usageItems": []},
            ),
        ):
            data = build_legacy_report_data(
                api,
                "octocat",
                max_repos=100,
                account={"login": "octocat", "type": "User", "plan": {}},
                rate_limits={"resources": {"core": {"limit": 5000, "remaining": 5000}}},
            )
        self.assertIsNone(data["actions"])
        self.assertIn("actions", data["errors"])

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


class LegacyApiUsageMergeTests(unittest.TestCase):
    def _account(self) -> dict:
        return {"login": "octocat", "type": "User", "plan": {}}

    def _rate_limits(self) -> dict:
        return {"resources": {"core": {"limit": 5000, "remaining": 5000}}}

    def test_legacy_merge_excludes_listing_but_includes_account_calls(self) -> None:
        from github_usage.report_api_usage import SCOPE_FULL_REPORT
        from tests._fakes import CountingFakeAPI

        repos = [_repo("r1"), _repo("r2")]
        api = CountingFakeAPI(pages_responses={"/user/repos": repos})
        report = build_legacy_report_data(
            api,
            "octocat",
            max_repos=10,
            account=self._account(),
            rate_limits=self._rate_limits(),
            baseline_stats={"actual_requests": 0, "actual_requests_by_resource": {}},
        )
        estimate = report["api_estimate"]
        # _limited_repos issues exactly one get_all_pages call, and the merge
        # carves out precisely the listing calls (so total - actual == 1 here).
        listing_calls = sum(1 for entry in api.request_log if entry["path"] == "/user/repos")
        self.assertEqual(listing_calls, 1)
        self.assertEqual(estimate["total_requests"] - estimate["actual_requests"], 1)
        self.assertEqual(
            sum(estimate["actual_requests_by_resource"].values()),
            estimate["actual_requests"],
        )
        self.assertEqual(estimate["estimate_scope"], SCOPE_FULL_REPORT)
        self.assertEqual(
            estimate["estimate_variance"],
            estimate["actual_requests"] - estimate["estimated_incremental_requests"],
        )
        self.assertFalse(estimate["from_cache"])

    def test_legacy_caller_baseline_excludes_pre_builder_calls(self) -> None:
        from github_usage.report_api_usage import SCOPE_FULL_REPORT, _api_request_stats
        from tests._fakes import CountingFakeAPI

        api = CountingFakeAPI(pages_responses={"/user/repos": [_repo("r1")]})
        api.request("GET", "/user")
        api.request("GET", "/rate_limit")
        baseline = _api_request_stats(api)
        report = build_legacy_report_data(
            api,
            "octocat",
            max_repos=10,
            account=self._account(),
            rate_limits=self._rate_limits(),
            baseline_stats=baseline,
        )
        estimate = report["api_estimate"]
        # The 2 pre-baseline calls plus the 1 listing call sit outside actual.
        self.assertEqual(estimate["total_requests"] - estimate["actual_requests"], 3)
        self.assertEqual(
            sum(estimate["actual_requests_by_resource"].values()),
            estimate["actual_requests"],
        )
        self.assertEqual(estimate["estimate_scope"], SCOPE_FULL_REPORT)

    def test_legacy_two_page_listing_does_not_move_variance(self) -> None:
        from tests._fakes import CountingFakeAPI

        def build_with_listing_pages(n: int) -> dict:
            api = CountingFakeAPI(
                pages_responses={"/user/repos": [_repo("r1")]},
                page_counts={"/user/repos": n},
            )
            report = build_legacy_report_data(
                api,
                "octocat",
                max_repos=10,
                account=self._account(),
                rate_limits=self._rate_limits(),
                baseline_stats={"actual_requests": 0, "actual_requests_by_resource": {}},
            )
            return report["api_estimate"]

        one_page = build_with_listing_pages(1)
        two_page = build_with_listing_pages(2)
        # The extra listing page lands in the total but is carved out of the
        # window, so the variance is identical.
        self.assertEqual(two_page["total_requests"] - one_page["total_requests"], 1)
        self.assertEqual(two_page["actual_requests"], one_page["actual_requests"])
        self.assertEqual(two_page["estimate_variance"], one_page["estimate_variance"])

    def test_legacy_builder_without_baseline_omits_scope(self) -> None:
        api = FakeAPI(pages_responses={"/user/repos": [_repo("r1")]})
        report = build_legacy_report_data(
            api,
            "octocat",
            max_repos=10,
            account=self._account(),
            rate_limits=self._rate_limits(),
        )
        estimate = report["api_estimate"]
        self.assertNotIn("estimate_scope", estimate)
        self.assertEqual(estimate["actual_requests"], 0)
        self.assertEqual(estimate["total_requests"], 0)
