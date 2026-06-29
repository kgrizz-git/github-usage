"""Tests for the ``github-usage runs --diff`` subcommand (``github_usage.cli_runs_diff``)
and the diff path in ``cli_runs._run_diff``.

All subprocess calls are intercepted via a ``FakeGit`` helper that returns
canned ``CompletedProcess`` results keyed by argv. No live network, no live
``git``. Tests run on any host regardless of whether ``git`` is installed
(``check_prerequisites`` is exercised separately).
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage import cli_runs, cli_runs_diff
from github_usage.setup_config import SetupPaths
from tests._fakes import FakeGit

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_git_repo(root: Path) -> None:
    """Create a real git repo at ``root`` with one initial commit."""
    (root / ".git").mkdir()
    # Minimal git internals so the helpers don't need to call real git.
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n")
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "refs" / "remotes").mkdir(parents=True)


def _make_config(root: Path) -> SetupPaths:
    paths = SetupPaths.from_root(root)
    _write(paths.config_file, "")
    return paths


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


# ---------------------------------------------------------------------------
# Unit tests for the algorithm
# ---------------------------------------------------------------------------


class ResolveRemoteNameTests(unittest.TestCase):
    """``resolve_remote_name`` falls back to ``origin`` on failure or detached HEAD."""

    def test_returns_configured_remote(self):
        fake = FakeGit(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): {"stdout": "main\n"},
                ("config", "branch.main.remote"): {"stdout": "upstream\n"},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(cli_runs_diff.resolve_remote_name(Path("/r")), "upstream")

    def test_falls_back_to_origin_on_missing_config(self):
        fake = FakeGit(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): {"stdout": "main\n"},
                ("config", "branch.main.remote"): {"returncode": 1, "stdout": ""},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(cli_runs_diff.resolve_remote_name(Path("/r")), "origin")

    def test_detached_head_falls_back_to_origin(self):
        # Detached HEAD: rev-parse returns "HEAD" (literal), not a branch.
        fake = FakeGit(
            responses={
                ("rev-parse", "--abbrev-ref", "HEAD"): {"stdout": "HEAD\n"},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(cli_runs_diff.resolve_remote_name(Path("/r")), "origin")

    def test_subprocess_error_falls_back_to_origin(self):
        def boom(*a, **kw):
            raise FileNotFoundError("git not found")

        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=boom):
            self.assertEqual(cli_runs_diff.resolve_remote_name(Path("/r")), "origin")


class ResolveDefaultBranchTests(unittest.TestCase):
    """``resolve_default_branch`` verifies each candidate ref before returning it."""

    def test_returns_symbolic_ref_value(self):
        fake = FakeGit(
            responses={
                ("symbolic-ref", "refs/remotes/origin/HEAD"): {
                    "stdout": "refs/remotes/origin/main\n"
                },
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(cli_runs_diff.resolve_default_branch(Path("/r"), "origin"), "main")

    def test_falls_back_to_main_then_master(self):
        # symbolic-ref fails; main is verified; returns "main".
        fake = FakeGit(
            responses={
                ("symbolic-ref", "refs/remotes/origin/HEAD"): {"returncode": 1},
                ("rev-parse", "--verify", "refs/remotes/origin/main"): {"returncode": 0},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(cli_runs_diff.resolve_default_branch(Path("/r"), "origin"), "main")

    def test_falls_back_to_master_when_main_missing(self):
        # symbolic-ref fails; main is missing; master is verified; returns "master".
        fake = FakeGit(
            responses={
                ("symbolic-ref", "refs/remotes/origin/HEAD"): {"returncode": 1},
                ("rev-parse", "--verify", "refs/remotes/origin/main"): {"returncode": 1},
                ("rev-parse", "--verify", "refs/remotes/origin/master"): {"returncode": 0},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(cli_runs_diff.resolve_default_branch(Path("/r"), "origin"), "master")

    def test_returns_none_when_no_candidates(self):
        fake = FakeGit(
            responses={
                ("symbolic-ref", "refs/remotes/origin/HEAD"): {"returncode": 1},
                ("rev-parse", "--verify", "refs/remotes/origin/main"): {"returncode": 1},
                ("rev-parse", "--verify", "refs/remotes/origin/master"): {"returncode": 1},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertIsNone(cli_runs_diff.resolve_default_branch(Path("/r"), "origin"))


class FetchRemoteTests(unittest.TestCase):
    """``fetch_remote`` returns fetch outcome and falls back gracefully."""

    def test_skip_fetch_returns_false_false(self):
        self.assertEqual(
            cli_runs_diff.fetch_remote(Path("/r"), "origin", skip_fetch=True, env={}),
            (False, False),
        )

    def test_successful_fetch_returns_true_false(self):
        fake = FakeGit(
            responses={
                ("fetch", "origin"): {"returncode": 0},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(
                cli_runs_diff.fetch_remote(Path("/r"), "origin", skip_fetch=False, env={}),
                (True, False),
            )

    def test_failed_fetch_returns_false_false(self):
        fake = FakeGit(
            responses={
                ("fetch", "origin"): {"returncode": 128, "stderr": "fatal: not a repo"},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            self.assertEqual(
                cli_runs_diff.fetch_remote(Path("/r"), "origin", skip_fetch=False, env={}),
                (False, False),
            )

    def test_timeout_returns_false_false(self):
        def boom(*a, **kw):
            raise subprocess.TimeoutExpired(cmd=a, timeout=60)

        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=boom):
            self.assertEqual(
                cli_runs_diff.fetch_remote(Path("/r"), "origin", skip_fetch=False, env={}),
                (False, False),
            )

    def test_missing_git_returns_false_false(self):
        def boom(*a, **kw):
            raise FileNotFoundError("git not found")

        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=boom):
            self.assertEqual(
                cli_runs_diff.fetch_remote(Path("/r"), "origin", skip_fetch=False, env={}),
                (False, False),
            )


class ClassifyDriftTests(unittest.TestCase):
    """End-to-end ``classify_drift`` against canned git responses."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run_classify(self, fake, *, remote="origin", default_branch="main", candidate_path=None):
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            return cli_runs_diff.classify_drift(
                self.root, remote, default_branch, candidate_path=candidate_path
            )

    def test_in_sync_modification(self):
        # One local path, hashes match at HEAD and origin/main.
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": ".github/workflows/email-report.yml\n"
                },
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-tree", "origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "in-sync")

    def test_local_committed_deletion_is_ahead(self):
        # Local deletion: HEAD has nothing, origin has the file. Three-dot
        # diff `git diff origin/main...HEAD` is non-empty (shows the deletion).
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
                ("ls-tree", "-r", "origin/main", "--", ".github/workflows/"): {
                    "stdout": "100644 blob def456\t.github/workflows/email-report.yml\n"
                },
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report.yml"): {"stdout": ""},
                ("ls-tree", "origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob def456\t.github/workflows/email-report.yml\n"
                },
                # ahead_diff non-empty (deletion); behind_diff empty.
                ("diff", "origin/main...HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "-deleted content\n"
                },
                ("diff", "HEAD...origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": ""
                },
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "ahead")
        self.assertEqual(rows[0]["summary"], "deleted locally, not pushed")

    def test_remote_deletion_is_behind(self):
        # Remote deletion: HEAD has the file, origin does not. Three-dot
        # diff `git diff HEAD...origin/main` is non-empty (shows the deletion
        # from origin's perspective).
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": ".github/workflows/email-report.yml\n"
                },
                ("ls-tree", "-r", "origin/main", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-tree", "origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": ""
                },
                # ahead_diff empty; behind_diff non-empty (deletion).
                ("diff", "origin/main...HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": ""
                },
                ("diff", "HEAD...origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "-deleted content\n"
                },
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "behind")
        self.assertEqual(rows[0]["summary"], "deleted on remote, not pulled")

    def test_remote_only(self):
        # File on remote only (not in HEAD, not on disk).
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
                ("ls-tree", "-r", "origin/main", "--", ".github/workflows/"): {
                    "stdout": "100644 blob def456\t.github/workflows/email-report.yml\n"
                },
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report.yml"): {"stdout": ""},
                ("ls-tree", "origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob def456\t.github/workflows/email-report.yml\n"
                },
                ("diff", "origin/main...HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": ""
                },
                ("diff", "HEAD...origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "+new content\n"
                },
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "remote-only")
        self.assertEqual(rows[0]["summary"], "added on remote, not pulled")

    def test_uncommitted_working_tree(self):
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {
                    "stdout": " M .github/workflows/email-report.yml\n"
                },
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": ".github/workflows/email-report.yml\n"
                },
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "uncommitted")
        self.assertEqual(rows[0]["summary"], "uncommitted changes in working tree")

    def test_staged_index_change(self):
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {
                    "stdout": "M  .github/workflows/email-report.yml\n"
                },
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": ".github/workflows/email-report.yml\n"
                },
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "staged")
        self.assertEqual(rows[0]["summary"], "staged changes in index")

    def test_combined_mm_status_is_uncommitted(self):
        # `MM` = staged + further working-tree change. Y column non-space
        # wins → uncommitted.
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {
                    "stdout": "MM .github/workflows/email-report.yml\n"
                },
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": ".github/workflows/email-report.yml\n"
                },
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "uncommitted")

    def test_untracked_file(self):
        # File on disk but not in git ls-files.
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {
                    "stdout": "?? .github/workflows/email-report-new.yml\n"
                },
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
            }
        )
        # Need to also create the on-disk file for the glob to find it.
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "email-report-new.yml").write_text("...")
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "untracked")
        self.assertEqual(rows[0]["summary"], "untracked file")

    def test_default_branch_none_degrades_to_unknown(self):
        # No remote ref available; the algorithm should not even attempt
        # remote listing and should mark rows that need a remote check
        # as `unknown`.
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": ".github/workflows/email-report.yml\n"
                },
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                # Note: NO call to ls-tree origin/main/... (skipped when
                # default_branch is None).
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            rows = cli_runs_diff.classify_drift(self.root, "origin", None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "unknown")
        self.assertIn("no remote default branch ref", rows[0]["summary"])

    def test_per_file_vs_per_repo_regression(self):
        # An unrelated local change to README.md should not produce a
        # drift row for email-report.yml.
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                # README.md is in HEAD's tree but not in workflows; shouldn't
                # affect the email-report path discovery.
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": ".github/workflows/email-report.yml\n"
                },
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-tree", "origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
            }
        )
        rows = self._run_classify(fake)
        # Only the email-report.yml row, despite README.md being a local change.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], ".github/workflows/email-report.yml")

    def test_staged_deletion_discovered_via_ls_tree_head(self):
        # `git rm` followed by no commit: not in ls-files, not on disk,
        # but still in HEAD's tree → discovered via `git ls-tree -r HEAD`.
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {
                    "stdout": "D  .github/workflows/email-report.yml\n"
                },
                # ls-tree HEAD still has the file (it was committed in HEAD).
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                # ls-files does NOT have it (removed from index).
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
            }
        )
        rows = self._run_classify(fake)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["drift"], "staged")
        self.assertEqual(rows[0]["summary"], "staged changes in index")

    def test_path_normalization_handles_absolute_and_relative(self):
        # glob returns absolute, ls-tree returns repo-relative; both
        # should normalize to the same path. The `??` status (untracked)
        # takes precedence over blob comparison.
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "email-report.yml").write_text("new")
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {
                    "stdout": "?? .github/workflows/email-report.yml\n"
                },
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
            }
        )
        rows = self._run_classify(fake)
        # No ValueError, single row, repo-relative path.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], ".github/workflows/email-report.yml")

    def test_batched_git_status_called_once(self):
        # The single `git status` call covers all candidate paths, not
        # one call per file. Assert via FakeGit call log.
        fake = FakeGit(
            responses={
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {
                    "stdout": (
                        "100644 blob abc123\t.github/workflows/email-report.yml\n"
                        "100644 blob def456\t.github/workflows/email-report-weekly.yml\n"
                    )
                },
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {
                    "stdout": (
                        ".github/workflows/email-report.yml\n"
                        ".github/workflows/email-report-weekly.yml\n"
                    )
                },
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-tree", "origin/main", "--", ".github/workflows/email-report.yml"): {
                    "stdout": "100644 blob abc123\t.github/workflows/email-report.yml\n"
                },
                ("ls-tree", "HEAD", "--", ".github/workflows/email-report-weekly.yml"): {
                    "stdout": "100644 blob def456\t.github/workflows/email-report-weekly.yml\n"
                },
                ("ls-tree", "origin/main", "--", ".github/workflows/email-report-weekly.yml"): {
                    "stdout": "100644 blob def456\t.github/workflows/email-report-weekly.yml\n"
                },
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            cli_runs_diff.classify_drift(self.root, "origin", "main")
        status_calls = [
            c for c in fake.calls if len(c) >= 2 and c[0] == "status" and c[1] == "--porcelain=v1"
        ]
        self.assertEqual(
            len(status_calls), 1, f"Expected 1 status call, got {len(status_calls)}: {status_calls}"
        )


class PrerequisiteTests(unittest.TestCase):
    """``check_prerequisites`` returns clear errors for missing prerequisites."""

    def test_returns_error_when_git_missing(self):
        with mock.patch.object(cli_runs_diff.shutil, "which", return_value=None):
            err = cli_runs_diff.check_prerequisites(Path("/r"))
        self.assertEqual(err, cli_runs_diff.ERR_GIT_MISSING)

    def test_returns_error_when_not_git_repo(self):
        with (
            mock.patch.object(cli_runs_diff.shutil, "which", return_value="/usr/bin/git"),
            tempfile.TemporaryDirectory() as tmp,
        ):
            root = Path(tmp)
            # No .git directory.
            err = cli_runs_diff.check_prerequisites(root)
        self.assertEqual(err, cli_runs_diff.ERR_NOT_GIT_REPO)

    def test_returns_none_when_prerequisites_met(self):
        with (
            mock.patch.object(cli_runs_diff.shutil, "which", return_value="/usr/bin/git"),
            tempfile.TemporaryDirectory() as tmp,
        ):
            root = Path(tmp)
            (root / ".git").mkdir()
            err = cli_runs_diff.check_prerequisites(root)
        self.assertIsNone(err)


# ---------------------------------------------------------------------------
# End-to-end tests through the main() entry point
# ---------------------------------------------------------------------------


class MainDiffPathTests(unittest.TestCase):
    """End-to-end tests for ``github-usage runs --diff`` through ``main()``."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _make_git_repo(self.root)
        self.paths = _make_config(self.root)
        self.addCleanup(self._tmp.cleanup)
        # Point the diff path at the temp repo.
        self._repo_root_patch = mock.patch.object(cli_runs, "repo_root", lambda: self.root)
        self._repo_root_patch.start()
        self.addCleanup(self._repo_root_patch.stop)

    def _run(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli_runs.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_help_exits_zero(self):
        code, out, _ = self._run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("--diff", out)
        self.assertIn("--no-fetch", out)

    def test_missing_git_binary_exits_one(self):
        with mock.patch.object(cli_runs_diff.shutil, "which", return_value=None):
            code, _, err = self._run(["--diff", "--no-fetch"])
        self.assertEqual(code, 1)
        self.assertIn("git is required for --diff", err)

    def test_not_git_repo_exits_one(self):
        with (
            mock.patch.object(cli_runs_diff.shutil, "which", return_value="/usr/bin/git"),
            tempfile.TemporaryDirectory() as tmp,
        ):
            root = Path(tmp)  # no .git
            _write(root / ".github-usage" / "config.toml", "")
            with mock.patch.object(cli_runs, "repo_root", return_value=root):
                code, _, err = self._run(["--diff", "--no-fetch"])
        self.assertEqual(code, 1)
        self.assertIn("must be run from within a git repository", err)

    def test_diff_with_owner_exits_one(self):
        code, _, err = self._run(["--diff", "--no-fetch", "--owner", "foo"])
        self.assertEqual(code, 1)
        self.assertIn("--owner and --repo only apply to --api", err)

    def test_diff_and_api_mutually_exclusive(self):
        # argparse's mutually exclusive group handles this at parse time.
        code, _, err = self._run(["--diff", "--api"])
        self.assertEqual(code, 2)  # argparse error exit
        self.assertIn("not allowed with argument", err)

    def test_no_fetch_without_diff_exits_one(self):
        code, _, err = self._run(["--no-fetch"])
        self.assertEqual(code, 1)
        self.assertIn("--no-fetch only applies to --diff", err)

    def test_unknown_profile_exits_one(self):
        _write(self.paths.config_file, MULTI_PROFILE_CONFIG)
        code, out, _ = self._run(["--diff", "--no-fetch", "--profile", "ghost"])
        self.assertEqual(code, 1)
        self.assertIn("Profile 'ghost' not found", out)

    def test_malformed_config_exits_one(self):
        _write(self.paths.config_file, "this is = = not valid toml [[[")
        code, out, _ = self._run(["--diff", "--no-fetch", "--profile", "default"])
        self.assertEqual(code, 1)
        self.assertIn("Failed to parse config.toml", out)

    def test_empty_diff_json_shape(self):
        # No workflow files anywhere; should produce a JSON object with
        # empty rows array and metadata.
        fake = FakeGit(
            responses={
                ("fetch", "origin"): {"returncode": 0},
                ("symbolic-ref", "refs/remotes/origin/HEAD"): {
                    "returncode": 0,
                    "stdout": "refs/remotes/origin/main\n",
                },
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
                ("ls-tree", "-r", "origin/main", "--", ".github/workflows/"): {"stdout": ""},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            code, out, _ = self._run(["--diff", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["kind"], "diff")
        self.assertEqual(payload["default_branch"], "main")
        self.assertEqual(payload["remote"], "origin")
        self.assertTrue(payload["fetched"])
        self.assertFalse(payload["using_cached_ref"])
        self.assertFalse(payload["skipped_fetch"])
        self.assertEqual(payload["rows"], [])

    def test_first_run_scenario_fetch_populates_refs(self):
        # Fresh clone: no local refs initially, fetch populates them,
        # resolve_default_branch returns "main" from fresh refs.
        fake = FakeGit(
            responses={
                # First, fetch succeeds and populates refs.
                ("fetch", "origin"): {"returncode": 0},
                # Now symbolic-ref works.
                ("symbolic-ref", "refs/remotes/origin/HEAD"): {
                    "stdout": "refs/remotes/origin/main\n"
                },
                # No workflow files.
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
                ("ls-tree", "-r", "origin/main", "--", ".github/workflows/"): {"stdout": ""},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            code, out, _ = self._run(["--diff", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        # No rows because no workflow files exist.
        self.assertEqual(payload["default_branch"], "main")
        self.assertTrue(payload["fetched"])

    def test_fetch_failure_with_cached_ref(self):
        # Fetch fails but symbolic-ref still works (cached ref exists).
        fake = FakeGit(
            responses={
                ("fetch", "origin"): {
                    "returncode": 128,
                    "stderr": "fatal: could not fetch",
                },
                ("symbolic-ref", "refs/remotes/origin/HEAD"): {
                    "stdout": "refs/remotes/origin/main\n"
                },
                ("status", "--porcelain=v1", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-tree", "-r", "HEAD", "--", ".github/workflows/"): {"stdout": ""},
                ("ls-files", "--", ".github/workflows/email-report*.yml"): {"stdout": ""},
                ("ls-tree", "-r", "origin/main", "--", ".github/workflows/"): {"stdout": ""},
            }
        )
        with mock.patch.object(cli_runs_diff, "_run_git", side_effect=fake):
            code, out, err = self._run(["--diff", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertFalse(payload["fetched"])
        self.assertTrue(payload["using_cached_ref"])
        self.assertIn("falling back to cached refs", err)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class ConstantsTests(unittest.TestCase):
    """Sanity checks for module-level constants."""

    def test_drift_categories_set(self):
        self.assertEqual(
            cli_runs_diff.DRIFT_CATEGORIES,
            frozenset(
                {
                    "in-sync",
                    "uncommitted",
                    "staged",
                    "untracked",
                    "ahead",
                    "behind",
                    "remote-only",
                    "diverged",
                    "unknown",
                }
            ),
        )

    def test_git_env_includes_lc_all(self):
        self.assertEqual(cli_runs_diff.GIT_ENV.get("LC_ALL"), "C")


if __name__ == "__main__":
    unittest.main()
