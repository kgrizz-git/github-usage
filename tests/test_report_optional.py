import unittest
from unittest import mock

from github_usage.report_optional import (
    _safe_int_size,
    get_artifact_storage_details,
    get_release_asset_details,
    get_repo_consumers,
)


class _FakeAPI:
    def __init__(self, pages):
        self._pages = pages

    def get_all_pages(self, path, params=None):
        return self._pages.get(path, [])


def _repo(full_name, owner_login="octocat", name="repo"):
    return {
        "full_name": full_name,
        "owner": {"login": owner_login},
        "name": name,
    }


class SafeIntSizeTests(unittest.TestCase):
    def test_parses_numeric_string(self):
        self.assertEqual(_safe_int_size("1024"), 1024)

    def test_parses_int(self):
        self.assertEqual(_safe_int_size(1024), 1024)

    def test_returns_none_for_none(self):
        self.assertIsNone(_safe_int_size(None))

    def test_returns_none_for_non_numeric_string(self):
        self.assertIsNone(_safe_int_size("abc"))

    def test_truncates_float_with_fraction(self):
        # Python's int() truncates a numeric float toward zero; the helper
        # preserves that behaviour rather than treating it as an error.
        self.assertEqual(_safe_int_size(1024.7), 1024)

    def test_returns_none_for_unexpected_type(self):
        self.assertIsNone(_safe_int_size({"unexpected": "type"}))

    def test_safe_int_size_rejects_booleans(self):
        # In Python int(True) == 1; without this guard, a release asset with
        # size: true would be counted as 1 byte instead of skipped.
        self.assertIsNone(_safe_int_size(True))
        self.assertIsNone(_safe_int_size(False))

    def test_safe_int_size_still_parses_zero_and_one(self):
        # The bool guard must not over-reject int 0 or int 1 (since in
        # Python, bool is a subclass of int and the order of checks matters).
        self.assertEqual(_safe_int_size(0), 0)
        self.assertEqual(_safe_int_size(1), 1)


class GetArtifactStorageDetailsTests(unittest.TestCase):
    def test_skips_items_with_non_numeric_size(self):
        api = _FakeAPI(
            {
                "/repos/octocat/repo/actions/artifacts": [
                    {"size_in_bytes": "1024"},
                    {"size_in_bytes": "abc"},
                    {"size_in_bytes": 1024.7},
                    {"size_in_bytes": None},
                    {"size_in_bytes": 256},
                ]
            }
        )
        result = get_artifact_storage_details(api, [_repo("octocat/repo")], max_repos=10)
        # "1024" → 1024, "abc" → skipped, 1024.7 → 1024 (truncated), None →
        # skipped, 256 → 256. Total = 1024 + 1024 + 256 = 2304.
        self.assertEqual(result["top_repos"], [{"repo": "octocat/repo", "artifact_bytes": 2304}])

    def test_omits_repos_with_no_valid_sizes(self):
        api = _FakeAPI(
            {
                "/repos/octocat/repo/actions/artifacts": [
                    {"size_in_bytes": "abc"},
                    {"size_in_bytes": None},
                ]
            }
        )
        result = get_artifact_storage_details(api, [_repo("octocat/repo")], max_repos=10)
        self.assertEqual(result["top_repos"], [])

    def test_handles_empty_artifacts(self):
        api = _FakeAPI({"/repos/octocat/repo/actions/artifacts": []})
        result = get_artifact_storage_details(api, [_repo("octocat/repo")], max_repos=10)
        self.assertEqual(result["top_repos"], [])


class GetReleaseAssetDetailsTests(unittest.TestCase):
    def test_skips_assets_with_non_numeric_size(self):
        api = _FakeAPI(
            {
                "/repos/octocat/repo/releases": [
                    {
                        "assets": [
                            {"size": "1024"},
                            {"size": "bad"},
                            {"size": 2048.5},
                            {"size": None},
                            {"size": 512},
                        ]
                    }
                ]
            }
        )
        result = get_release_asset_details(api, [_repo("octocat/repo")], max_repos=10)
        # "1024" → 1024, "bad" → skipped, 2048.5 → 2048 (truncated), None →
        # skipped, 512 → 512. Total = 1024 + 2048 + 512 = 3584.
        self.assertEqual(
            result["top_repos"], [{"repo": "octocat/repo", "release_asset_bytes": 3584}]
        )

    def test_omits_repos_with_no_valid_asset_sizes(self):
        api = _FakeAPI(
            {
                "/repos/octocat/repo/releases": [
                    {"assets": [{"size": "bad"}, {"size": None}]},
                ]
            }
        )
        result = get_release_asset_details(api, [_repo("octocat/repo")], max_repos=10)
        self.assertEqual(result["top_repos"], [])


class GetRepoConsumersTests(unittest.TestCase):
    def test_returns_sorted_top_consumers_and_skips_runtime_errors(self):
        repo1 = _repo("octocat/repo1", name="repo1")
        repo2 = _repo("octocat/repo2", name="repo2")
        repo3 = _repo("octocat/repo3", name="repo3")
        with mock.patch(
            "github_usage.report_optional.get_actions_per_repo",
            side_effect=[
                (10.0, 0.0, {"sku1": {"grossAmount": 5.0}}),
                RuntimeError("billing unavailable"),
                (30.0, 0.0, {"sku3": {"grossAmount": 12.0}}),
            ],
        ):
            result = get_repo_consumers(mock.Mock(), [repo1, repo2, repo3], limit=2, max_repos=10)
        self.assertEqual(len(result["by_minutes"]), 2)
        self.assertEqual(result["by_minutes"][0]["repo"], "octocat/repo3")
        self.assertEqual(result["by_minutes"][1]["repo"], "octocat/repo1")
        self.assertEqual(result["scanned_repo_count"], 3)

    def test_truncates_repos_above_max(self):
        repos = [_repo(f"octocat/r{i}", name=f"r{i}") for i in range(5)]
        with mock.patch(
            "github_usage.report_optional.get_actions_per_repo",
            return_value=(1.0, 0.0, {"sku": {"grossAmount": 0.0}}),
        ):
            result = get_repo_consumers(mock.Mock(), repos, limit=2, max_repos=2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["scanned_repo_count"], 2)


if __name__ == "__main__":
    unittest.main()
