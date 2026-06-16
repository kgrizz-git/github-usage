import unittest
from unittest import mock


class FakeAPI:
    def get_all_pages(self, path, params=None):
        return []


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
