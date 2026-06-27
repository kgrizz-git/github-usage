import unittest

from tests._fakes import FakeAPI


class BillingTests(unittest.TestCase):
    def test_get_billing_summary_aggregates_items_by_sku(self):
        from github_usage.billing import get_billing_summary

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
                            "grossAmount": 2.0,
                            "discountAmount": 0.5,
                            "netAmount": 1.5,
                        },
                        {
                            "sku": "storage",
                            "grossAmount": 1.0,
                            "discountAmount": 0.0,
                            "netAmount": 1.0,
                        },
                    ]
                }
            }
        )

        result = get_billing_summary(api, "octocat", "Actions")

        self.assertEqual(result["total_gross"], 3.0)
        self.assertEqual(result["total_discount"], 0.5)
        self.assertEqual(result["total_net"], 2.5)
        self.assertIn("linux", result["items"])

    def test_get_premium_request_usage_groups_by_model(self):
        from github_usage.billing import get_premium_request_usage

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {
                    "usageItems": [
                        {
                            "model": "gpt-4.1",
                            "grossQuantity": 2,
                            "grossAmount": 0.08,
                            "discountAmount": 0.02,
                            "netAmount": 0.06,
                        }
                    ]
                }
            }
        )

        result = get_premium_request_usage(api, "octocat")

        self.assertEqual(result["gpt-4.1"]["total_requests"], 2)
        self.assertEqual(result["gpt-4.1"]["total_net"], 0.06)

    def test_get_user_actions_billing_splits_minutes_and_storage(self):
        from github_usage.billing import get_user_actions_billing

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): {
                    "usageItems": [
                        {"sku": "linux", "unitType": "minutes", "grossQuantity": 10},
                        {
                            "sku": "storage",
                            "unitType": "gigabyte-hours",
                            "grossQuantity": 4,
                        },
                    ]
                }
            }
        )

        minutes, storage, sku = get_user_actions_billing(api, "octocat")

        self.assertEqual(minutes, 10)
        self.assertEqual(storage, 4)
        self.assertEqual(set(sku), {"linux", "storage"})

    def test_get_actions_per_repo_passes_repository_parameter(self):
        from github_usage.billing import get_actions_per_repo

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/api")),
                ): {"usageItems": [{"sku": "linux", "unitType": "minutes", "grossQuantity": 7}]}
            }
        )

        minutes, storage, sku = get_actions_per_repo(api, "octocat", "api")

        self.assertEqual(minutes, 7)
        self.assertEqual(storage, 0)
        self.assertIn("linux", sku)

    def test_get_actions_from_runs_accumulates_per_run_minutes(self):
        from github_usage.billing import get_actions_from_runs

        api = FakeAPI(
            pages_responses={
                "/repos/octocat/api/actions/runs": [
                    {
                        "workflow_name": "CI",
                        "billable": {"UBUNTU": {"millis": 60000}},  # 1 min
                    },
                    {
                        "workflow_name": "CI",
                        "billable": {"UBUNTU": {"millis": 120000}},  # 2 mins
                    },
                ]
            }
        )

        total_min, os_min, wf_min = get_actions_from_runs(api, "octocat", "api")

        # Total should be 1 + 2 = 3
        self.assertEqual(total_min, 3.0)
        # CI workflow should have 1 + 2 = 3
        self.assertEqual(wf_min["CI"], 3.0)

    def test_get_actions_from_runs_sends_correct_dates(self):
        """Pin the date to 2026-06-15 and assert the created filter spans the full month."""
        from datetime import date
        from unittest import mock

        from github_usage import billing

        with mock.patch.object(billing, "date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 15)
            api = FakeAPI(pages_responses={"/repos/octocat/api/actions/runs": []})
            total_min, os_min, wf_min = billing.get_actions_from_runs(api, "octocat", "api")

        # First request recorded should be the runs endpoint with the correct created range
        self.assertEqual(
            api.requests[0],
            (
                "PAGES",
                "/repos/octocat/api/actions/runs",
                {"created": "2026-06-01..2026-06-30", "per_page": 100},
            ),
        )
        # Default values
        self.assertEqual(total_min, 0.0)
        self.assertEqual(os_min, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0})
        self.assertEqual(wf_min, {})

    def test_get_actions_from_runs_handles_missing_fields(self):
        """Runs lacking billable, billable keys mapped to None, or missing workflow_name."""
        from github_usage.billing import get_actions_from_runs

        api = FakeAPI(
            pages_responses={
                "/repos/octocat/api/actions/runs": [
                    {"billable": {"UBUNTU": None}},  # None inner dict
                    {},  # no billable, no workflow_name
                    {"billable": {"WINDOWS": {"millis": 60000}}, "workflow_name": "win"},
                ]
            }
        )

        # Should not raise
        total_min, os_min, wf_min = get_actions_from_runs(api, "octocat", "api")

        # 1 min from the windows run
        self.assertEqual(total_min, 1.0)
        self.assertEqual(wf_min.get("win"), 1.0)
        # "Unknown" workflow for runs without workflow_name
        self.assertEqual(wf_min.get("Unknown"), 0.0)

    def test_get_actions_from_runs_empty(self):
        from github_usage.billing import get_actions_from_runs

        api = FakeAPI(pages_responses={"/repos/octocat/api/actions/runs": []})

        result = get_actions_from_runs(api, "octocat", "api")

        self.assertEqual(result, (0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {}))

    def test_get_actions_from_runs_handles_none_response(self):
        """Regression: api.get_all_pages returns None (not [])."""
        from github_usage.billing import get_actions_from_runs

        # FakeAPI with pages_responses containing None
        api = FakeAPI()
        # Override get_all_pages to return None

        def none_pages(path, params=None):
            return None

        api.get_all_pages = none_pages

        # Should not raise; returns defaults
        result = get_actions_from_runs(api, "octocat", "api")

        self.assertEqual(result, (0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {}))

    def test_get_actions_from_runs_os_millis(self):
        """Multi-OS and per-OS totals."""
        from github_usage.billing import get_actions_from_runs

        api = FakeAPI(
            pages_responses={
                "/repos/octocat/api/actions/runs": [
                    {
                        "workflow_name": "CI",
                        "billable": {
                            "UBUNTU": {"millis": 60000},  # 1 min
                            "WINDOWS": {"millis": 120000},  # 2 min
                            "MACOS": {"millis": 180000},  # 3 min
                        },
                    },
                ]
            }
        )

        total_min, os_min, wf_min = get_actions_from_runs(api, "octocat", "api")

        self.assertEqual(total_min, 6.0)
        self.assertEqual(os_min, {"UBUNTU": 60000, "WINDOWS": 120000, "MACOS": 180000})
        self.assertEqual(wf_min["CI"], 6.0)

    def test_get_full_billing_success(self):
        from github_usage.billing import get_full_billing

        api = FakeAPI(
            request_responses={
                ("GET", "/users/octocat/settings/billing/usage", ()): {
                    "usageItems": [{"product": "Actions", "sku": "linux", "grossAmount": 1.0}]
                }
            }
        )

        result = get_full_billing(api, "octocat")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sku"], "linux")

    def test_get_full_billing_failure(self):
        from github_usage.billing import get_full_billing

        api = FakeAPI(
            request_responses={
                ("GET", "/users/octocat/settings/billing/usage", ()): RuntimeError("boom")
            }
        )

        self.assertIsNone(get_full_billing(api, "octocat"))

    def test_get_full_billing_nondict(self):
        from github_usage.billing import get_full_billing

        api = FakeAPI(
            request_responses={("GET", "/users/octocat/settings/billing/usage", ()): [1, 2, 3]}
        )

        self.assertIsNone(get_full_billing(api, "octocat"))

    def test_get_billing_summary_nondict(self):
        from github_usage.billing import get_billing_summary

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"),),
                ): "junk"
            }
        )

        self.assertIsNone(get_billing_summary(api, "octocat", "Actions"))

    def test_get_billing_summary_handles_null_amounts(self):
        """Source sanitization: items with null amounts are stored with 0.0 and totals are safe."""
        from github_usage.billing import get_billing_summary

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
                            "grossAmount": None,
                            "discountAmount": None,
                            "netAmount": None,
                        }
                    ]
                }
            }
        )

        result = get_billing_summary(api, "octocat", "Actions")

        self.assertEqual(result["total_gross"], 0.0)
        self.assertEqual(result["total_discount"], 0.0)
        self.assertEqual(result["total_net"], 0.0)
        # Sanitized item stored
        self.assertEqual(result["items"]["linux"]["grossAmount"], 0.0)
        self.assertEqual(result["items"]["linux"]["netAmount"], 0.0)

    def test_get_premium_request_usage_nondict(self):
        from github_usage.billing import get_premium_request_usage

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): [1, 2]
            }
        )

        self.assertIsNone(get_premium_request_usage(api, "octocat"))

    def test_get_premium_request_usage_handles_null_amounts(self):
        """Source sanitization: items with null amounts are stored with 0.0."""
        from github_usage.billing import get_premium_request_usage

        api = FakeAPI(
            request_responses={
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
                }
            }
        )

        result = get_premium_request_usage(api, "octocat")

        self.assertEqual(result["gpt-4.1"]["total_requests"], 0.0)
        self.assertEqual(result["gpt-4.1"]["total_gross"], 0.0)
        self.assertIn("gpt-4.1", result)
        # Item list is preserved (with sanitized entries)
        self.assertEqual(len(result["gpt-4.1"]["items"]), 1)
        self.assertEqual(result["gpt-4.1"]["items"][0]["grossAmount"], 0.0)

    def test_get_actions_per_repo_nondict(self):
        from github_usage.billing import get_actions_per_repo

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/api")),
                ): "junk"
            }
        )

        self.assertEqual(get_actions_per_repo(api, "octocat", "api"), (0.0, 0.0, {}))

    def test_get_actions_per_repo_handles_null_quantity(self):
        """Source sanitization: items with null grossQuantity are stored with 0.0."""
        from github_usage.billing import get_actions_per_repo

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/api")),
                ): {
                    "usageItems": [
                        {
                            "sku": "linux",
                            "unitType": "minutes",
                            "grossQuantity": None,
                        }
                    ]
                }
            }
        )

        minutes, storage, sku = get_actions_per_repo(api, "octocat", "api")

        # Total minutes stays 0.0 (no crash on None + float)
        self.assertEqual(minutes, 0.0)
        self.assertEqual(storage, 0.0)
        # Sanitized SKU stored
        self.assertEqual(sku["linux"]["grossQuantity"], 0.0)

    def test_get_actions_per_repo_error_propagation(self):
        from github_usage.billing import BillingFetchError, get_actions_per_repo

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/api")),
                ): RuntimeError("API error 403")
            }
        )

        with self.assertRaises(BillingFetchError):
            get_actions_per_repo(api, "octocat", "api")

    def test_get_actions_per_repo_empty_response(self):
        from github_usage.billing import get_actions_per_repo

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/usage/summary",
                    (("product", "Actions"), ("repository", "octocat/api")),
                ): None
            }
        )

        self.assertEqual(get_actions_per_repo(api, "octocat", "api"), (0.0, 0.0, {}))
