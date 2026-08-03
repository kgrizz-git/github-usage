"""Tests for shared repo consumer ranking helpers."""

from __future__ import annotations

import unittest

from github_usage.repo_consumers import build_consumer_rankings, private_list_is_redundant


def _row(
    repo: str,
    *,
    minutes: float = 0.0,
    gross: float = 0.0,
    storage_avg_mb: float = 0.0,
    visibility: str = "public",
) -> dict:
    return {
        "repo": repo,
        "minutes": minutes,
        "gross": gross,
        "storage_avg_mb": storage_avg_mb,
        "visibility": visibility,
    }


class BuildConsumerRankingsTests(unittest.TestCase):
    def test_ranks_by_minutes_cost_and_storage(self) -> None:
        rows = [
            _row("octocat/a", minutes=10.0, gross=1.0, storage_avg_mb=5.0),
            _row("octocat/b", minutes=50.0, gross=3.0, storage_avg_mb=20.0),
            _row("octocat/c", minutes=30.0, gross=2.0, storage_avg_mb=10.0),
        ]
        rankings = build_consumer_rankings(rows, limit=2)
        self.assertEqual([r["repo"] for r in rankings["by_minutes"]], ["octocat/b", "octocat/c"])
        self.assertEqual([r["repo"] for r in rankings["by_cost"]], ["octocat/b", "octocat/c"])
        self.assertEqual(
            [r["repo"] for r in rankings["by_storage"]],
            ["octocat/b", "octocat/c"],
        )
        self.assertEqual(rankings["by_storage"][0]["storage_avg_mb"], 20.0)

    def test_internal_folds_into_private_public_excluded_from_private_keys(self) -> None:
        rows = [
            _row("octocat/private", minutes=40.0, storage_avg_mb=8.0, visibility="private"),
            _row("octocat/internal", minutes=30.0, storage_avg_mb=6.0, visibility="internal"),
            _row("octocat/public", minutes=100.0, storage_avg_mb=50.0, visibility="public"),
        ]
        rankings = build_consumer_rankings(rows, limit=5)
        private_minutes = [r["repo"] for r in rankings["by_minutes_private"]]
        private_storage = [r["repo"] for r in rankings["by_storage_private"]]
        self.assertEqual(private_minutes, ["octocat/private", "octocat/internal"])
        self.assertEqual(private_storage, ["octocat/private", "octocat/internal"])
        self.assertNotIn("octocat/public", private_minutes)
        self.assertNotIn("octocat/public", private_storage)

    def test_empty_private_returns_empty_lists_with_keys_present(self) -> None:
        rows = [
            _row("octocat/public", minutes=10.0, storage_avg_mb=1.0, visibility="public"),
        ]
        rankings = build_consumer_rankings(rows, limit=3)
        self.assertEqual(rankings["by_minutes_private"], [])
        self.assertEqual(rankings["by_storage_private"], [])
        self.assertIn("by_minutes_private", rankings)
        self.assertIn("by_storage_private", rankings)

    def test_limit_applies_per_ranking(self) -> None:
        rows = [
            _row("octocat/a", minutes=10.0, storage_avg_mb=1.0, visibility="private"),
            _row("octocat/b", minutes=20.0, storage_avg_mb=2.0, visibility="private"),
            _row("octocat/c", minutes=30.0, storage_avg_mb=3.0, visibility="private"),
        ]
        rankings = build_consumer_rankings(rows, limit=2)
        self.assertEqual(len(rankings["by_minutes"]), 2)
        self.assertEqual(len(rankings["by_minutes_private"]), 2)
        self.assertEqual(len(rankings["by_storage_private"]), 2)

    def test_tie_break_on_repo_name_for_new_rankings(self) -> None:
        rows = [
            _row("octocat/z", minutes=10.0, storage_avg_mb=10.0, visibility="private"),
            _row("octocat/a", minutes=10.0, storage_avg_mb=10.0, visibility="private"),
        ]
        rankings = build_consumer_rankings(rows, limit=5)
        self.assertEqual(
            [r["repo"] for r in rankings["by_storage"]],
            ["octocat/a", "octocat/z"],
        )
        self.assertEqual(
            [r["repo"] for r in rankings["by_storage_private"]],
            ["octocat/a", "octocat/z"],
        )

    def test_does_not_mutate_input_rows(self) -> None:
        rows = [_row("octocat/a", minutes=5.0, storage_avg_mb=1.0)]
        original = [dict(row) for row in rows]
        build_consumer_rankings(rows, limit=1)
        self.assertEqual(rows, original)


class PrivateListIsRedundantTests(unittest.TestCase):
    def test_true_when_private_list_empty(self) -> None:
        combined = [_row("octocat/a", visibility="private")]
        self.assertTrue(private_list_is_redundant(combined, []))

    def test_true_when_combined_all_private_and_lengths_match(self) -> None:
        combined = [
            _row("octocat/a", visibility="private"),
            _row("octocat/b", visibility="internal"),
        ]
        private = [
            _row("octocat/a", visibility="private"),
            _row("octocat/b", visibility="internal"),
        ]
        self.assertTrue(private_list_is_redundant(combined, private))

    def test_false_when_combined_has_public_repo(self) -> None:
        combined = [
            _row("octocat/a", visibility="private"),
            _row("octocat/b", visibility="public"),
        ]
        private = [_row("octocat/a", visibility="private")]
        self.assertFalse(private_list_is_redundant(combined, private))

    def test_false_when_private_longer_than_combined_all_private(self) -> None:
        """Top-5-all-private combined must not suppress a longer private Top-10."""
        combined = [
            _row("octocat/a", visibility="private"),
            _row("octocat/b", visibility="private"),
            _row("octocat/c", visibility="private"),
            _row("octocat/d", visibility="private"),
            _row("octocat/e", visibility="private"),
        ]
        private = combined + [_row(f"octocat/extra{i}", visibility="private") for i in range(5)]
        self.assertFalse(private_list_is_redundant(combined, private))


if __name__ == "__main__":
    unittest.main()
