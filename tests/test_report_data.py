import unittest
from unittest import mock

from tests._fakes import FakeAPI


class ReportDataTests(unittest.TestCase):
    def test_build_report_data_captures_partial_endpoint_failure(self):
        from github_usage.report_data import build_report_data

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): RuntimeError("copilot unavailable"),
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 4900}}
                },
            }
        )

        report = build_report_data(
            api,
            "octocat",
            include_actions=True,
            include_copilot=True,
            include_lfs=True,
            include_consumers=False,
            include_artifact_storage=False,
            include_release_assets=False,
            max_repos=100,
            warn_over=None,
        )

        self.assertEqual(report["username"], "octocat")
        self.assertIn("copilot", report["errors"])
        self.assertIsNone(report["copilot"])
        self.assertIsNotNone(report["monthly_costs"])

    def test_estimate_api_request_count_respects_max_repos_and_options(self):
        from github_usage.report_data import estimate_api_request_count

        estimate = estimate_api_request_count(
            repo_count=250,
            include_consumers=True,
            include_artifact_storage=True,
            include_release_assets=True,
            max_repos=25,
            core_limit=5000,
            core_remaining=100,
        )

        self.assertEqual(estimate["repos_considered"], 25)
        self.assertEqual(estimate["estimated_incremental_requests"], 85)
        self.assertEqual(estimate["estimated_percent_of_remaining"], 85.0)

    def test_get_warning_state_handles_missing_monthly_costs(self):
        from github_usage.report_data import get_warning_state

        report_data = {"monthly_costs": None, "actions": {"minutes_percent": 50}}

        # Should not crash on net cost threshold check
        warnings = get_warning_state(report_data, "100")
        self.assertEqual(warnings, [])

    def test_get_warning_state_handles_missing_actions_for_percent_threshold(self):
        from github_usage.report_data import get_warning_state

        report_data = {"actions": None}

        # Should return a warning message instead of raising ValueError
        warnings = get_warning_state(report_data, "80%")
        self.assertIn("Percentage warning threshold skipped", warnings[0])

    def test_single_warning_state_invalid_dollar_value(self):
        from github_usage.report_data import _single_warning_state

        with self.assertRaisesRegex(ValueError, "invalid --warn-over"):
            _single_warning_state({}, "abc")

    def test_single_warning_state_invalid_percent_value(self):
        from github_usage.report_data import _single_warning_state

        # "abc%" must raise even with no actions data, because the
        # try/except float() runs BEFORE the `if not actions` guard.
        with self.assertRaisesRegex(ValueError, "invalid --warn-over"):
            _single_warning_state({}, "abc%")

    def test_get_key_insights_reports_top_repo_share_when_consumers_present(self):
        from github_usage.report_data import get_key_insights

        report = {
            "actions": {"minutes": 100.0, "storage_percent": 100.0},
            "repo_consumers": {
                "by_minutes": [
                    {"repo": "octocat/heavy", "minutes": 60.0},
                    {"repo": "octocat/light", "minutes": 10.0},
                ]
            },
        }

        insights = get_key_insights(report)

        self.assertEqual(len(insights), 1)
        self.assertIn("octocat/heavy", insights[0])
        self.assertIn("60%", insights[0])

    def test_get_key_insights_annotates_private_visibility(self):
        from github_usage.report_data import get_key_insights

        report = {
            "actions": {"minutes": 100.0, "storage_percent": 100.0},
            "repo_consumers": {
                "by_minutes": [
                    {"repo": "octocat/heavy", "minutes": 60.0, "visibility": "private"},
                ]
            },
        }
        insights = get_key_insights(report)
        self.assertIn("[private]", insights[0])

    def test_get_key_insights_omits_share_when_actions_is_none(self):
        from github_usage.report_data import get_key_insights

        report = {
            "actions": None,
            "repo_consumers": {"by_minutes": [{"repo": "octocat/heavy", "minutes": 60.0}]},
        }

        insights = get_key_insights(report)

        self.assertEqual(insights, [])

    def test_get_key_insights_reports_storage_below_free_tier(self):
        from github_usage.report_data import get_key_insights

        report = {
            "actions": {"minutes": 100.0, "storage_percent": 50.0},
            "repo_consumers": {"by_minutes": []},
        }

        insights = get_key_insights(report)

        self.assertEqual(insights, ["Actions storage is below the free-tier limit."])

    def test_get_key_insights_handles_none_by_minutes_without_index_error(self):
        from github_usage.report_data import get_key_insights

        report = {
            "actions": {"minutes": 100.0, "storage_percent": 50.0},
            "repo_consumers": {"by_minutes": None},
        }

        insights = get_key_insights(report)

        self.assertEqual(insights, ["Actions storage is below the free-tier limit."])

    def test_get_key_insights_caps_at_three(self):
        from github_usage.report_data import get_key_insights

        # Build a long by_minutes list so the share insight is the only
        # candidate; verify length is bounded.
        report = {
            "actions": {"minutes": 100.0, "storage_percent": 50.0},
            "repo_consumers": {
                "by_minutes": [{"repo": f"r{i}", "minutes": 1.0} for i in range(10)]
            },
        }

        insights = get_key_insights(report)

        self.assertLessEqual(len(insights), 3)

    def test_get_actions_usage_handles_null_amounts(self):
        """Source sanitization: report_data._billing_summary and get_actions_usage loop
        both encounter null amount fields; totals stay 0.0; stored items have 0.0."""
        from github_usage.report_data import get_actions_usage

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {
                    "usageItems": [
                        {
                            "sku": "linux",
                            "unitType": "minutes",
                            "grossAmount": None,
                            "discountAmount": None,
                            "netAmount": None,
                            "grossQuantity": None,
                        }
                    ]
                }
            }
        )

        result = get_actions_usage(api, "octocat")

        self.assertEqual(result["minutes"], 0.0)
        self.assertEqual(result["storage_gb_hours"], 0.0)
        # Sanitized SKU has 0.0 in the null fields
        self.assertEqual(result["sku_breakdown"]["linux"]["grossAmount"], 0.0)
        self.assertEqual(result["sku_breakdown"]["linux"]["grossQuantity"], 0.0)

    def test_get_copilot_usage_handles_null_amounts(self):
        """Source sanitization: both _billing_summary and inline premium loop handle nulls."""
        from github_usage.report_data import get_copilot_usage

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {
                    "usageItems": [
                        {
                            "sku": "copilot",
                            "grossAmount": None,
                            "discountAmount": None,
                            "netAmount": None,
                        }
                    ]
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {
                    "usageItems": [
                        {
                            "model": "gpt-4.1",
                            "grossQuantity": None,
                            "grossAmount": None,
                            "discountAmount": None,
                            "netAmount": None,
                        }
                    ]
                },
            }
        )

        result = get_copilot_usage(api, "octocat")

        # No crash; per-model totals are 0.0
        self.assertEqual(result["by_model"]["gpt-4.1"]["requests"], 0.0)
        self.assertEqual(result["by_model"]["gpt-4.1"]["gross"], 0.0)

    def test_get_copilot_usage_handles_non_dict_premium(self):
        """Regression: /premium_request/usage returns a list; get_copilot_usage does not raise."""
        from github_usage.report_data import get_copilot_usage

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): [1, 2, 3],  # list instead of dict
            }
        )

        result = get_copilot_usage(api, "octocat")

        # No crash; by_model is empty
        self.assertEqual(result["by_model"], {})

    def test_rate_limit_handles_non_dict_response(self):
        """Regression: /rate_limit returns a list; _rate_limit returns (None, None)."""
        from github_usage.report_data import _rate_limit

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): [1, 2, 3],  # list instead of dict
            }
        )

        self.assertEqual(_rate_limit(api), (None, None))

    def test_consumers_enabled_reuses_rows_for_visibility_split(self):
        from github_usage.report_data import build_report_data

        repos = [
            {
                "full_name": "octocat/private-repo",
                "owner": {"login": "octocat"},
                "name": "private-repo",
                "visibility": "private",
            },
            {
                "full_name": "octocat/public-repo",
                "owner": {"login": "octocat"},
                "name": "public-repo",
                "visibility": "public",
            },
        ]
        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {
                    "usageItems": [
                        {
                            "sku": "actions_linux",
                            "unitType": "minutes",
                            "grossQuantity": 1500.0,
                            "grossAmount": 0.0,
                            "discountAmount": 0.0,
                            "netAmount": 0.0,
                        }
                    ],
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 4900}}
                },
            },
            pages_responses={"/user/repos": repos},
        )
        with (
            mock.patch(
                "github_usage.report_optional.get_actions_per_repo",
                side_effect=[
                    (1000.0, 0.0, {"sku": {"grossAmount": 0.0}}),
                    (500.0, 0.0, {"sku": {"grossAmount": 0.0}}),
                ],
            ),
            mock.patch(
                "github_usage.report_data.fetch_repo_actions_table",
            ) as mock_fetch,
        ):
            report = build_report_data(
                api,
                "octocat",
                include_actions=True,
                include_copilot=False,
                include_lfs=False,
                include_consumers=True,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
            )
        actions = report["actions"]
        self.assertEqual(actions["private_minutes"], 1000.0)
        self.assertEqual(actions["public_minutes"], 500.0)
        mock_fetch.assert_not_called()

    def test_actions_only_uses_fetch_repo_actions_table(self):
        from github_usage.report_data import build_report_data

        repos = [
            {
                "full_name": "octocat/private-repo",
                "owner": {"login": "octocat"},
                "name": "private-repo",
                "visibility": "private",
            },
            {
                "full_name": "octocat/public-repo",
                "owner": {"login": "octocat"},
                "name": "public-repo",
                "visibility": "public",
            },
        ]
        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {
                    "usageItems": [
                        {
                            "sku": "actions_linux",
                            "unitType": "minutes",
                            "grossQuantity": 1500.0,
                            "grossAmount": 0.0,
                            "discountAmount": 0.0,
                            "netAmount": 0.0,
                        }
                    ],
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 4900}}
                },
            },
            pages_responses={"/user/repos": repos},
        )
        fake_rows = [
            {
                "repo": "octocat/private-repo",
                "minutes": 1000.0,
                "storage_gb_hours": 0.0,
                "avg_mb": 0.0,
                "gross": 0.0,
                "sku": {},
                "visibility": "private",
            },
            {
                "repo": "octocat/public-repo",
                "minutes": 500.0,
                "storage_gb_hours": 0.0,
                "avg_mb": 0.0,
                "gross": 0.0,
                "sku": {},
                "visibility": "public",
            },
        ]
        with mock.patch(
            "github_usage.report_data.fetch_repo_actions_table",
            return_value=(fake_rows, {}),
        ) as mock_fetch:
            report = build_report_data(
                api,
                "octocat",
                include_actions=True,
                include_copilot=False,
                include_lfs=False,
                include_consumers=False,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
            )
        actions = report["actions"]
        self.assertEqual(actions["private_minutes"], 1000.0)
        self.assertEqual(actions["public_minutes"], 500.0)
        mock_fetch.assert_called_once_with(api, repos)

    def test_actions_disabled_skips_per_repo_fetch(self):
        from github_usage.report_data import build_report_data

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 4900}}
                },
            },
        )
        with mock.patch(
            "github_usage.report_data.fetch_repo_actions_table",
        ) as mock_fetch:
            report = build_report_data(
                api,
                "octocat",
                include_actions=False,
                include_copilot=False,
                include_lfs=False,
                include_consumers=False,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
            )
        self.assertIsNone(report["actions"])
        mock_fetch.assert_not_called()

    def test_consumers_error_falls_back_to_fetch_repo_actions_table(self):
        from github_usage.report_data import build_report_data

        repos = [
            {
                "full_name": "octocat/private-repo",
                "owner": {"login": "octocat"},
                "name": "private-repo",
                "visibility": "private",
            },
            {
                "full_name": "octocat/public-repo",
                "owner": {"login": "octocat"},
                "name": "public-repo",
                "visibility": "public",
            },
        ]
        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {
                    "usageItems": [
                        {
                            "sku": "actions_linux",
                            "unitType": "minutes",
                            "grossQuantity": 1500.0,
                            "grossAmount": 0.0,
                            "discountAmount": 0.0,
                            "netAmount": 0.0,
                        }
                    ],
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 4900}}
                },
            },
            pages_responses={"/user/repos": repos},
        )
        fake_rows = [
            {
                "repo": "octocat/private-repo",
                "minutes": 1000.0,
                "storage_gb_hours": 0.0,
                "avg_mb": 0.0,
                "gross": 0.0,
                "sku": {},
                "visibility": "private",
            },
            {
                "repo": "octocat/public-repo",
                "minutes": 500.0,
                "storage_gb_hours": 0.0,
                "avg_mb": 0.0,
                "gross": 0.0,
                "sku": {},
                "visibility": "public",
            },
        ]
        with (
            mock.patch(
                "github_usage.report_data.get_repo_consumers",
                side_effect=RuntimeError("consumers API failure"),
            ),
            mock.patch(
                "github_usage.report_data.fetch_repo_actions_table",
                return_value=(fake_rows, {}),
            ) as mock_fetch,
        ):
            report = build_report_data(
                api,
                "octocat",
                include_actions=True,
                include_copilot=False,
                include_lfs=False,
                include_consumers=True,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
            )
        actions = report["actions"]
        self.assertEqual(actions["private_minutes"], 1000.0)
        self.assertEqual(actions["public_minutes"], 500.0)
        mock_fetch.assert_called_once_with(api, repos)

    def test_only_public_passes_through_to_visibility_split(self):
        from github_usage.report_data import build_report_data

        repos = [
            {
                "full_name": "octocat/public-repo",
                "owner": {"login": "octocat"},
                "name": "public-repo",
                "visibility": "public",
            },
        ]
        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {
                    "usageItems": [
                        {
                            "sku": "actions_linux",
                            "unitType": "minutes",
                            "grossQuantity": 500.0,
                            "grossAmount": 0.0,
                            "discountAmount": 0.0,
                            "netAmount": 0.0,
                        }
                    ],
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "git_lfs"),),
                ): {"usageItems": []},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 4900}}
                },
            },
            pages_responses={"/user/repos": repos},
        )
        fake_rows = [
            {
                "repo": "octocat/public-repo",
                "minutes": 500.0,
                "storage_gb_hours": 0.0,
                "avg_mb": 0.0,
                "gross": 0.0,
                "sku": {},
                "visibility": "public",
            },
        ]
        with mock.patch(
            "github_usage.report_data.fetch_repo_actions_table",
            return_value=(fake_rows, {}),
        ):
            report = build_report_data(
                api,
                "octocat",
                include_actions=True,
                include_copilot=False,
                include_lfs=False,
                include_consumers=False,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
                only_public=True,
            )
        self.assertTrue(report["actions"]["filtered"])
        self.assertEqual(report["actions"]["public_minutes"], 500.0)
        self.assertEqual(report["actions"]["private_minutes"], 0.0)
