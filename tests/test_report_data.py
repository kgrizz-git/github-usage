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
