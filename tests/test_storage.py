import unittest
from datetime import date
from unittest import mock

from tests._fakes import FakeAPI


class StorageTests(unittest.TestCase):
    def test_get_storage_analysis_handles_malformed_repos(self):
        from github_usage.storage import get_storage_analysis

        api = FakeAPI()
        # One valid repo, one missing owner, one missing name
        repos = [
            {
                "owner": {"login": "octocat"},
                "name": "hello-world",
                "full_name": "octocat/hello-world",
            },
            {"owner": {}, "name": "no-owner"},
            {"owner": {"login": "no-name"}},
            {},
        ]

        result = get_storage_analysis(api, repos)
        # Should only have one result or empty if no storage found, but should not crash
        self.assertIn("repos", result)

    def test_get_storage_analysis_aggregates_artifacts_and_releases(self):
        from github_usage.storage import get_storage_analysis

        api = mock.Mock()
        api.get_all_pages.side_effect = [
            [{"name": "art1", "size_in_bytes": 1024 * 1024 * 1024}],  # 1 GB
            [{"assets": [{"name": "bin", "size": 1024 * 1024 * 1024}]}],  # 1 GB
        ]

        repos = [{"owner": {"login": "octocat"}, "name": "api"}]
        result = get_storage_analysis(api, repos)

        self.assertEqual(len(result["repos"]), 1)
        self.assertEqual(result["repos"][0]["total_storage"], 2.0)
        self.assertEqual(result["repos"][0]["artifact_storage_gb"], 1.0)
        self.assertEqual(result["repos"][0]["release_storage_gb"], 1.0)
        self.assertEqual(len(result["repos"][0]["items"]), 2)

    def test_get_storage_analysis_handles_owner_null(self):
        from github_usage.storage import get_storage_analysis

        api = FakeAPI()
        # owner=None (JSON null) used to crash with
        # AttributeError: 'NoneType' object has no attribute 'get' on the
        # original `repo.get("owner", {}).get("login")` chain. After A1 the
        # `(repo.get("owner") or {}).get("login")` form short-circuits.
        repos = [
            {"owner": None, "name": "x"},
            {"owner": None},
            {"owner": {"login": "octocat"}, "name": "valid", "full_name": "octocat/valid"},
        ]

        # Should not raise; only the valid repo survives.
        result = get_storage_analysis(api, repos)
        # No storage found (FakeAPI returns []), so result may be empty —
        # the key check is that the call returns and contains "repos".
        self.assertIn("repos", result)

    def test_artifact_expiry_and_retention_rollups(self):
        from github_usage.storage import get_storage_analysis

        api = mock.Mock()
        api.get_all_pages.side_effect = [
            [
                {
                    "name": "old",
                    "size_in_bytes": 10 * 1024 * 1024,
                    "created_at": "2026-04-01T00:00:00Z",
                    "expires_at": "2026-06-30T00:00:00Z",
                    "expired": True,
                },
                {
                    "name": "soon",
                    "size_in_bytes": 20 * 1024 * 1024,
                    "created_at": "2026-07-01T00:00:00Z",
                    "expires_at": "2026-08-03T00:00:00Z",
                    "expired": False,
                },
                {
                    "name": "later",
                    "size_in_bytes": 30 * 1024 * 1024,
                    "created_at": "2026-07-10T00:00:00Z",
                    "expires_at": "2026-10-08T00:00:00Z",
                    "expired": False,
                },
            ],
            [],  # releases
        ]
        repos = [
            {
                "owner": {"login": "octocat"},
                "name": "priv",
                "full_name": "octocat/priv",
                "visibility": "private",
            }
        ]
        result = get_storage_analysis(api, repos, reference_date=date(2026, 7, 31))
        repo = result["repos"][0]
        self.assertEqual(repo["artifact_count"], 3)
        self.assertEqual(repo["expired_count"], 1)
        self.assertEqual(repo["expiring_soon_count"], 1)  # soon expires Aug 3
        self.assertEqual(repo["retention_days"], 90)  # Jul 10 → Oct 8
        self.assertEqual(repo["earliest_expiry"], "2026-08-03T00:00:00Z")
        items = {item["name"]: item for item in repo["items"]}
        self.assertTrue(items["old"]["expired"])
        self.assertEqual(items["soon"]["days_to_expiry"], 3)
        self.assertAlmostEqual(repo["artifact_storage_gb"], 60 / 1024)
        self.assertEqual(repo["release_storage_gb"], 0.0)


class ReportStorageTests(unittest.TestCase):
    def test_build_storage_summary_from_actions_split(self):
        from github_usage.report_storage import build_storage_summary

        summary = build_storage_summary(
            {
                "private_storage_gb_hours": 165.29,
                "public_storage_gb_hours": 50.0,
                "unattributed_storage_gb_hours": 0.0,
                "private_storage_avg_mb": 229.0,
                "public_storage_avg_mb": 69.0,
            },
            reference_date=date(2026, 7, 15),
        )
        assert summary is not None
        self.assertEqual(summary["allowance_gb_hours"], 372.0)
        self.assertEqual(summary["private_gb_hours"], 165.29)
        self.assertEqual(summary["retention_default_days"], 90)

    def test_build_storage_summary_absent_without_split(self):
        from github_usage.report_storage import build_storage_summary

        self.assertIsNone(build_storage_summary({"storage_gb_hours": 10.0}))
        self.assertIsNone(build_storage_summary(None))
