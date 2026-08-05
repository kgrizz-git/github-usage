"""Tests for wizard visibility filter validation and wizard flow helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage.gui.wizard.setup_wizard_flow import (
    WizardData,
    load_initial_data,
    review_summary,
    save_options_step,
    validate_options,
)
from github_usage.setup_config import SetupPaths, load_config, write_config


class WizardVisibilityFilterTests(unittest.TestCase):
    def test_validate_options_rejects_both_visibility_filters(self) -> None:
        data = WizardData(only_public=True, only_private=True)
        self.assertEqual(
            validate_options(data),
            "Only one visibility filter can be enabled: public or private",
        )

    def test_validate_options_allows_single_visibility_filter(self) -> None:
        data = WizardData(only_public=True)
        self.assertIsNone(validate_options(data))


class WizardEmailFormatFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.paths = SetupPaths.from_root(self.root)
        write_config(self.paths.config_file, load_config(self.paths.config_file))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_load_initial_data_reads_email_format_html(self):
        write_config(
            self.paths.config_file,
            {"email_report": {"email_format": "html"}},
        )
        with mock.patch("github_usage.gui.wizard.setup_wizard_flow.read_secrets", return_value={}):
            data = load_initial_data(self.paths)
        self.assertEqual(data.email_format, "html")

    def test_load_initial_data_defaults_email_format_to_text(self):
        write_config(self.paths.config_file, {"email_report": {}})
        with mock.patch("github_usage.gui.wizard.setup_wizard_flow.read_secrets", return_value={}):
            data = load_initial_data(self.paths)
        self.assertEqual(data.email_format, "text")

    def test_save_options_step_persists_email_format_html(self):
        data = WizardData(email_format="html")
        with mock.patch("github_usage.gui.wizard.setup_wizard_flow.apply_env"):
            save_options_step(self.paths, data)
        config = load_config(self.paths.config_file)
        self.assertEqual(config["email_report"]["email_format"], "html")

    def test_save_options_step_persists_email_format_text(self):
        data = WizardData(email_format="text")
        with mock.patch("github_usage.gui.wizard.setup_wizard_flow.apply_env"):
            save_options_step(self.paths, data)
        config = load_config(self.paths.config_file)
        self.assertEqual(config["email_report"]["email_format"], "text")

    def test_review_summary_includes_email_format(self):
        data = WizardData(email_format="html")
        summary = review_summary(data)
        self.assertIn("html", summary)
        self.assertIn("Email format", summary)

    def test_wizard_data_default_email_format_is_text(self):
        self.assertEqual(WizardData().email_format, "text")

    def test_load_initial_data_normalizes_uppercase_email_format(self):
        write_config(self.paths.config_file, {"email_report": {"email_format": "HTML"}})
        with mock.patch("github_usage.gui.wizard.setup_wizard_flow.read_secrets", return_value={}):
            data = load_initial_data(self.paths)
        self.assertEqual(data.email_format, "html")

    def test_load_initial_data_rejects_invalid_email_format(self):
        write_config(self.paths.config_file, {"email_report": {"email_format": "plaintext"}})
        with mock.patch("github_usage.gui.wizard.setup_wizard_flow.read_secrets", return_value={}):
            data = load_initial_data(self.paths)
        self.assertEqual(data.email_format, "text")


if __name__ == "__main__":
    unittest.main()
