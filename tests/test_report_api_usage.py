import unittest

from github_usage.report_api_usage import api_usage_lines, api_usage_rows


def _estimate(**overrides):
    base = {
        "actual_requests": 123,
        "total_requests": 130,
        "estimated_incremental_requests": 120,
        "estimate_variance": 3,
        "estimate_scope": "repo-sections-only",
        "core_limit": 5000,
        "core_remaining": 4877,
        "actual_requests_by_resource": {"billing": 20, "repos": 1, "actions": 100},
    }
    base.update(overrides)
    return base


class ApiUsageLinesTests(unittest.TestCase):
    def test_full_estimate_renders_all_lines(self):
        self.assertEqual(
            api_usage_lines(_estimate()),
            [
                "- Repo requests in estimate scope: 123 (estimated 120)",
                "- Total requests this fetch: 130",
                "- Core quota remaining before: 4,877 / 5,000",
                "- Core rate limit: 5,000 requests/hour (authenticated) - "
                "https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api",
                "- By resource (estimate scope): actions 100, billing 20, repos 1",
                "- Source: live fetch",
            ],
        )

    def test_legacy_scope_label_mentions_account_level(self):
        lines = api_usage_lines(_estimate(estimate_scope="full-report-including-account-level"))
        self.assertTrue(lines[0].startswith("- All requests in estimate scope:"))

    def test_unknown_scope_falls_back_to_neutral_label(self):
        lines = api_usage_lines(_estimate(estimate_scope="something-new"))
        self.assertTrue(lines[0].startswith("- Requests in estimate scope:"))

    def test_missing_measurement_renders_no_lines(self):
        # No measurement keys: estimate-only dicts (and None) must not render
        # as measured zeros.
        self.assertEqual(api_usage_lines({}), [])
        self.assertEqual(api_usage_lines(None), [])
        self.assertEqual(
            api_usage_lines(
                {
                    "core_limit": 5000,
                    "core_remaining": 4877,
                    "estimated_incremental_requests": 120,
                }
            ),
            [],
        )

    def test_missing_quota_and_breakdown_lines_are_skipped(self):
        estimate = _estimate(core_limit=None, core_remaining=None)
        del estimate["actual_requests_by_resource"]
        lines = api_usage_lines(estimate)
        self.assertNotIn("Core quota remaining before", "\n".join(lines))
        self.assertNotIn("By resource", "\n".join(lines))
        # Documented fallback limit still renders.
        self.assertIn("Core rate limit: 5,000 requests/hour", "\n".join(lines))

    def test_zero_buckets_are_filtered_from_breakdown(self):
        estimate = _estimate(
            actual_requests=2,
            total_requests=2,
            estimated_incremental_requests=5,
            actual_requests_by_resource={"billing": 0, "user": 2, "actions": 0},
        )
        lines = api_usage_lines(estimate)
        self.assertIn("- By resource (estimate scope): user 2", lines)

    def test_all_zero_buckets_omit_breakdown_line(self):
        estimate = _estimate(
            actual_requests=0,
            total_requests=0,
            actual_requests_by_resource={"billing": 0, "user": 0},
        )
        self.assertNotIn("By resource", "\n".join(api_usage_lines(estimate)))

    def test_cache_hit_reports_zero_new_requests_with_original_total(self):
        lines = api_usage_lines(_estimate(from_cache=True))
        self.assertIn("- Total requests (original fetch): 130", lines)
        self.assertIn(
            "- Source: cached report (0 new API requests; 130 total during the original fetch)",
            lines,
        )

    def test_non_numeric_counts_fall_back_to_zero(self):
        lines = api_usage_lines(_estimate(actual_requests="many", total_requests=None))
        self.assertTrue(lines[0].startswith("- Repo requests in estimate scope: 0 "))
        self.assertEqual(lines[1], "- Total requests this fetch: 0")


class ApiUsageRowsTests(unittest.TestCase):
    def test_rows_derive_labels_and_values_from_lines(self):
        rows = api_usage_rows(_estimate())
        self.assertEqual(
            rows[0],
            ("Repo requests in estimate scope", "123 (estimated 120)"),
        )
        self.assertEqual(rows[1], ("Total requests this fetch", "130"))
        self.assertEqual(rows[-1], ("Source", "live fetch"))

    def test_rows_cover_every_line(self):
        estimate = _estimate()
        self.assertEqual(len(api_usage_rows(estimate)), len(api_usage_lines(estimate)))

    def test_rows_empty_without_measurement(self):
        self.assertEqual(api_usage_rows({}), [])
        self.assertEqual(api_usage_rows(None), [])


if __name__ == "__main__":
    unittest.main()
