import unittest


class FakeAPI:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def request(self, method, path, params=None):
        self.requests.append((method, path, params or {}))
        return self.responses.get((method, path, tuple(sorted((params or {}).items()))))

    def get_all_pages(self, path, params=None):
        self.requests.append(("PAGES", path, params or {}))
        return self.responses.get(("PAGES", path), [])


class BillingTests(unittest.TestCase):
    def test_get_billing_summary_aggregates_items_by_sku(self):
        from github_usage.billing import get_billing_summary

        api = FakeAPI(
            {
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
            {
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
            {
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
            {
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
