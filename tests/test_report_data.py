import unittest
from unittest import mock

from tests._fakes import FakeAPI

_PRIVATE_REPO = {
    "full_name": "octocat/private-repo",
    "owner": {"login": "octocat"},
    "name": "private-repo",
    "visibility": "private",
}

_PUBLIC_REPO = {
    "full_name": "octocat/public-repo",
    "owner": {"login": "octocat"},
    "name": "public-repo",
    "visibility": "public",
}

_TWO_REPOS = (_PRIVATE_REPO, _PUBLIC_REPO)

_PRIVATE_ROW = {
    "repo": "octocat/private-repo",
    "minutes": 1000.0,
    "storage_gb_hours": 0.0,
    "avg_mb": 0.0,
    "gross": 0.0,
    "sku": {},
    "visibility": "private",
}

_PUBLIC_ROW = {
    "repo": "octocat/public-repo",
    "minutes": 500.0,
    "storage_gb_hours": 0.0,
    "avg_mb": 0.0,
    "gross": 0.0,
    "sku": {},
    "visibility": "public",
}

_DEFAULT_FAKE_ROWS = (_PRIVATE_ROW, _PUBLIC_ROW)

_DEFAULT_KWARGS = {
    "include_actions": True,
    "include_copilot": False,
    "include_lfs": False,
    "include_consumers": False,
    "include_artifact_storage": False,
    "include_release_assets": False,
    "max_repos": 100,
    "warn_over": None,
}


def _make_billing_api(
    actions_items=None,
    copilot_items=None,
    premium_items=None,
    lfs_items=None,
    rate_limit=None,
    pages=None,
    omit=(),
):
    """Return a FakeAPI pre-loaded with standard billing endpoints.

    Pass ``omit=("actions",)`` to exclude the Actions endpoint.
    """
    responses = {}
    default_rate = {"resources": {"core": {"limit": 5000, "remaining": 4900}}}

    if "actions" not in omit:
        responses[
            ("GET", "/users/octocat/settings/billing/usage/summary", (("product", "Actions"),))
        ] = {"usageItems": actions_items or []}

    if "copilot" not in omit:
        responses[
            ("GET", "/users/octocat/settings/billing/usage/summary", (("product", "Copilot"),))
        ] = {"usageItems": copilot_items or []}
        responses[
            (
                "GET",
                "/users/octocat/settings/billing/premium_request/usage",
                (("product", "copilot"),),
            )
        ] = {"usageItems": premium_items or []}

    if "lfs" not in omit:
        responses[
            ("GET", "/users/octocat/settings/billing/usage/summary", (("product", "git_lfs"),))
        ] = {"usageItems": lfs_items or []}

    if "rate_limit" not in omit:
        responses[("GET", "/rate_limit", ())] = rate_limit or default_rate

    return FakeAPI(
        request_responses=responses,
        pages_responses=pages or {},
    )


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
            include_actions=False,
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

    def test_estimate_includes_actions_fallback_when_consumers_disabled(self):
        from github_usage.report_data import estimate_api_request_count

        estimate = estimate_api_request_count(
            repo_count=10,
            include_actions=True,
            include_consumers=False,
            include_artifact_storage=False,
            include_release_assets=False,
            max_repos=100,
        )
        self.assertEqual(estimate["estimated_incremental_requests"], 10)

    def test_estimate_skips_actions_fallback_when_consumers_enabled(self):
        from github_usage.report_data import estimate_api_request_count

        estimate = estimate_api_request_count(
            repo_count=10,
            include_actions=True,
            include_consumers=True,
            include_artifact_storage=False,
            include_release_assets=False,
            max_repos=100,
        )
        self.assertEqual(estimate["estimated_incremental_requests"], 20)

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

    def test_get_copilot_usage_prefers_ai_credit_when_present(self):
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
                    "/users/octocat/settings/billing/ai_credit/usage",
                    (("product", "copilot"),),
                ): {
                    "usageItems": [
                        {
                            "model": "gpt-4.1",
                            "grossQuantity": 1.0,
                            "grossAmount": 0.5,
                            "discountAmount": 0.0,
                            "netAmount": 0.5,
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
                            "model": "legacy-model",
                            "grossQuantity": 99.0,
                            "grossAmount": 0.0,
                            "discountAmount": 0.0,
                            "netAmount": 0.0,
                        }
                    ]
                },
            }
        )

        result = get_copilot_usage(api, "octocat")

        self.assertEqual(result["metering"], "ai_credits")
        self.assertEqual(result["total_credits_used"], 1.0)
        self.assertIn("gpt-4.1", result["by_model"])
        self.assertNotIn("legacy-model", result["by_model"])

    def test_get_copilot_usage_ai_credit_included_usage_uses_gross_quantity(self):
        """Included AI credit rows can have netAmount 0 while grossQuantity is non-zero."""
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
                    "/users/octocat/settings/billing/ai_credit/usage",
                    (("product", "copilot"),),
                ): {
                    "usageItems": [
                        {
                            "model": "gpt-4.1",
                            "grossQuantity": 3956.18,
                            "netQuantity": 0.0,
                            "grossAmount": 39.56,
                            "discountAmount": 39.56,
                            "netAmount": 0.0,
                        }
                    ]
                },
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
            }
        )

        result = get_copilot_usage(api, "octocat")

        self.assertEqual(result["metering"], "ai_credits")
        self.assertAlmostEqual(result["total_credits_used"], 3956.18)
        self.assertAlmostEqual(result["by_model"]["gpt-4.1"]["requests"], 3956.18)

    def test_get_copilot_usage_falls_back_to_premium_when_ai_empty(self):
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
                    "/users/octocat/settings/billing/ai_credit/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {
                    "usageItems": [
                        {
                            "model": "gpt-4.1",
                            "grossQuantity": 12.0,
                            "grossAmount": 0.0,
                            "discountAmount": 0.0,
                            "netAmount": 0.0,
                        }
                    ]
                },
            }
        )

        result = get_copilot_usage(api, "octocat")

        self.assertEqual(result["metering"], "premium_requests")
        self.assertEqual(result["total_requests"], 12.0)

    def test_get_copilot_usage_raises_when_both_endpoints_fail(self):
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
                    "/users/octocat/settings/billing/ai_credit/usage",
                    (("product", "copilot"),),
                ): RuntimeError("403 Forbidden"),
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): RuntimeError("403 Forbidden"),
            }
        )

        with self.assertRaisesRegex(RuntimeError, "Copilot usage unavailable"):
            get_copilot_usage(api, "octocat")

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
                    "/users/octocat/settings/billing/ai_credit/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
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
                    "/users/octocat/settings/billing/ai_credit/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): [1, 2, 3],  # list instead of dict
            }
        )

        result = get_copilot_usage(api, "octocat")

        self.assertEqual(result["metering"], "ai_credits")
        self.assertIn("Premium request usage unavailable", result["usage_note"] or "")

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

        api = _make_billing_api(
            actions_items=[
                {
                    "sku": "actions_linux",
                    "unitType": "minutes",
                    "grossQuantity": 1500.0,
                    "grossAmount": 0.0,
                    "discountAmount": 0.0,
                    "netAmount": 0.0,
                }
            ],
            pages={"/user/repos": _TWO_REPOS},
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
                api, "octocat", **{**_DEFAULT_KWARGS, "include_consumers": True}
            )
        actions = report["actions"]
        self.assertEqual(actions["private_minutes"], 1000.0)
        self.assertEqual(actions["public_minutes"], 500.0)
        mock_fetch.assert_not_called()

    def test_actions_only_uses_fetch_repo_actions_table(self):
        from github_usage.report_data import build_report_data

        api = _make_billing_api(
            actions_items=[
                {
                    "sku": "actions_linux",
                    "unitType": "minutes",
                    "grossQuantity": 1500.0,
                    "grossAmount": 0.0,
                    "discountAmount": 0.0,
                    "netAmount": 0.0,
                }
            ],
            pages={"/user/repos": _TWO_REPOS},
        )
        with mock.patch(
            "github_usage.report_data.fetch_repo_actions_table",
            return_value=(list(_DEFAULT_FAKE_ROWS), {}),
        ) as mock_fetch:
            report = build_report_data(api, "octocat", **_DEFAULT_KWARGS)
        actions = report["actions"]
        self.assertEqual(actions["private_minutes"], 1000.0)
        self.assertEqual(actions["public_minutes"], 500.0)
        mock_fetch.assert_called_once_with(api, _TWO_REPOS)

    def test_actions_disabled_skips_per_repo_fetch(self):
        from github_usage.report_data import build_report_data

        api = _make_billing_api(omit=("actions",))
        with mock.patch(
            "github_usage.report_data.fetch_repo_actions_table",
        ) as mock_fetch:
            report = build_report_data(
                api, "octocat", **{**_DEFAULT_KWARGS, "include_actions": False}
            )
        self.assertIsNone(report["actions"])
        mock_fetch.assert_not_called()

    def test_consumers_error_falls_back_to_fetch_repo_actions_table(self):
        from github_usage.report_data import build_report_data

        api = _make_billing_api(
            actions_items=[
                {
                    "sku": "actions_linux",
                    "unitType": "minutes",
                    "grossQuantity": 1500.0,
                    "grossAmount": 0.0,
                    "discountAmount": 0.0,
                    "netAmount": 0.0,
                }
            ],
            pages={"/user/repos": _TWO_REPOS},
        )
        with (
            mock.patch(
                "github_usage.report_data.get_repo_consumers",
                side_effect=RuntimeError("consumers API failure"),
            ),
            mock.patch(
                "github_usage.report_data.fetch_repo_actions_table",
                return_value=(list(_DEFAULT_FAKE_ROWS), {}),
            ) as mock_fetch,
        ):
            report = build_report_data(
                api, "octocat", **{**_DEFAULT_KWARGS, "include_consumers": True}
            )
        actions = report["actions"]
        self.assertEqual(actions["private_minutes"], 1000.0)
        self.assertEqual(actions["public_minutes"], 500.0)
        mock_fetch.assert_called_once_with(api, _TWO_REPOS)

    def test_fallback_fetch_errors_propagated_into_report(self):
        from github_usage.report_data import build_report_data

        api = _make_billing_api(pages={"/user/repos": _TWO_REPOS})
        fallback_errors = {"octocat/private-repo": "billing fetch failed"}
        with mock.patch(
            "github_usage.report_data.fetch_repo_actions_table",
            return_value=([_PUBLIC_ROW], fallback_errors),
        ):
            report = build_report_data(api, "octocat", **_DEFAULT_KWARGS)
        self.assertIn("octocat/private-repo", report["errors"])

    def test_only_public_passes_through_to_visibility_split(self):
        from github_usage.report_data import build_report_data

        api = _make_billing_api(
            actions_items=[
                {
                    "sku": "actions_linux",
                    "unitType": "minutes",
                    "grossQuantity": 500.0,
                    "grossAmount": 0.0,
                    "discountAmount": 0.0,
                    "netAmount": 0.0,
                }
            ],
            pages={"/user/repos": _TWO_REPOS},
        )
        public_row = {**_PUBLIC_ROW, "minutes": 500.0}
        with mock.patch(
            "github_usage.report_data.fetch_repo_actions_table",
            return_value=([public_row], {}),
        ) as mock_fetch:
            report = build_report_data(api, "octocat", **{**_DEFAULT_KWARGS, "only_public": True})
        mock_fetch.assert_called_once_with(api, [_PUBLIC_REPO])
        self.assertTrue(report["actions"]["filtered"])
        self.assertEqual(report["actions"]["public_minutes"], 500.0)
        self.assertEqual(report["actions"]["private_minutes"], 0.0)


def _email_kwargs(**overrides):
    params = dict(_DEFAULT_KWARGS)
    params.update(include_consumers=True, max_repos=10)
    params.update(overrides)
    return params


# Sample repos: no visibility key (treated as public), zero usage with the
# default fake responses.
_SAMPLE_PUBLIC_REPOS = [
    {"full_name": "octocat/r1", "owner": {"login": "octocat"}, "name": "r1"},
    {"full_name": "octocat/r2", "owner": {"login": "octocat"}, "name": "r2"},
]


class ApiUsageBuilderMergeTests(unittest.TestCase):
    def test_email_merge_zeroed_stats_for_non_counting_client(self):
        from github_usage.report_data import build_report_data

        api = FakeAPI(pages_responses={"/user/repos": []})
        report = build_report_data(api, "octocat", **_email_kwargs())
        estimate = report["api_estimate"]
        self.assertEqual(estimate["actual_requests"], 0)
        self.assertEqual(estimate["total_requests"], 0)
        self.assertEqual(estimate["actual_requests_by_resource"], {})
        self.assertEqual(estimate["estimate_scope"], "repo-sections-only")
        self.assertFalse(estimate["from_cache"])
        self.assertEqual(
            estimate["estimate_variance"], 0 - estimate["estimated_incremental_requests"]
        )

    def test_email_actual_counts_only_repo_level_calls(self):
        import json

        from github_usage.report_api_usage import SCOPE_REPO_SECTIONS
        from github_usage.report_data import build_report_data
        from tests._fakes import CountingFakeAPI

        api = CountingFakeAPI(pages_responses={"/user/repos": list(_SAMPLE_PUBLIC_REPOS)})
        report = build_report_data(api, "octocat", **_email_kwargs())
        estimate = report["api_estimate"]
        # Only the two per-repo billing calls fall in the estimate window.
        self.assertEqual(estimate["actual_requests"], 2)
        self.assertEqual(
            estimate["actual_requests_by_resource"],
            {
                "billing": 2,
                "user": 0,
                "rate_limit": 0,
                "actions": 0,
                "repos": 0,
                "other": 0,
            },
        )
        # Account-level calls (/rate_limit, billing summaries, monthly costs)
        # land in the total but not in the window delta.
        self.assertGreater(estimate["total_requests"], estimate["actual_requests"])
        self.assertEqual(estimate["estimate_scope"], SCOPE_REPO_SECTIONS)
        self.assertEqual(
            estimate["estimate_variance"],
            estimate["actual_requests"] - estimate["estimated_incremental_requests"],
        )
        self.assertFalse(estimate["from_cache"])
        # Raw request paths never enter the report, so exports cannot leak them.
        blob = json.dumps(estimate)
        self.assertNotIn("request_log", blob)
        self.assertNotIn("/user/repos", blob)
        self.assertNotIn("/repos/", blob)

    def test_email_fallback_path_tracks_fetch_repo_actions_table(self):
        from github_usage.report_data import build_report_data
        from tests._fakes import CountingFakeAPI

        api = CountingFakeAPI(pages_responses={"/user/repos": list(_SAMPLE_PUBLIC_REPOS)})
        report = build_report_data(api, "octocat", **_email_kwargs(include_consumers=False))
        estimate = report["api_estimate"]
        self.assertEqual(estimate["actual_requests"], 2)
        self.assertEqual(
            estimate["actual_requests_by_resource"],
            {
                "billing": 2,
                "user": 0,
                "rate_limit": 0,
                "actions": 0,
                "repos": 0,
                "other": 0,
            },
        )

    def test_email_partial_failure_still_merges_made_calls(self):
        from unittest import mock

        from github_usage.billing import BillingFetchError, get_actions_per_repo
        from github_usage.report_data import build_report_data
        from tests._fakes import CountingFakeAPI

        api = CountingFakeAPI(pages_responses={"/user/repos": list(_SAMPLE_PUBLIC_REPOS)})
        calls = []

        def flaky(api_arg, owner, name):
            calls.append((owner, name))
            if len(calls) > 1:
                raise BillingFetchError(f"{owner}/{name}: boom")
            return get_actions_per_repo(api_arg, owner, name)

        with mock.patch("github_usage.report_optional.get_actions_per_repo", side_effect=flaky):
            report = build_report_data(api, "octocat", **_email_kwargs())
        consumers = report["repo_consumers"]
        self.assertIn("octocat/r2", consumers["errors"])
        estimate = report["api_estimate"]
        # The one successful per-repo call is counted despite the failure;
        # only repo-level calls land in the window delta.
        self.assertEqual(estimate["actual_requests"], 1)
        self.assertEqual(
            estimate["actual_requests_by_resource"],
            {
                "billing": 1,
                "user": 0,
                "rate_limit": 0,
                "actions": 0,
                "repos": 0,
                "other": 0,
            },
        )
        self.assertGreater(estimate["total_requests"], estimate["actual_requests"])
        self.assertEqual(
            estimate["estimate_variance"],
            estimate["actual_requests"] - estimate["estimated_incremental_requests"],
        )

    def test_email_section_failure_still_tracks_and_falls_back(self):
        from unittest import mock

        from github_usage.billing import get_actions_per_repo
        from github_usage.report_data import build_report_data
        from tests._fakes import CountingFakeAPI

        api = CountingFakeAPI(pages_responses={"/user/repos": list(_SAMPLE_PUBLIC_REPOS)})
        calls = []

        def flaky(api_arg, owner, name):
            # A real counted call, then an abort that escapes get_repo_consumers
            # (plain RuntimeError, not BillingFetchError) into _try_section.
            calls.append((owner, name))
            result = get_actions_per_repo(api_arg, owner, name)
            if len(calls) > 1:
                raise RuntimeError("mid-scan abort")
            return result

        with mock.patch("github_usage.report_optional.get_actions_per_repo", side_effect=flaky):
            report = build_report_data(api, "octocat", **_email_kwargs())
        # The consumers section failed and fell back to the per-repo table.
        self.assertIn("repo_consumers", report["errors"])
        estimate = report["api_estimate"]
        # 2 aborted-section calls + 2 fallback calls, all tracked.
        self.assertEqual(estimate["actual_requests"], 4)
        self.assertEqual(
            estimate["actual_requests_by_resource"],
            {
                "billing": 4,
                "user": 0,
                "rate_limit": 0,
                "actions": 0,
                "repos": 0,
                "other": 0,
            },
        )

    def test_email_artifact_and_release_sections_are_tracked(self):
        from github_usage.report_data import build_report_data
        from tests._fakes import CountingFakeAPI

        pages = {
            "/user/repos": list(_SAMPLE_PUBLIC_REPOS),
            "/repos/octocat/r1/actions/artifacts": [{"id": 1, "size_in_bytes": 10}],
            "/repos/octocat/r1/releases": [{"assets": [{"size": 5}]}],
            "/repos/octocat/r2/actions/artifacts": [],
            "/repos/octocat/r2/releases": [],
        }
        api = CountingFakeAPI(pages_responses=pages)
        report = build_report_data(
            api,
            "octocat",
            **_email_kwargs(
                include_actions=False,
                include_consumers=False,
                include_artifact_storage=True,
                include_release_assets=True,
            ),
        )
        estimate = report["api_estimate"]
        # 2 artifact + 2 release per-repo calls; artifact/release pages bucket
        # as actions/repos (not billing).
        self.assertEqual(estimate["actual_requests"], 4)
        self.assertEqual(
            estimate["actual_requests_by_resource"],
            {
                "billing": 0,
                "user": 0,
                "rate_limit": 0,
                "actions": 2,
                "repos": 2,
                "other": 0,
            },
        )

    def test_email_workflow_breakdown_calls_are_tracked(self):
        from unittest import mock

        from github_usage.report_data import build_report_data
        from tests._fakes import CountingFakeAPI

        repos = [
            {
                "full_name": "octocat/priv",
                "owner": {"login": "octocat"},
                "name": "priv",
                "visibility": "private",
            }
        ]
        api = CountingFakeAPI(pages_responses={"/user/repos": repos})
        with mock.patch(
            "github_usage.report_optional.get_actions_per_repo",
            return_value=(10.0, 0.0, {"sku": {"grossAmount": 1.0}}),
        ):
            report = build_report_data(api, "octocat", **_email_kwargs())
        estimate = report["api_estimate"]
        # 1 mocked consumers call (uncounted) + runs pages + workflows pages.
        self.assertEqual(estimate["actual_requests"], 2)
        self.assertEqual(estimate["actual_requests_by_resource"]["actions"], 2)
