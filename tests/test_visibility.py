"""Tests for repository visibility helpers."""

import unittest

from github_usage.visibility import (
    filter_repos_by_visibility,
    group_by_visibility,
    repo_visibility,
    visibility_group_header,
    visibility_label,
)


class VisibilityHelperTests(unittest.TestCase):
    def test_repo_visibility_prefers_field(self) -> None:
        self.assertEqual(repo_visibility({"visibility": "internal", "private": False}), "internal")

    def test_repo_visibility_falls_back_to_private_bool(self) -> None:
        self.assertEqual(repo_visibility({"private": True}), "private")
        self.assertEqual(repo_visibility({"private": False}), "public")

    def test_group_by_visibility_mixed(self) -> None:
        rows = [
            {"repo": "a", "visibility": "public"},
            {"repo": "b", "visibility": "private"},
            {"repo": "c", "visibility": "internal"},
        ]
        grouped = group_by_visibility(rows)
        self.assertEqual(list(grouped.keys()), ["private", "internal", "public"])

    def test_group_by_visibility_all_public(self) -> None:
        rows = [{"visibility": "public"}, {"visibility": "public"}]
        self.assertEqual(list(group_by_visibility(rows).keys()), ["public"])

    def test_group_by_visibility_empty(self) -> None:
        self.assertEqual(group_by_visibility([]), {})

    def test_group_by_visibility_unknown_value(self) -> None:
        rows = [{"visibility": "public"}, {"visibility": "custom"}]
        grouped = group_by_visibility(rows)
        self.assertEqual(list(grouped.keys()), ["public", "custom"])

    def test_visibility_label_private(self) -> None:
        self.assertEqual(visibility_label("private"), " [private]")

    def test_visibility_label_public(self) -> None:
        self.assertEqual(visibility_label("public"), "")

    def test_visibility_group_header(self) -> None:
        self.assertEqual(visibility_group_header("private"), "Private Repos:")

    def test_filter_repos_by_visibility_only_public(self) -> None:
        repos = [
            {"visibility": "public"},
            {"visibility": "private"},
            {"visibility": "internal"},
        ]
        filtered = filter_repos_by_visibility(repos, only_public=True)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(repo_visibility(filtered[0]), "public")

    def test_filter_repos_by_visibility_only_private_includes_internal(self) -> None:
        repos = [
            {"visibility": "public"},
            {"visibility": "private"},
            {"visibility": "internal"},
        ]
        filtered = filter_repos_by_visibility(repos, only_private=True)
        self.assertEqual({repo_visibility(r) for r in filtered}, {"private", "internal"})

    def test_filter_repos_by_visibility_neither(self) -> None:
        repos = [{"visibility": "public"}, {"visibility": "private"}]
        self.assertEqual(filter_repos_by_visibility(repos), repos)

    def test_filter_repos_by_visibility_uses_private_fallback(self) -> None:
        repos = [{"private": True}, {"private": False}]
        filtered = filter_repos_by_visibility(repos, only_private=True)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(repo_visibility(filtered[0]), "private")


if __name__ == "__main__":
    unittest.main()
