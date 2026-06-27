"""Tests for setup_config profile loading and writing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from github_usage.setup_config import (
    DEFAULT_PROFILE_NAME,
    SetupPaths,
    email_report_args,
    ensure_profiles,
    find_profile,
    load_config,
    load_report_profiles,
    write_config,
)


class LoadReportProfilesTests(unittest.TestCase):
    def test_legacy_config_yields_default_profile(self):
        data = {
            "email_report": {"max_repos": 50},
            "schedule": {"hour": 8},
            "github_actions": {"cron": "0 8 * * 5"},
        }
        profiles = load_report_profiles(data)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], DEFAULT_PROFILE_NAME)
        self.assertEqual(profiles[0]["email_report"]["max_repos"], 50)
        self.assertEqual(profiles[0]["schedule"]["hour"], 8)

    def test_multi_profile_config(self):
        data = {
            "reports": [
                {
                    "name": "weekly",
                    "target_email": "team@example.com",
                    "email_report": {"include_consumers": True},
                    "schedule": {"weekday": 1},
                    "github_actions": {"cron": "0 9 * * 1"},
                },
                {
                    "name": "monthly",
                    "target_email": "finance@example.com",
                    "email_report": {"max_repos": 200},
                },
            ]
        }
        profiles = load_report_profiles(data)
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0]["name"], "weekly")
        self.assertEqual(profiles[1]["target_email"], "finance@example.com")

    def test_missing_name_raises_key_error(self):
        with self.assertRaises(KeyError):
            load_report_profiles({"reports": [{"email_report": {}}]})

    def test_duplicate_names_raise_value_error(self):
        data = {"reports": [{"name": "dup"}, {"name": "dup"}]}
        with self.assertRaises(ValueError):
            load_report_profiles(data)


class WriteConfigRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_single_profile_writes_legacy_format(self):
        config = load_config(self.paths.config_file)
        write_config(self.paths.config_file, config)
        text = self.paths.config_file.read_text(encoding="utf-8")
        self.assertIn("[email_report]", text)
        self.assertNotIn("[[reports]]", text)

    def test_multi_profile_round_trip(self):
        config = {
            "reports": [
                {
                    "name": "weekly",
                    "target_email": "team@example.com",
                    "target_subject": "Weekly Digest",
                    "email_report": {"warn_over": ["10", "90%"]},
                    "schedule": {"weekday": 1},
                    "github_actions": {"cron": "0 9 * * 1"},
                },
                {
                    "name": "monthly",
                    "target_email": "finance@example.com",
                    "email_report": {"max_repos": 200},
                    "schedule": {"weekday": 2},
                    "github_actions": {"cron": "0 9 1 * *"},
                },
            ]
        }
        config["profiles"] = load_report_profiles(config)
        write_config(self.paths.config_file, config)
        loaded = load_config(self.paths.config_file)
        self.assertEqual(len(loaded["profiles"]), 2)
        self.assertEqual(loaded["profiles"][0]["target_subject"], "Weekly Digest")
        self.assertEqual(loaded["profiles"][1]["email_report"]["max_repos"], 200)

    def test_ensure_profiles_migrates_legacy(self):
        config = {
            "email_report": {"max_repos": 25},
            "schedule": {"hour": 10},
            "github_actions": {"cron": "0 10 * * 1"},
        }
        migrated = ensure_profiles(config)
        self.assertEqual(len(migrated["profiles"]), 1)
        self.assertEqual(migrated["profiles"][0]["name"], DEFAULT_PROFILE_NAME)
        self.assertEqual(migrated["profiles"][0]["email_report"]["max_repos"], 25)


class EmailReportArgsTests(unittest.TestCase):
    def test_includes_to_and_subject_when_set(self):
        config = {
            "profiles": [
                {
                    "name": "weekly",
                    "target_email": "team@example.com",
                    "target_subject": "Weekly Report",
                    "email_report": {},
                    "schedule": {},
                    "github_actions": {},
                }
            ]
        }
        args = email_report_args(config, "weekly")
        self.assertIn("--to", args)
        self.assertIn("team@example.com", args)
        self.assertIn("--subject", args)
        self.assertIn("Weekly Report", args)

    def test_find_profile_raises_for_unknown(self):
        config = load_config(Path("/nonexistent"))
        with self.assertRaises(KeyError):
            find_profile(config, "missing")
