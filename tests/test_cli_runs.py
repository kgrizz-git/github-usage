"""Tests for the ``github-usage runs`` subcommand (``github_usage.cli_runs``).

Covers the offline local-config view (``list_local_runs``), cron extraction,
owner/repo resolution, the ``--api`` enrichment path (fully mocked — no live network
calls), error handling, and stdout formatting in text and JSON modes.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from github_usage import cli_runs
from github_usage.setup_config import SetupPaths, load_config


class _Args:
    """Lightweight stand-in for the parsed ``runs`` argparse namespace."""

    def __init__(self, *, profile=None, json=False, api=False, owner=None, repo=None):
        self.profile = profile
        self.json = json
        self.api = api
        self.owner = owner
        self.repo = repo


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


MULTI_PROFILE_CONFIG = """
[[reports]]
name = "default"
[reports.schedule]
weekday = 1
hour = 9
minute = 0
[reports.github_actions]
cron = "0 9 * * 1"

[[reports]]
name = "weekly"
[reports.schedule]
weekday = 5
hour = 8
minute = 30
[reports.github_actions]
cron = "0 8 * * 5"
"""


class ListLocalRunsTests(unittest.TestCase):
    """Offline ``list_local_runs`` behavior with various config shapes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.paths = SetupPaths.from_root(self.root)
        self.addCleanup(self._tmp.cleanup)
        # Isolate launchd checks from the host so results are deterministic.
        missing = self.root / "LaunchAgents"
        self._patches = [
            mock.patch.object(
                cli_runs, "launch_agent_dest", lambda name: missing / f"{name}.plist"
            ),
            mock.patch.object(
                cli_runs, "legacy_launch_agent_dest", lambda: missing / "legacy.plist"
            ),
        ]
        for patcher in self._patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_default_synthetic_config_non_macos(self):
        """No config.toml yields the synthetic default profile; launchd unsupported off-mac."""
        config = load_config(self.paths.config_file)
        with mock.patch.object(cli_runs.sys, "platform", "linux"):
            rows = cli_runs.list_local_runs(config, self.paths)
        self.assertEqual(len(rows), 2)
        launchd, ga = rows
        self.assertEqual(launchd["source"], "launchd")
        self.assertEqual(launchd["active"], "unsupported")
        self.assertEqual(ga["source"], "github_actions")
        # No workflow file on disk -> inactive, cron falls back to the config default.
        self.assertEqual(ga["active"], "inactive")
        self.assertEqual(ga["schedule"], "0 9 * * 1")

    def test_multi_profile_reports_config(self):
        """A two-profile reports config yields a launchd + github_actions row per profile."""
        _write(self.paths.config_file, MULTI_PROFILE_CONFIG)
        config = load_config(self.paths.config_file)
        with mock.patch.object(cli_runs.sys, "platform", "linux"):
            rows = cli_runs.list_local_runs(config, self.paths)
        self.assertEqual(len(rows), 4)
        names = {row["profile"] for row in rows}
        self.assertEqual(names, {"default", "weekly"})

    def test_profile_filter_restricts_and_skips_stray(self):
        """--profile restricts to one profile and suppresses stray-workflow detection."""
        _write(self.paths.config_file, MULTI_PROFILE_CONFIG)
        _write(self.root / ".github/workflows/email-report-orphan.yml", "on:\n  schedule:\n")
        config = load_config(self.paths.config_file)
        with mock.patch.object(cli_runs.sys, "platform", "linux"):
            rows = cli_runs.list_local_runs(config, self.paths, profile_filter="weekly")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["profile"] == "weekly" for row in rows))
        self.assertNotIn(cli_runs.UNCONFIGURED, {row["profile"] for row in rows})

    def test_profile_filter_unknown_raises_keyerror(self):
        """An unknown --profile name propagates KeyError from find_profile."""
        config = load_config(self.paths.config_file)
        with self.assertRaises(KeyError):
            cli_runs.list_local_runs(config, self.paths, profile_filter="nope")

    def test_stray_workflow_dedup(self):
        """The configured workflow is not flagged stray; an orphan file is."""
        config = load_config(self.paths.config_file)  # synthetic default
        _write(self.root / ".github/workflows/email-report.yml", "on:\n  schedule:\n")
        _write(
            self.root / ".github/workflows/email-report-orphan.yml",
            "on:\n  schedule:\n    - cron: '0 0 * * 0'\n",
        )
        with mock.patch.object(cli_runs.sys, "platform", "linux"):
            rows = cli_runs.list_local_runs(config, self.paths)
        stray = [row for row in rows if row["profile"] == cli_runs.UNCONFIGURED]
        self.assertEqual(len(stray), 1)
        self.assertEqual(stray[0]["workflow_file"], ".github/workflows/email-report-orphan.yml")
        self.assertEqual(stray[0]["schedule"], "0 0 * * 0")
        # The configured default workflow must NOT appear as stray.
        self.assertEqual(
            [r for r in rows if r["workflow_file"] == ".github/workflows/email-report.yml"][0][
                "profile"
            ],
            "default",
        )

    def test_launchd_active_on_macos_when_installed(self):
        """On macOS an installed plist marks the launchd row active."""
        config = load_config(self.paths.config_file)
        installed = self.root / "LaunchAgents" / "default.plist"
        _write(installed, "<plist/>")
        with mock.patch.object(cli_runs.sys, "platform", "darwin"):
            rows = cli_runs.list_local_runs(config, self.paths)
        launchd = next(r for r in rows if r["source"] == "launchd")
        self.assertEqual(launchd["active"], "active")

    def test_generated_but_not_installed_note(self):
        """A generated (but not installed) plist surfaces an explanatory note."""
        config = load_config(self.paths.config_file)
        _write(self.paths.launchd_plist_for("default"), "<plist/>")
        with mock.patch.object(cli_runs.sys, "platform", "darwin"):
            rows = cli_runs.list_local_runs(config, self.paths)
        launchd = next(r for r in rows if r["source"] == "launchd")
        self.assertEqual(launchd["active"], "inactive")
        self.assertEqual(launchd["notes"], "plist generated but not installed")

    def test_legacy_plist_emits_separate_row(self):
        """A present legacy plist is reported as its own row on macOS."""
        config = load_config(self.paths.config_file)
        _write(self.root / "LaunchAgents" / "legacy.plist", "<plist/>")
        with mock.patch.object(cli_runs.sys, "platform", "darwin"):
            rows = cli_runs.list_local_runs(config, self.paths)
        legacy = [r for r in rows if r["profile"] == "(legacy)"]
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0]["active"], "active")


class CronExtractionTests(unittest.TestCase):
    """``extract_first_cron_from_workflow`` quote handling and fallback."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_single_quoted_cron(self):
        wf = self.root / "wf.yml"
        _write(wf, "on:\n  schedule:\n    - cron: '0 9 * * 1'\n")
        self.assertEqual(cli_runs.extract_first_cron_from_workflow(wf), "0 9 * * 1")

    def test_double_quoted_cron(self):
        wf = self.root / "wf.yml"
        _write(wf, 'on:\n  schedule:\n    - cron: "23 9 * * 1"\n')
        self.assertEqual(cli_runs.extract_first_cron_from_workflow(wf), "23 9 * * 1")

    def test_unquoted_cron(self):
        wf = self.root / "wf.yml"
        _write(wf, "on:\n  schedule:\n    - cron: 5 4 * * 0\n")
        self.assertEqual(cli_runs.extract_first_cron_from_workflow(wf), "5 4 * * 0")

    def test_missing_file_returns_fallback(self):
        self.assertEqual(
            cli_runs.extract_first_cron_from_workflow(
                self.root / "absent.yml", fallback="1 2 3 4 5"
            ),
            "1 2 3 4 5",
        )

    def test_no_cron_line_returns_fallback(self):
        wf = self.root / "wf.yml"
        _write(wf, "on:\n  push:\n")
        self.assertIsNone(cli_runs.extract_first_cron_from_workflow(wf))


class ResolveOwnerRepoTests(unittest.TestCase):
    """``_resolve_owner_repo`` URL parsing and override behavior."""

    def _resolve_with_url(self, url: str):
        def fake_run(*_a, **_k):
            return types.SimpleNamespace(returncode=0, stdout=url + "\n")

        with mock.patch.object(cli_runs.subprocess, "run", side_effect=fake_run):
            return cli_runs._resolve_owner_repo(_Args())

    def test_https_with_git_suffix(self):
        self.assertEqual(
            self._resolve_with_url("https://github.com/owner/repo.git"), ("owner", "repo")
        )

    def test_ssh_scp_form(self):
        self.assertEqual(self._resolve_with_url("git@github.com:owner/repo.git"), ("owner", "repo"))

    def test_ssh_url_form(self):
        self.assertEqual(
            self._resolve_with_url("ssh://git@github.com/owner/repo"), ("owner", "repo")
        )

    def test_https_without_git_suffix(self):
        self.assertEqual(self._resolve_with_url("https://github.com/owner/repo"), ("owner", "repo"))

    def test_repo_name_with_dots(self):
        self.assertEqual(
            self._resolve_with_url("https://github.com/owner/my.repo.git"), ("owner", "my.repo")
        )

    def test_overrides_bypass_git(self):
        run = mock.MagicMock()
        with mock.patch.object(cli_runs.subprocess, "run", run):
            owner, repo = cli_runs._resolve_owner_repo(_Args(owner="o", repo="r"))
        self.assertEqual((owner, repo), ("o", "r"))
        run.assert_not_called()

    def test_unresolvable_raises(self):
        def fake_run(*_a, **_k):
            return types.SimpleNamespace(returncode=1, stdout="")

        with (
            mock.patch.object(cli_runs.subprocess, "run", side_effect=fake_run),
            self.assertRaises(cli_runs.RunsApiError),
        ):
            cli_runs._resolve_owner_repo(_Args())


class _FakeAPI:
    """Minimal stand-in for ``GitHubAPI`` returning canned workflow/run payloads."""

    def __init__(self, *_a, **_k):
        self.calls: list[tuple] = []

    def request(self, method, path, params=None):
        self.calls.append((method, path, params))
        if path.endswith("/actions/workflows"):
            return {
                "workflows": [
                    {"id": 99, "path": ".github/workflows/email-report.yml"},
                ]
            }
        if "/actions/workflows/99/runs" in path:
            return {
                "workflow_runs": [
                    {"created_at": "2026-06-01T00:00:00Z", "conclusion": "success"},
                ]
            }
        return {}


class EnrichWithApiTests(unittest.TestCase):
    """``_enrich_with_api`` token, resolution, and merge behavior (mocked)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _rows(self):
        return [
            {
                "profile": "default",
                "source": "github_actions",
                "schedule": "0 9 * * 1",
                "active": "active",
                "notes": "",
                "workflow_file": ".github/workflows/email-report.yml",
                "api_last_run": None,
                "api_status": None,
            },
            {
                "profile": "default",
                "source": "launchd",
                "schedule": {"weekday": 1, "hour": 9, "minute": 0},
                "active": "inactive",
                "notes": "",
                "workflow_file": None,
                "api_last_run": None,
                "api_status": None,
            },
        ]

    def test_missing_token_raises(self):
        with (
            mock.patch("github_usage.auth.resolve_token", return_value=None) as resolve,
            self.assertRaises(cli_runs.RunsApiError),
        ):
            cli_runs._enrich_with_api(self._rows(), _Args(api=True, owner="o", repo="r"))
        resolve.assert_called_once_with(argv=[])

    def test_merge_sets_api_fields(self):
        fake = _FakeAPI()
        with (
            mock.patch("github_usage.auth.resolve_token", return_value="tok"),
            mock.patch("github_usage.api.GitHubAPI", return_value=fake),
        ):
            rows = cli_runs._enrich_with_api(self._rows(), _Args(api=True, owner="o", repo="r"))
        ga = next(r for r in rows if r["source"] == "github_actions")
        launchd = next(r for r in rows if r["source"] == "launchd")
        self.assertEqual(ga["api_last_run"], "2026-06-01T00:00:00Z")
        self.assertEqual(ga["api_status"], "success")
        # launchd rows are never enriched.
        self.assertIsNone(launchd["api_last_run"])
        # Verify the workflow-specific runs endpoint (with per_page=1) was used.
        self.assertTrue(
            any(
                "/actions/workflows/99/runs" in call[1] and call[2] == {"per_page": 1}
                for call in fake.calls
            )
        )

    def test_unresolvable_owner_repo_raises(self):
        def fake_run(*_a, **_k):
            return types.SimpleNamespace(returncode=1, stdout="")

        with (
            mock.patch("github_usage.auth.resolve_token", return_value="tok"),
            mock.patch.object(cli_runs.subprocess, "run", side_effect=fake_run),
            self.assertRaises(cli_runs.RunsApiError),
        ):
            cli_runs._enrich_with_api(self._rows(), _Args(api=True))


class MainEntryPointTests(unittest.TestCase):
    """End-to-end ``main()`` behavior: routing, errors, output formats."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        # Point the command at the temp repo and isolate launchd checks.
        missing = self.root / "LaunchAgents"
        self._patches = [
            mock.patch.object(cli_runs, "repo_root", lambda: self.root),
            mock.patch.object(
                cli_runs, "launch_agent_dest", lambda name: missing / f"{name}.plist"
            ),
            mock.patch.object(
                cli_runs, "legacy_launch_agent_dest", lambda: missing / "legacy.plist"
            ),
        ]
        for patcher in self._patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, argv):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_runs.main(argv)
        return code, stdout.getvalue()

    def test_help_exits_zero(self):
        code, out = self._run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("github-usage runs", out)

    def test_text_output_default(self):
        code, out = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("Configured runs:", out)
        self.assertIn("Warning: No config.toml found", out)

    def test_json_active_is_always_string(self):
        code, out = self._run(["--json"])
        self.assertEqual(code, 0)
        # Strip the leading warning line before parsing JSON.
        payload = out[out.index("[") :]
        rows = json.loads(payload)
        for row in rows:
            self.assertIn(row["active"], {"active", "inactive", "unsupported"})

    def test_corrupted_toml_exits_one(self):
        _write(self.paths_config(), "this is = = not valid toml [[[")
        code, out = self._run([])
        self.assertEqual(code, 1)
        self.assertIn("Failed to parse config.toml", out)

    def test_duplicate_profile_name_exits_one(self):
        _write(
            self.paths_config(),
            '[[reports]]\nname = "dup"\n[[reports]]\nname = "dup"\n',
        )
        code, out = self._run([])
        self.assertEqual(code, 1)
        self.assertIn("Invalid config.toml", out)

    def test_missing_profile_name_exits_one(self):
        _write(self.paths_config(), '[[reports]]\ntarget_email = "x@y.z"\n')
        code, out = self._run([])
        self.assertEqual(code, 1)
        self.assertIn("Invalid config.toml", out)

    def test_unknown_profile_filter_exits_one(self):
        code, out = self._run(["--profile", "ghost"])
        self.assertEqual(code, 1)
        self.assertIn("Profile 'ghost' not found", out)

    def test_api_missing_token_exits_one(self):
        with mock.patch("github_usage.auth.resolve_token", return_value=None):
            code, out = self._run(["--api", "--owner", "o", "--repo", "r"])
        self.assertEqual(code, 1)
        self.assertIn("No GitHub token found", out)

    def test_api_warning_under_absent_config(self):
        fake = _FakeAPI()
        with (
            mock.patch("github_usage.auth.resolve_token", return_value="tok"),
            mock.patch("github_usage.api.GitHubAPI", return_value=fake),
        ):
            code, out = self._run(["--api", "--owner", "o", "--repo", "r"])
        self.assertEqual(code, 0)
        self.assertIn("Warning: No config.toml found", out)

    def paths_config(self) -> Path:
        """Return the temp repo's config.toml path."""
        return self.root / ".github-usage" / "config.toml"


if __name__ == "__main__":
    unittest.main()
