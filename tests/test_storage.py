import unittest
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
