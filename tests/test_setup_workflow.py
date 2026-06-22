"""Tests for setup_workflow: cron validation, template rendering, atomic write, diff."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage.setup_workflow import (
    DEFAULT_WORKFLOW_CONFIG,
    diff_workflow,
    render_workflow,
    validate_cron,
    workflow_path,
    write_workflow,
)

# Path to the actual checked-in template.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE = _REPO_ROOT / ".github" / "workflows" / "email-report.yml.template"


class ValidateCronTests(unittest.TestCase):
    def test_accepts_valid_expressions(self):
        for expr in [
            "0 9 * * 1",
            "*/30 9-17 * * 1-5",
            "0 0 1 * *",
            "0 9 * * 1,3",
            "0 9 * * 0",
            "0 9 * * 7",
        ]:
            with self.subTest(expr=expr):
                self.assertEqual(validate_cron(expr), expr)

    def test_rejects_four_fields(self):
        with self.assertRaises(ValueError):
            validate_cron("9 * * *")

    def test_rejects_six_fields(self):
        with self.assertRaises(ValueError):
            validate_cron("0 0 9 * * 1")

    def test_rejects_invalid_weekday(self):
        with self.assertRaises(ValueError):
            validate_cron("0 9 * * 8")

    def test_rejects_invalid_hour(self):
        with self.assertRaises(ValueError):
            validate_cron("0 24 * * 1")

    def test_rejects_at_shortcut(self):
        with self.assertRaises(ValueError):
            validate_cron("@weekly")

    def test_rejects_quartz_question_mark(self):
        with self.assertRaises(ValueError):
            validate_cron("0 9 ? * 1")

    def test_rejects_quartz_L(self):
        with self.assertRaises(ValueError):
            validate_cron("0 9 L * 1")

    def test_rejects_non_cron_text(self):
        with self.assertRaises(ValueError):
            validate_cron("not a cron")

    def test_rejects_invalid_step(self):
        with self.assertRaises(ValueError):
            validate_cron("*/0 9 * * 1")

    def test_rejects_inverted_range(self):
        with self.assertRaises(ValueError):
            validate_cron("0 17-9 * * 1")


class RenderWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        wf_dir = self.root / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        shutil.copy(_TEMPLATE, wf_dir / "email-report.yml.template")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _config(self, **overrides) -> dict:
        ga = dict(DEFAULT_WORKFLOW_CONFIG)
        ga.update(overrides)
        return {"github_actions": ga}

    def test_default_config_renders_cron_and_false_defaults(self):
        rendered = render_workflow(self._config(), self.root)
        self.assertIn("cron: '0 9 * * 1'", rendered)
        self.assertIn("|| 'false'", rendered)

    def test_include_consumers_true_renders_true_fallback(self):
        rendered = render_workflow(self._config(include_consumers=True), self.root)
        self.assertIn("inputs.include_consumers || 'true'", rendered)

    def test_include_artifact_storage_true_renders_true_fallback(self):
        rendered = render_workflow(self._config(include_artifact_storage=True), self.root)
        self.assertIn("inputs.include_artifact_storage || 'true'", rendered)

    def test_include_release_assets_true_renders_true_fallback(self):
        rendered = render_workflow(self._config(include_release_assets=True), self.root)
        self.assertIn("inputs.include_release_assets || 'true'", rendered)

    def test_no_token_strings_remain_after_render(self):
        rendered = render_workflow(self._config(), self.root)
        self.assertNotIn("__CRON__", rendered)
        self.assertNotIn("__INCLUDE_CONSUMERS_DEFAULT__", rendered)
        self.assertNotIn("__INCLUDE_ARTIFACT_STORAGE_DEFAULT__", rendered)
        self.assertNotIn("__INCLUDE_RELEASE_ASSETS_DEFAULT__", rendered)

    def test_custom_cron_appears_in_rendered_output(self):
        rendered = render_workflow(self._config(cron="0 8 * * 5"), self.root)
        self.assertIn("cron: '0 8 * * 5'", rendered)

    def test_rendered_output_has_expected_yaml_structure(self):
        rendered = render_workflow(self._config(), self.root)
        self.assertIn("name:", rendered)
        self.assertIn("jobs:", rendered)
        self.assertIn("schedule:", rendered)
        self.assertIn("workflow_dispatch:", rendered)

    def test_render_is_idempotent(self):
        config = self._config()
        first = render_workflow(config, self.root)
        second = render_workflow(config, self.root)
        self.assertEqual(first, second)

    def test_missing_template_raises_file_not_found(self):
        (self.root / ".github" / "workflows" / "email-report.yml.template").unlink()
        with self.assertRaises(FileNotFoundError):
            render_workflow(self._config(), self.root)


class WriteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_write_creates_file_with_correct_content(self):
        text = "name: Test\non:\n  schedule:\n    - cron: '0 9 * * 1'\n"
        write_workflow(self.root, text)
        dest = workflow_path(self.root)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_text(encoding="utf-8"), text)

    def test_write_creates_parent_directory(self):
        self.assertFalse((self.root / ".github").exists())
        write_workflow(self.root, "content\n")
        self.assertTrue(workflow_path(self.root).is_file())

    def test_write_sets_644_permissions(self):
        write_workflow(self.root, "content\n")
        mode = workflow_path(self.root).stat().st_mode & 0o777
        self.assertEqual(mode, 0o644)

    def test_write_is_atomic_and_cleans_up_temp_on_failure(self):
        original = "original content\n"
        write_workflow(self.root, original)
        wf_dir = workflow_path(self.root).parent

        with mock.patch("os.replace", side_effect=OSError("disk full")), self.assertRaises(OSError):
            write_workflow(self.root, "new content\n")

        # Destination unchanged.
        self.assertEqual(workflow_path(self.root).read_text(encoding="utf-8"), original)
        # No orphaned temp files.
        tmp_files = list(wf_dir.glob("*.tmp"))
        self.assertEqual(tmp_files, [])


class DiffWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        shutil.copy(_TEMPLATE, self.root)  # not in workflows dir; just a ref

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_diff_returns_empty_when_file_absent(self):
        self.assertEqual(diff_workflow(self.root, "anything\n"), "")

    def test_diff_returns_empty_when_content_matches(self):
        text = "name: Test\n"
        write_workflow(self.root, text)
        self.assertEqual(diff_workflow(self.root, text), "")

    def test_diff_returns_nonempty_when_content_differs(self):
        write_workflow(self.root, "name: Old\n")
        result = diff_workflow(self.root, "name: New\n")
        self.assertNotEqual(result, "")
        self.assertIn("-name: Old", result)
        self.assertIn("+name: New", result)

    def test_diff_returns_empty_after_write_workflow(self):
        """Separate from idempotency: write then diff — on-disk matches rendered."""
        import shutil as _shutil

        tmpdir2 = tempfile.mkdtemp()
        root2 = Path(tmpdir2)
        wf_dir = root2 / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        _shutil.copy(_TEMPLATE, wf_dir / "email-report.yml.template")
        try:
            config = {"github_actions": dict(DEFAULT_WORKFLOW_CONFIG)}
            rendered = render_workflow(config, root2)
            write_workflow(root2, rendered)
            self.assertEqual(diff_workflow(root2, rendered), "")
        finally:
            _shutil.rmtree(tmpdir2)
