"""Tests for guided setup (./start.sh setup / github-usage setup)."""

from __future__ import annotations

import io
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
from github_usage.setup_wizard import (
    _MENU_OPTIONS,
    _REINSTALL_REMINDER,
    _full_setup,
    _github_actions_only,
    _schedule_only,
    _wrap_description,
    run_setup,
)


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


class ScheduleMenuOptionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)
        write_config(self.paths.config_file, load_config(self.paths.config_file))

    def test_menu_options_numbering_and_labels(self):
        expected = [
            ("1", "Recommended full setup"),
            ("2", "Local email secrets only"),
            ("3", "Report options only"),
            ("4", "Report schedule only"),
            ("5", "GitHub Actions workflow"),
            ("6", "macOS launchd schedule"),
            ("7", "GitHub Actions secrets"),
            ("8", "Developer security hooks"),
            ("9", "Verify configuration"),
            ("0", "Show status"),
        ]
        self.assertEqual(len(_MENU_OPTIONS), 10)
        for index, (key, label) in enumerate(expected):
            self.assertEqual(_MENU_OPTIONS[index][0], key)
            self.assertEqual(_MENU_OPTIONS[index][1], label)

    def test_default_menu_option_is_full_setup(self):
        full_setup = mock.Mock(return_value=0)
        patched_options = [
            (key, label, desc, full_setup if key == "1" else handler)
            for key, label, desc, handler in _MENU_OPTIONS
        ]
        with (
            mock.patch("builtins.input", return_value=""),
            mock.patch("github_usage.setup_wizard._MENU_OPTIONS", patched_options),
            mock.patch("github_usage.setup_wizard.sys.stdin.isatty", return_value=True),
        ):
            code = run_setup(["--root", str(self.paths.root)])
        self.assertEqual(code, 0)
        full_setup.assert_called_once()

    def test_schedule_only_regenerates_plist_and_prints_reminder_when_installed(self):
        with (
            mock.patch("github_usage.setup_wizard._configure_schedule") as schedule,
            mock.patch("github_usage.setup_wizard.generate_plist") as plist,
            mock.patch(
                "github_usage.setup_wizard.launch_agent_status",
                return_value="installed",
            ),
            mock.patch("github_usage.setup_wizard.sys.platform", "darwin"),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            plist.return_value = self.paths.launchd_plist
            code = _schedule_only(self.paths)
        self.assertEqual(code, 0)
        schedule.assert_called_once_with(self.paths)
        plist.assert_called_once_with(self.paths)
        output = stdout.getvalue()
        self.assertIn("Generated", output)
        self.assertIn(_REINSTALL_REMINDER, output)
        self.assertEqual(output.count(_REINSTALL_REMINDER), 1)

    def test_schedule_only_skips_reminder_when_not_installed(self):
        with (
            mock.patch("github_usage.setup_wizard._configure_schedule"),
            mock.patch("github_usage.setup_wizard.generate_plist") as plist,
            mock.patch(
                "github_usage.setup_wizard.launch_agent_status",
                return_value="not installed",
            ),
            mock.patch("github_usage.setup_wizard.sys.platform", "darwin"),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            plist.return_value = self.paths.launchd_plist
            code = _schedule_only(self.paths)
        self.assertEqual(code, 0)
        plist.assert_called_once_with(self.paths)
        self.assertNotIn(_REINSTALL_REMINDER, stdout.getvalue())

    def test_schedule_only_skips_reminder_on_non_macos(self):
        with (
            mock.patch("github_usage.setup_wizard._configure_schedule"),
            mock.patch("github_usage.setup_wizard.generate_plist") as plist,
            mock.patch(
                "github_usage.setup_wizard.launch_agent_status",
                return_value="installed",
            ),
            mock.patch("github_usage.setup_wizard.sys.platform", "linux"),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            plist.return_value = self.paths.launchd_plist
            code = _schedule_only(self.paths)
        self.assertEqual(code, 0)
        plist.assert_called_once_with(self.paths)
        self.assertNotIn(_REINSTALL_REMINDER, stdout.getvalue())

    def test_schedule_menu_option_dispatches_option_4(self):
        schedule_only = mock.Mock(return_value=0)
        patched_options = [
            (key, label, desc, schedule_only if key == "4" else handler)
            for key, label, desc, handler in _MENU_OPTIONS
        ]
        with (
            mock.patch("builtins.input", return_value="4"),
            mock.patch("github_usage.setup_wizard._MENU_OPTIONS", patched_options),
            mock.patch("github_usage.setup_wizard.sys.stdin.isatty", return_value=True),
        ):
            code = run_setup(["--root", str(self.paths.root)])
        self.assertEqual(code, 0)
        schedule_only.assert_called_once()

    def test_launchd_menu_option_dispatches_at_key_6(self):
        launchd = mock.Mock(return_value=0)
        patched_options = [
            (key, label, desc, launchd if key == "6" else handler)
            for key, label, desc, handler in _MENU_OPTIONS
        ]
        with (
            mock.patch("builtins.input", return_value="6"),
            mock.patch("github_usage.setup_wizard._MENU_OPTIONS", patched_options),
            mock.patch("github_usage.setup_wizard.sys.stdin.isatty", return_value=True),
        ):
            code = run_setup(["--root", str(self.paths.root)])
        self.assertEqual(code, 0)
        launchd.assert_called_once()

    def test_github_actions_menu_option_dispatches_at_key_5(self):
        gh_actions = mock.Mock(return_value=0)
        patched_options = [
            (key, label, desc, gh_actions if key == "5" else handler)
            for key, label, desc, handler in _MENU_OPTIONS
        ]
        with (
            mock.patch("builtins.input", return_value="5"),
            mock.patch("github_usage.setup_wizard._MENU_OPTIONS", patched_options),
            mock.patch("github_usage.setup_wizard.sys.stdin.isatty", return_value=True),
        ):
            code = run_setup(["--root", str(self.paths.root)])
        self.assertEqual(code, 0)
        gh_actions.assert_called_once()

    def test_status_menu_option_dispatches_at_key_0(self):
        status = mock.Mock(return_value=0)
        patched_options = [
            (key, label, desc, status if key == "0" else handler)
            for key, label, desc, handler in _MENU_OPTIONS
        ]
        with (
            mock.patch("builtins.input", return_value="0"),
            mock.patch("github_usage.setup_wizard._MENU_OPTIONS", patched_options),
            mock.patch("github_usage.setup_wizard.sys.stdin.isatty", return_value=True),
        ):
            code = run_setup(["--root", str(self.paths.root)])
        self.assertEqual(code, 0)
        status.assert_called_once()


class FullSetupPlistSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)
        write_config(self.paths.config_file, load_config(self.paths.config_file))

    def test_full_setup_regenerates_plist_after_schedule(self):
        order: list[str] = []

        def record_schedule(_paths):
            order.append("schedule")

        def record_plist(_paths):
            order.append("plist")
            return self.paths.launchd_plist

        def record_verify(_paths):
            order.append("verify")
            return 0

        with (
            mock.patch(
                "github_usage.setup_wizard._configure_env_secrets",
                side_effect=lambda _p: order.append("secrets"),
            ),
            mock.patch(
                "github_usage.setup_wizard._configure_email_options",
                side_effect=lambda _p: order.append("options"),
            ),
            mock.patch(
                "github_usage.setup_wizard._configure_schedule", side_effect=record_schedule
            ),
            mock.patch(
                "github_usage.setup_wizard._configure_github_actions",
                side_effect=lambda _p: order.append("github_actions"),
            ),
            mock.patch(
                "github_usage.setup_wizard._render_and_offer_commit",
                side_effect=lambda _p: order.append("render"),
            ),
            mock.patch(
                "github_usage.setup_wizard.generate_plist", side_effect=record_plist
            ) as plist,
            mock.patch("github_usage.setup_wizard._verify_setup", side_effect=record_verify),
            mock.patch("github_usage.setup_wizard._prompt_yes_no", return_value=False),
            mock.patch("builtins.print"),
        ):
            code = _full_setup(self.paths)
        self.assertEqual(code, 0)
        plist.assert_called_once()
        self.assertLess(order.index("schedule"), order.index("github_actions"))
        self.assertLess(order.index("github_actions"), order.index("plist"))
        self.assertLess(order.index("plist"), order.index("verify"))

    def test_full_setup_regenerates_plist_even_when_verify_fails(self):
        with (
            mock.patch("github_usage.setup_wizard._configure_env_secrets"),
            mock.patch("github_usage.setup_wizard._configure_email_options"),
            mock.patch("github_usage.setup_wizard._configure_schedule"),
            mock.patch("github_usage.setup_wizard._configure_github_actions"),
            mock.patch("github_usage.setup_wizard._render_and_offer_commit"),
            mock.patch("github_usage.setup_wizard.generate_plist") as plist,
            mock.patch("github_usage.setup_wizard._verify_setup", return_value=1),
            mock.patch("github_usage.setup_wizard._prompt_yes_no", return_value=False),
            mock.patch("builtins.print"),
        ):
            code = _full_setup(self.paths)
        self.assertEqual(code, 1)
        plist.assert_called_once()


class GitHubActionsWizardTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)
        write_config(self.paths.config_file, load_config(self.paths.config_file))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_configure_github_actions_writes_github_actions_block(self):
        inputs = iter(["0 14 * * 5", "n", "n", "n"])
        with (
            mock.patch("builtins.input", side_effect=lambda _: next(inputs)),
            mock.patch("builtins.print"),
        ):
            from github_usage.setup_wizard import _configure_github_actions

            _configure_github_actions(self.paths)
        config = load_config(self.paths.config_file)
        self.assertEqual(config["github_actions"]["cron"], "0 14 * * 5")
        self.assertFalse(config["github_actions"]["include_consumers"])

    def test_configure_github_actions_reprompts_on_invalid_cron(self):
        inputs = iter(["bad cron", "0 9 * * 1", "n", "n", "n"])
        with (
            mock.patch("builtins.input", side_effect=lambda _: next(inputs)),
            mock.patch("builtins.print"),
        ):
            from github_usage.setup_wizard import _configure_github_actions

            _configure_github_actions(self.paths)
        config = load_config(self.paths.config_file)
        self.assertEqual(config["github_actions"]["cron"], "0 9 * * 1")

    def test_github_actions_only_calls_configure_and_render(self):
        with (
            mock.patch("github_usage.setup_wizard._configure_github_actions") as cfg,
            mock.patch("github_usage.setup_wizard._render_and_offer_commit") as render,
        ):
            code = _github_actions_only(self.paths)
        self.assertEqual(code, 0)
        cfg.assert_called_once_with(self.paths)
        render.assert_called_once_with(self.paths)

    def test_full_setup_calls_render_workflow(self):
        with (
            mock.patch("github_usage.setup_wizard._configure_env_secrets"),
            mock.patch("github_usage.setup_wizard._configure_email_options"),
            mock.patch("github_usage.setup_wizard._configure_schedule"),
            mock.patch("github_usage.setup_wizard._configure_github_actions"),
            mock.patch("github_usage.setup_wizard._render_and_offer_commit") as render,
            mock.patch("github_usage.setup_wizard.generate_plist") as plist,
            mock.patch("github_usage.setup_wizard._verify_setup", return_value=0),
            mock.patch("github_usage.setup_wizard._prompt_yes_no", return_value=False),
            mock.patch("builtins.print"),
        ):
            plist.return_value = self.paths.launchd_plist
            _full_setup(self.paths)
        render.assert_called_once_with(self.paths)


if __name__ == "__main__":
    unittest.main()
