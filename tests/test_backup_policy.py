"""Tests for the repository backup-file harness."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BackupPolicyTests(unittest.TestCase):
    """Verify backup files stay out of commits."""

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


class temporary_git_repo:
    """Context manager for an isolated git repository."""

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        repo = Path(self._tmp.name)
        git(repo, "init")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test User")
        return repo

    def __exit__(self, *exc_info: object) -> None:
        self._tmp.cleanup()


def git(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z"})
    subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)
