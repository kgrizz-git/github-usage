"""Tests for guided setup (./setup.sh / github-usage setup)."""

from __future__ import annotations

import plistlib
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage.setup_config import (
    SetupPaths,
    email_report_args,
    is_minimally_configured,
    load_config,
    mask_secret,
    read_env_file,
    status_lines,
    write_config,
    write_env_file,
)
from github_usage.setup_launchd import generate_plist
from github_usage.setup_wizard import _wrap_description, run_setup


class SetupConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)

    def test_write_env_file_sets_restrictive_permissions(self):
        write_env_file(
            self.paths.env_file,
            {
                "GITHUB_TOKEN": "ghp_secretvalue123",
                "RESEND_API_KEY": "re_key",
                "REPORT_EMAIL": "user@example.com",
                "RESEND_FROM": "reports@example.com",
            },
        )
        mode = self.paths.env_file.stat().st_mode
        self.assertEqual(mode & stat.S_IRWXG, 0)
        self.assertEqual(mode & stat.S_IRWXO, 0)
        values = read_env_file(self.paths.env_file)
        self.assertEqual(values["GITHUB_TOKEN"], "ghp_secretvalue123")
        self.assertEqual(values["REPORT_EMAIL"], "user@example.com")

    def test_write_and_load_config_round_trip(self):
        config = {
            "email_report": {
                "include_consumers": True,
                "max_repos": 50,
                "warn_over": ["10", "90%"],
            },
            "schedule": {"weekday": 2, "hour": 8, "minute": 30},
        }
        write_config(self.paths.config_file, config)
        loaded = load_config(self.paths.config_file)
        self.assertTrue(loaded["email_report"]["include_consumers"])
        self.assertEqual(loaded["email_report"]["max_repos"], 50)
        self.assertEqual(loaded["schedule"]["hour"], 8)

    def test_email_report_args_from_config(self):
        config = {
            "email_report": {
                "include_consumers": True,
                "include_artifact_storage": False,
                "include_release_assets": True,
                "max_repos": 25,
                "warn_over": ["25"],
                "skip_copilot": True,
            }
        }
        args = email_report_args(config)
        self.assertIn("--include-consumers", args)
        self.assertIn("--include-release-assets", args)
        self.assertIn("--yes-include-release-assets", args)
        self.assertIn("--max-repos", args)
        self.assertIn("25", args)
        self.assertIn("--skip-copilot", args)

    def test_mask_secret_never_returns_full_value(self):
        secret = "ghp_abcdefghijklmnopqrstuvwxyz"
        masked = mask_secret(secret)
        self.assertNotIn(secret, masked)
        self.assertNotEqual(masked, secret)

    def test_status_lines_do_not_include_secret_values(self):
        write_env_file(
            self.paths.env_file,
            {
                "GITHUB_TOKEN": "ghp_topsecretvalue",
                "RESEND_API_KEY": "re_topsecret",
                "REPORT_EMAIL": "user@example.com",
                "RESEND_FROM": "reports@example.com",
            },
        )
        write_config(self.paths.config_file, load_config(self.paths.config_file))
        output = "\n".join(status_lines(self.paths))
        self.assertNotIn("ghp_topsecretvalue", output)
        self.assertNotIn("re_topsecret", output)
        self.assertIn("GITHUB_TOKEN:", output)

    def test_is_minimally_configured(self):
        self.assertFalse(is_minimally_configured(self.paths))
        write_config(self.paths.config_file, load_config(self.paths.config_file))
        write_env_file(
            self.paths.env_file,
            {
                "GITHUB_TOKEN": "ghp_x",
                "RESEND_API_KEY": "re_x",
                "REPORT_EMAIL": "a@b.com",
                "RESEND_FROM": "r@b.com",
            },
        )
        self.assertTrue(is_minimally_configured(self.paths))


class SetupLaunchdTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "send-email-report.sh").write_text("#!/bin/sh\n")
        write_config(self.paths.config_file, load_config(self.paths.config_file))

    def test_generate_plist_uses_repo_path_and_schedule(self):
        plist_path = generate_plist(self.paths)
        payload = plistlib.loads(plist_path.read_bytes())
        self.assertEqual(payload["Label"], "com.github.github-usage.email-report")
        self.assertIn("send-email-report.sh", payload["ProgramArguments"][0])
        self.assertEqual(payload["WorkingDirectory"], str(self.root.resolve()))
        interval = payload["StartCalendarInterval"]
        self.assertEqual(interval["Weekday"], 1)
        self.assertEqual(interval["Hour"], 9)
        self.assertEqual(interval["Minute"], 0)


class SetupWizardCliTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)
        write_config(self.paths.config_file, load_config(self.paths.config_file))

    def test_print_args_emits_cli_flags(self):
        write_config(
            self.paths.config_file,
            {
                "email_report": {"include_consumers": True, "max_repos": 10},
                "schedule": {"weekday": 1, "hour": 9, "minute": 0},
            },
        )
        with mock.patch("sys.stdout") as stdout:
            code = run_setup(["--print-args", "--root", str(self.root)])
        self.assertEqual(code, 0)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn("--include-consumers", output)
        self.assertIn("--max-repos", output)

    def test_status_exits_nonzero_when_unconfigured(self):
        with mock.patch("builtins.print"):
            code = run_setup(["--status", "--root", str(self.root)])
        self.assertEqual(code, 1)

    def test_verify_requires_config(self):
        empty_root = Path(self.tmpdir) / "empty"
        empty_root.mkdir()
        with mock.patch("builtins.print"):
            code = run_setup(["--verify", "--root", str(empty_root)])
        self.assertEqual(code, 1)


class GitignoreSetupTests(unittest.TestCase):
    def test_gitignore_covers_local_setup_artifacts(self):
        gitignore = Path(".gitignore").read_text()
        self.assertIn(".github-usage/", gitignore)
        self.assertIn(".env.email-report", gitignore)


class MenuDescriptionTests(unittest.TestCase):
    def test_wrap_description_respects_width(self):
        text = (
            "Walk through every step: local secrets, report options, schedule, "
            "verification, and optionally install launchd, CI secrets, and dev hooks."
        )
        for line in _wrap_description(text, width=40):
            self.assertLessEqual(len(line), 40)

    def test_wrap_description_preserves_all_words(self):
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        joined = " ".join(_wrap_description(text, width=20))
        self.assertEqual(joined, text)

    def test_wrap_description_handles_short_text(self):
        self.assertEqual(_wrap_description("short", width=40), ["short"])

    def test_wrap_description_handles_empty(self):
        self.assertEqual(_wrap_description("", width=40), [""])


if __name__ == "__main__":
    unittest.main()
