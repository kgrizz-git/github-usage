"""Tests for setup_launchd profile-name validation (path-injection guard)."""

from __future__ import annotations

import unittest

from github_usage.setup_launchd import label_for, launch_agent_dest


class ProfileNameValidationTest(unittest.TestCase):
    def test_valid_names_pass_through(self) -> None:
        for name in ("default", "work-2", "team.reports", "a_b"):
            self.assertIn(name, label_for(name))
            self.assertTrue(str(launch_agent_dest(name)).endswith(f"{name}.plist"))

    def test_path_separators_rejected(self) -> None:
        for bad in ("../evil", "a/b", "..", ".", "with space", "semi;colon", ""):
            with self.assertRaises(ValueError):
                label_for(bad)
            with self.assertRaises(ValueError):
                launch_agent_dest(bad)

    def test_dest_stays_in_launch_agents_dir(self) -> None:
        dest = launch_agent_dest("default")
        self.assertEqual(dest.parent.name, "LaunchAgents")


if __name__ == "__main__":
    unittest.main()
