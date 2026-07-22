"""Renderer tests for visibility-aware Actions output."""

from __future__ import annotations

import contextlib
import io
import unittest

from github_usage.report_actions import (
    render_actions_os_breakdown,
    render_actions_top_consumers,
    render_repo_actions_table,
)


class RenderActionsVisibilityTests(unittest.TestCase):
    def test_render_repo_actions_table_groups_by_visibility(self) -> None:
        repo_actions = [
            {
                "repo": "o/private",
                "minutes": 10.0,
                "storage_gb_hours": 0.1,
                "avg_mb": 1.0,
                "gross": 1.0,
                "visibility": "private",
            },
            {
                "repo": "o/public",
                "minutes": 20.0,
                "storage_gb_hours": 0.2,
                "avg_mb": 2.0,
                "gross": 2.0,
                "visibility": "public",
            },
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render_repo_actions_table(repo_actions)
        out = buf.getvalue()
        self.assertIn("Private Repos:", out)
        self.assertIn("Public Repos:", out)
        self.assertIn("SUBTOTAL", out)
        self.assertIn("TOTAL", out)

    def test_render_repo_actions_table_single_visibility(self) -> None:
        repo_actions = [
            {
                "repo": "o/public",
                "minutes": 20.0,
                "storage_gb_hours": 0.2,
                "avg_mb": 2.0,
                "gross": 2.0,
                "visibility": "public",
            },
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render_repo_actions_table(repo_actions)
        out = buf.getvalue()
        self.assertNotIn("Private Repos:", out)
        self.assertNotIn("SUBTOTAL", out)
        self.assertIn("TOTAL", out)

    def test_render_actions_top_consumers_annotates_visibility(self) -> None:
        repo_actions = [
            {
                "repo": "o/private",
                "minutes": 10.0,
                "avg_mb": 1.0,
                "visibility": "private",
            },
            {
                "repo": "o/public",
                "minutes": 5.0,
                "avg_mb": 1.0,
                "visibility": "public",
            },
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render_actions_top_consumers(repo_actions)
        out = buf.getvalue()
        self.assertIn("o/private [private]", out)
        self.assertNotIn("o/public [", out)

    def test_render_actions_os_breakdown_annotates_visibility(self) -> None:
        breakdown = {
            "found": True,
            "repos": [
                {
                    "name": "o/private",
                    "visibility": "private",
                    "os_minutes": {"UBUNTU": 1.0, "WINDOWS": 0.0, "MACOS": 0.0},
                }
            ],
            "totals": {"UBUNTU": 60000, "WINDOWS": 0, "MACOS": 0},
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render_actions_os_breakdown(breakdown)
        self.assertIn("o/private [private]", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
