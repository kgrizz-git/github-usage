"""Tests for per-workflow estimated minutes (Phase 4 / 6d)."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._fakes import FakeAPI

_CAVEAT = "(estimated from run wall-clock; not billable — will not match billed repo total)"


def _completed_run(
    *,
    workflow_id: int = 1,
    name: str = "CI",
    status: str = "completed",
    run_started_at: str = "2026-08-01T10:00:00Z",
    updated_at: str = "2026-08-01T10:01:30Z",
    created_at: str = "2026-08-01T09:59:00Z",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "name": name,
        "status": status,
        "run_started_at": run_started_at,
        "updated_at": updated_at,
        "created_at": created_at,
    }


def _billing_summary_responses(login: str = "octocat") -> dict:
    """Shared FakeAPI billing request_responses for legacy builder tests."""
    return {
        ("GET", "/user", ()): {"login": login, "type": "User", "plan": {}},
        ("GET", "/rate_limit", ()): {"resources": {"core": {"limit": 5000, "remaining": 5000}}},
        (
            "GET",
            f"/users/{login}/settings/billing/usage/summary",
            (("product", "Actions"),),
        ): {"usageItems": []},
        (
            "GET",
            f"/users/{login}/settings/billing/usage/summary",
            (("product", "Copilot"),),
        ): {"usageItems": []},
        (
            "GET",
            f"/users/{login}/settings/billing/usage/summary",
            (("product", "git_lfs"),),
        ): {"usageItems": []},
        (
            "GET",
            f"/users/{login}/settings/billing/premium_request/usage",
            (("product", "copilot"),),
        ): {"usageItems": []},
        ("GET", f"/users/{login}/settings/billing/usage", ()): {"usageItems": []},
    }


class FetchWorkflowMinutesTests(unittest.TestCase):
    def test_aggregates_by_workflow_id_sorted_desc(self) -> None:
        from github_usage.report_workflow_minutes import fetch_workflow_minutes

        runs = [
            _completed_run(
                workflow_id=1,
                name="CI",
                run_started_at="2026-08-01T10:00:00Z",
                updated_at="2026-08-01T10:02:00Z",
            ),
            _completed_run(
                workflow_id=2,
                name="Deploy",
                run_started_at="2026-08-01T11:00:00Z",
                updated_at="2026-08-01T11:06:00Z",
            ),
            _completed_run(
                workflow_id=1,
                name="CI",
                run_started_at="2026-08-01T12:00:00Z",
                updated_at="2026-08-01T12:01:00Z",
            ),
        ]
        api = FakeAPI(
            pages_responses={
                "/repos/octocat/priv/actions/runs": runs,
                "/repos/octocat/priv/actions/workflows": [
                    {"id": 1, "name": "CI Workflow"},
                    {"id": 2, "name": "Deploy Workflow"},
                ],
            }
        )
        cache: dict = {}
        result = fetch_workflow_minutes(api, "octocat", "priv", runs_cache=cache)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["repo"], "octocat/priv")
        names = [entry["name"] for entry in result["by_workflow"]]
        self.assertEqual(names, ["Deploy Workflow", "CI Workflow"])
        deploy = result["by_workflow"][0]
        self.assertEqual(deploy["runs"], 1)
        self.assertAlmostEqual(deploy["minutes"], 6.0)

    def test_skips_non_completed_and_zero_duration(self) -> None:
        from github_usage.report_workflow_minutes import fetch_workflow_minutes

        runs = [
            _completed_run(status="in_progress"),
            _completed_run(updated_at="2026-08-01T10:00:00Z"),  # zero duration
            _completed_run(updated_at="2026-08-01T10:01:00Z"),
        ]
        api = FakeAPI(pages_responses={"/repos/o/r/actions/runs": runs})
        result = fetch_workflow_minutes(api, "o", "r", runs_cache={})

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["by_workflow"][0]["runs"], 1)

    def test_soft_fails_workflow_name_map_uses_run_name(self) -> None:
        from github_usage.report_workflow_minutes import fetch_workflow_minutes

        class FailingWorkflowsAPI(FakeAPI):
            def get_all_pages(self, path, params=None, limit=None):
                if path.endswith("/actions/workflows"):
                    raise RuntimeError("forbidden")
                return super().get_all_pages(path, params, limit)

        runs = [_completed_run(name="Nightly", updated_at="2026-08-01T10:02:00Z")]
        api = FailingWorkflowsAPI(
            pages_responses={"/repos/o/r/actions/runs": runs},
        )
        result = fetch_workflow_minutes(api, "o", "r", runs_cache={})
        self.assertIsNotNone(result)
        assert result is not None

        self.assertEqual(result["by_workflow"][0]["name"], "Nightly")

    def test_fractional_minutes_not_ceiled(self) -> None:
        from github_usage.report_workflow_minutes import fetch_workflow_minutes

        runs = [_completed_run(updated_at="2026-08-01T10:00:30Z")]  # 30 sec = 0.5 min
        api = FakeAPI(pages_responses={"/repos/o/r/actions/runs": runs})
        result = fetch_workflow_minutes(api, "o", "r", runs_cache={})
        self.assertIsNotNone(result)
        assert result is not None

        self.assertAlmostEqual(result["by_workflow"][0]["minutes"], 0.5)
        self.assertAlmostEqual(result["total_minutes"], 0.5)

    def test_timezone_safe_z_and_offset_timestamps(self) -> None:
        from github_usage.report_workflow_minutes import fetch_workflow_minutes

        runs = [
            _completed_run(
                run_started_at="2026-08-01T10:00:00Z",
                updated_at="2026-08-01T10:01:30+00:00",
            )
        ]
        api = FakeAPI(pages_responses={"/repos/o/r/actions/runs": runs})
        result = fetch_workflow_minutes(api, "o", "r", runs_cache={})
        self.assertIsNotNone(result)
        assert result is not None

        self.assertAlmostEqual(result["by_workflow"][0]["minutes"], 1.5)

    def test_returns_none_when_no_usable_runs(self) -> None:
        from github_usage.report_workflow_minutes import fetch_workflow_minutes

        api = FakeAPI(pages_responses={"/repos/o/r/actions/runs": []})
        self.assertIsNone(fetch_workflow_minutes(api, "o", "r", runs_cache={}))

    def test_shared_runs_cache_avoids_second_api_fetch(self) -> None:
        from github_usage.report_workflow_minutes import fetch_workflow_minutes

        runs = [_completed_run(updated_at="2026-08-01T10:02:00Z")]
        api = FakeAPI(pages_responses={"/repos/o/r/actions/runs": runs})
        cache: dict = {}
        fetch_workflow_minutes(api, "o", "r", runs_cache=cache)
        before = len(api.requests)
        fetch_workflow_minutes(api, "o", "r", runs_cache=cache)
        runs_calls = [
            r for r in api.requests[before:] if r[0] == "PAGES" and r[1].endswith("/actions/runs")
        ]
        self.assertEqual(runs_calls, [])


class RenderWorkflowBreakdownTests(unittest.TestCase):
    def test_renderer_includes_caveat_and_fractional_minutes(self) -> None:
        from github_usage.report_workflow_minutes import render_workflow_breakdown

        breakdown = {
            "repo": "octocat/priv",
            "total_minutes": 1.5,
            "by_workflow": [
                {"name": "CI", "runs": 1, "minutes": 1.5},
            ],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            render_workflow_breakdown(breakdown)
        output = buf.getvalue()
        self.assertIn("Minutes by Workflow", output)
        self.assertIn("octocat/priv", output)
        self.assertIn(_CAVEAT, output)
        self.assertIn("1.5 min", output)
        self.assertIn("100.0%", output)

    def test_renderer_noop_when_falsy(self) -> None:
        from github_usage.report_workflow_minutes import render_workflow_breakdown

        buf = io.StringIO()
        with redirect_stdout(buf):
            render_workflow_breakdown(None)
            render_workflow_breakdown({})
        self.assertEqual(buf.getvalue(), "")


class BuilderWorkflowBreakdownTests(unittest.TestCase):
    def test_legacy_builder_stores_breakdown_when_top_private_has_minutes(self) -> None:
        from github_usage.legacy_report_data import build_legacy_report_data

        repos = [{"name": "priv", "owner": {"login": "octocat"}, "full_name": "octocat/priv"}]
        api = FakeAPI(
            request_responses=_billing_summary_responses(),
            pages_responses={
                "/user/repos": repos,
                "/repos/octocat/priv/actions/runs": [
                    _completed_run(updated_at="2026-08-01T10:02:00Z")
                ],
            },
        )
        with mock.patch(
            "github_usage.legacy_report_data.fetch_repo_actions_table",
            return_value=(
                [
                    {
                        "repo": "octocat/priv",
                        "minutes": 50.0,
                        "storage_gb_hours": 1.0,
                        "avg_mb": 1.0,
                        "gross": 1.0,
                        "sku": {},
                        "visibility": "private",
                    }
                ],
                {},
            ),
        ):
            data = build_legacy_report_data(
                api,
                "octocat",
                max_repos=100,
                account={"login": "octocat", "type": "User", "plan": {}},
                rate_limits={"resources": {"core": {"limit": 5000, "remaining": 5000}}},
            )
        self.assertIsNotNone(data.get("workflow_breakdown"))
        self.assertEqual(data["workflow_breakdown"]["repo"], "octocat/priv")

    def test_legacy_builder_omits_breakdown_when_top_private_zero_minutes(self) -> None:
        from github_usage.legacy_report_data import build_legacy_report_data

        with mock.patch(
            "github_usage.legacy_report_data.fetch_repo_actions_table",
            return_value=(
                [
                    {
                        "repo": "octocat/priv",
                        "minutes": 0.0,
                        "storage_gb_hours": 0.0,
                        "avg_mb": 0.0,
                        "gross": 0.0,
                        "sku": {},
                        "visibility": "private",
                    }
                ],
                {},
            ),
        ):
            data = build_legacy_report_data(
                FakeAPI(
                    request_responses={
                        ("GET", "/rate_limit", ()): {
                            "resources": {"core": {"limit": 5000, "remaining": 5000}}
                        },
                    },
                    pages_responses={"/user/repos": []},
                ),
                "octocat",
                max_repos=100,
                account={"login": "octocat", "type": "User", "plan": {}},
                rate_limits={"resources": {"core": {"limit": 5000, "remaining": 5000}}},
            )
        self.assertIsNone(data.get("workflow_breakdown"))

    def test_email_builder_stores_breakdown_when_include_consumers_and_private_top(self) -> None:
        from github_usage.report_data import build_report_data

        repos = [
            {
                "name": "priv",
                "owner": {"login": "octocat"},
                "full_name": "octocat/priv",
                "private": True,
            }
        ]
        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 5000}}
                },
            },
            pages_responses={
                "/user/repos": repos,
                "/repos/octocat/priv/actions/billing/usage": {"total_minutes_used": 10},
                "/repos/octocat/priv/actions/runs": [
                    _completed_run(updated_at="2026-08-01T10:03:00Z")
                ],
            },
        )
        with mock.patch(
            "github_usage.report_optional.get_actions_per_repo",
            return_value=(25.0, 0.0, {"sku": {"grossAmount": 1.0}}),
        ):
            report = build_report_data(
                api,
                "octocat",
                include_actions=False,
                include_copilot=False,
                include_lfs=False,
                include_consumers=True,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
            )
        self.assertIsNotNone(report.get("workflow_breakdown"))

    def test_email_builder_soft_fails_workflow_breakdown(self) -> None:
        """RuntimeError from workflow fetch is recorded; report still completes."""
        from github_usage.report_data import build_report_data

        repos = [
            {
                "name": "priv",
                "owner": {"login": "octocat"},
                "full_name": "octocat/priv",
                "private": True,
            }
        ]
        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 5000}}
                },
            },
            pages_responses={"/user/repos": repos},
        )
        with (
            mock.patch(
                "github_usage.report_optional.get_actions_per_repo",
                return_value=(25.0, 0.0, {"sku": {"grossAmount": 1.0}}),
            ),
            mock.patch(
                "github_usage.report_data.workflow_breakdown_for_top_private",
                side_effect=RuntimeError("workflow fetch failed"),
            ),
        ):
            report = build_report_data(
                api,
                "octocat",
                include_actions=False,
                include_copilot=False,
                include_lfs=False,
                include_consumers=True,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
            )
        self.assertNotIn("workflow_breakdown", report)
        self.assertEqual(report["errors"].get("workflow_breakdown"), "workflow fetch failed")

    def test_legacy_builder_soft_fails_workflow_breakdown(self) -> None:
        """RuntimeError from workflow fetch is recorded; legacy report still completes."""
        from github_usage.legacy_report_data import build_legacy_report_data

        with (
            mock.patch(
                "github_usage.legacy_report_data.fetch_repo_actions_table",
                return_value=(
                    [
                        {
                            "repo": "octocat/priv",
                            "minutes": 50.0,
                            "storage_gb_hours": 1.0,
                            "avg_mb": 1.0,
                            "gross": 1.0,
                            "sku": {},
                            "visibility": "private",
                        }
                    ],
                    {},
                ),
            ),
            mock.patch(
                "github_usage.legacy_report_data.workflow_breakdown_for_top_private",
                side_effect=RuntimeError("workflow fetch failed"),
            ),
        ):
            data = build_legacy_report_data(
                FakeAPI(
                    request_responses={
                        ("GET", "/rate_limit", ()): {
                            "resources": {"core": {"limit": 5000, "remaining": 5000}}
                        },
                    },
                    pages_responses={"/user/repos": []},
                ),
                "octocat",
                max_repos=100,
                account={"login": "octocat", "type": "User", "plan": {}},
                rate_limits={"resources": {"core": {"limit": 5000, "remaining": 5000}}},
            )
        self.assertIsNone(data.get("workflow_breakdown"))
        self.assertEqual(data["errors"].get("workflow_breakdown"), "workflow fetch failed")


class QuotaEstimateTests(unittest.TestCase):
    def test_legacy_estimate_includes_workflow_breakdown_headroom(self) -> None:
        from github_usage.legacy_report_data import estimate_legacy_api_request_count

        base = estimate_legacy_api_request_count(
            10,
            max_repos=100,
            include_release_assets=False,
            core_limit=5000,
            core_remaining=5000,
        )
        self.assertGreaterEqual(base["estimated_incremental_requests"], 10 + 10)

    def test_email_estimate_adds_workflow_headroom_when_consumers_enabled(self) -> None:
        from github_usage.report_optional import estimate_api_request_count

        with_consumers = estimate_api_request_count(
            repo_count=5,
            include_consumers=True,
            include_artifact_storage=False,
            include_release_assets=False,
            max_repos=100,
        )
        without = estimate_api_request_count(
            repo_count=5,
            include_consumers=False,
            include_artifact_storage=False,
            include_release_assets=False,
            max_repos=100,
        )
        self.assertEqual(
            with_consumers["estimated_incremental_requests"],
            without["estimated_incremental_requests"] + 5 + 10,
        )


class EmailWorkflowBreakdownTests(unittest.TestCase):
    def _sample_breakdown(self) -> dict:
        return {
            "repo": "octocat/priv",
            "total_minutes": 10.5,
            "by_workflow": [
                {"name": "CI", "runs": 3, "minutes": 6.0},
                {"name": "Deploy", "runs": 1, "minutes": 4.5},
            ],
        }

    def test_text_section_includes_caveat_and_top_five(self) -> None:
        from github_usage.email_report_text import _format_workflow_breakdown_section

        text = "\n".join(
            _format_workflow_breakdown_section({"workflow_breakdown": self._sample_breakdown()})
        )
        self.assertIn("Minutes by Workflow", text)
        self.assertIn(_CAVEAT, text)
        self.assertIn("CI", text)
        self.assertIn("6.0 min", text)

    def test_html_section_includes_caveat_and_table(self) -> None:
        from github_usage.email_report_html import _format_html_workflow_breakdown_section

        html = "\n".join(
            _format_html_workflow_breakdown_section(
                {"workflow_breakdown": self._sample_breakdown()}
            )
        )
        self.assertIn("Minutes by Workflow", html)
        self.assertIn(_CAVEAT, html)
        self.assertIn("<table>", html)
        self.assertIn("Deploy", html)


if __name__ == "__main__":
    unittest.main()
