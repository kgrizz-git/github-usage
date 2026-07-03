"""Tests for gui_backend runs and drift helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage.gui_backend import (
    check_workflow_drift,
    formatted_scheduled_runs,
    load_setup_paths,
)


class RunsBackendTests(unittest.TestCase):
    """Scheduled runs formatting and drift wrapper."""

    def test_formatted_scheduled_runs_empty_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = load_setup_paths(Path(tmp))
            rows = formatted_scheduled_runs(paths)
        self.assertIsInstance(rows, list)

    def test_check_workflow_drift_git_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = load_setup_paths(Path(tmp))
            with mock.patch(
                "github_usage.cli_runs_diff.check_prerequisites",
                return_value="git missing",
            ):
                result = check_workflow_drift(paths)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("git missing", result.messages[0])


if __name__ == "__main__":
    unittest.main()
