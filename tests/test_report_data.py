import unittest


class FakeAPI:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def request(self, method, path, params=None):
        self.requests.append((method, path, params or {}))
        key = (method, path, tuple(sorted((params or {}).items())))
        value = self.responses.get(key)
        if isinstance(value, Exception):
            raise value
        return value

    def get_all_pages(self, path, params=None):
        self.requests.append(("PAGES", path, params or {}))
        return self.responses.get(("PAGES", path), [])


class ReportDataTests(unittest.TestCase):
    def test_build_report_data_captures_partial_endpoint_failure(self):
        from github_usage.report_data import build_report_data

        api = FakeAPI(
            {
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
        self.assertEqual(estimate["estimated_incremental_requests"], 75)
        self.assertEqual(estimate["estimated_percent_of_remaining"], 75.0)
