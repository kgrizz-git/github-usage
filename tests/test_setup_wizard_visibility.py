"""Tests for wizard visibility filter validation."""

from __future__ import annotations

import unittest

from github_usage.gui.wizard.setup_wizard_flow import WizardData, validate_options


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


if __name__ == "__main__":
    unittest.main()
