"""Tests for the repository backup-file harness."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class BackupPolicyTests(unittest.TestCase):
    """Verify backup files stay out of commits."""

    def test_temporary_repo_isolates_and_restores_hook_environment(self) -> None:
        """Hook Git variables must not redirect fixture commands to the real repo."""
        inherited = {
            "GIT_DIR": "/nonexistent/hook-repo",
            "GIT_INDEX_FILE": "/nonexistent/hook-index",
            "GIT_WORK_TREE": "/nonexistent/hook-worktree",
        }
        with patch.dict(os.environ, inherited):
            with temporary_git_repo() as repo:
                local_vars = subprocess.check_output(
                    ["git", "rev-parse", "--local-env-vars"], text=True
                ).splitlines()
                for name in local_vars:
                    self.assertNotIn(name, os.environ)
                result = subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"], cwd=repo, text=True
                )
                self.assertEqual(Path(result.strip()).resolve(), repo.resolve())
            for key, value in inherited.items():
                self.assertEqual(os.environ[key], value)

    def test_gitignore_ignores_transient_backup_files(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("backups/*.bak", gitignore)

    def test_pre_commit_runs_backup_policy_before_pruning(self) -> None:
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

        policy_index = config.index("id: check-backups")
        prune_index = config.index("id: prune-stale-backups")
        self.assertLess(policy_index, prune_index)

    def test_check_backups_rejects_staged_backup_additions(self) -> None:
        with temporary_git_repo() as repo:
            install_check_backups(repo)
            backup = repo / "backups" / "edited.py.bak"
            backup.parent.mkdir()
            backup.write_text("temporary copy\n", encoding="utf-8")
            git(repo, "add", "backups/edited.py.bak")

            result = subprocess.run(
                [str(repo / "scripts" / "check-backups")],
                cwd=repo,
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Do not stage backups/*.bak files", result.stderr)

    def test_check_backups_rejects_tracked_non_backup_files(self) -> None:
        with temporary_git_repo() as repo:
            install_check_backups(repo)
            note = repo / "backups" / "notes.txt"
            note.parent.mkdir()
            note.write_text("not a backup\n", encoding="utf-8")
            git(repo, "add", "backups/notes.txt")
            git(repo, "commit", "-m", "add invalid backup file")

            result = subprocess.run(
                [str(repo / "scripts" / "check-backups")],
                cwd=repo,
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Only backups/*.bak files are allowed", result.stderr)


def install_check_backups(repo: Path) -> None:
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts" / "check-backups", scripts / "check-backups")


@contextmanager
def temporary_git_repo() -> Iterator[Path]:
    """Create an isolated Git fixture and restore the caller's hook environment."""
    with patch.dict(os.environ):
        # Hooks export repository-local variables, including the worktree index.
        # Clear them for every fixture command, including spawned scripts.
        local_vars = subprocess.check_output(
            ["git", "rev-parse", "--local-env-vars"], text=True
        ).splitlines()
        for name in local_vars:
            os.environ.pop(name, None)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.com")
            git(repo, "config", "user.name", "Test User")
            yield repo


def git(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z"})
    subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)
