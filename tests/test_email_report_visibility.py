"""Tests for public/private visibility split rendering in email report formatters."""

from __future__ import annotations

import unittest


class EmailReportVisibilityTests(unittest.TestCase):
    def test_format_actions_section_shows_split_when_public_minutes_present(self):
        from github_usage.email_report_text import _format_actions_section

        data = {
            "actions": {
                "minutes": 1500.0,
                "minutes_limit": 2000,
                "minutes_percent": 75.0,
                "storage_avg_mb": 200.0,
                "storage_limit_mb": 500,
                "storage_percent": 40.0,
                "private_minutes": 1200.0,
                "public_minutes": 300.0,
            },
            "monthly_costs": {"actions": {"net": 0.0}},
        }
        lines = _format_actions_section(data)
        joined = "\n".join(lines)
        self.assertIn("private: 1,200.0 min quota-counted", joined)
        self.assertIn("public: 300.0 min free", joined)

    def test_format_actions_section_no_split_without_public_minutes(self):
        from github_usage.email_report_text import _format_actions_section

        data = {
            "actions": {
                "minutes": 500.0,
                "minutes_limit": 2000,
                "minutes_percent": 25.0,
                "storage_avg_mb": 100.0,
                "storage_limit_mb": 500,
                "storage_percent": 20.0,
            },
            "monthly_costs": {"actions": {"net": 0.0}},
        }
        lines = _format_actions_section(data)
        joined = "\n".join(lines)
        self.assertNotIn("private:", joined)
        self.assertNotIn("public:", joined)

    def test_public_repos_text_note_returns_note_with_minutes_and_storage(self):
        from github_usage.email_report_text import _public_repos_text_note

        note = _public_repos_text_note({"public_minutes": 500.0, "public_storage_avg_mb": 12.5})
        self.assertIn("500.0 min", note)
        self.assertIn("12.5 MB avg storage", note)

    def test_public_repos_text_note_omits_storage_line_when_zero(self):
        from github_usage.email_report_text import _public_repos_text_note

        note = _public_repos_text_note({"public_minutes": 100.0, "public_storage_avg_mb": 0.0})
        self.assertIn("100.0 min", note)
        self.assertNotIn("MB", note)

    def test_public_repos_text_note_returns_empty_when_both_zero(self):
        from github_usage.email_report_text import _public_repos_text_note

        self.assertEqual(
            _public_repos_text_note({"public_minutes": 0.0, "public_storage_avg_mb": 0.0}), ""
        )

    def test_public_repos_html_note_returns_html_with_data(self):
        from github_usage.email_report_html import _public_repos_html_note

        note = _public_repos_html_note({"public_minutes": 200.0, "public_storage_avg_mb": 5.0})
        self.assertIn("200.0 min", note)
        self.assertIn("visibility-tag", note)
        self.assertIn("5.0 MB avg storage", note)

    def test_public_repos_html_note_omits_storage_when_minutes_positive_mb_zero(self):
        from github_usage.email_report_html import _public_repos_html_note

        note = _public_repos_html_note({"public_minutes": 300.0, "public_storage_avg_mb": 0.0})
        self.assertIn("300.0 min", note)
        self.assertNotIn("MB", note)

    def test_public_repos_html_note_returns_empty_when_both_zero(self):
        from github_usage.email_report_html import _public_repos_html_note

        self.assertEqual(
            _public_repos_html_note({"public_minutes": 0.0, "public_storage_avg_mb": 0.0}), ""
        )

    def test_format_forecast_section_shows_private_scope_when_split_available(self):
        from datetime import date

        from github_usage.email_report_text import _format_forecast_section

        data = {
            "actions": {
                "minutes": 1500.0,
                "minutes_limit": 2000,
                "storage_avg_mb": 200.0,
                "storage_limit_mb": 500,
                "private_minutes": 1200.0,
                "public_minutes": 300.0,
                "public_storage_avg_mb": 50.0,
            },
            "copilot": None,
        }
        lines = _format_forecast_section(
            data, include_forecast=True, reference_date=date(2026, 8, 5)
        )
        joined = "\n".join(lines)
        self.assertIn("private repos", joined)
        self.assertIn("Public repos (free)", joined)
        self.assertIn("300.0 min", joined)

    def test_format_html_forecast_section_shows_private_scope_when_split_available(self):
        from datetime import date

        from github_usage.email_report_html import _format_html_forecast_section

        data = {
            "actions": {
                "minutes": 1500.0,
                "minutes_limit": 2000,
                "storage_avg_mb": 200.0,
                "storage_limit_mb": 500,
                "private_minutes": 1200.0,
                "public_minutes": 300.0,
                "public_storage_avg_mb": 50.0,
            },
            "copilot": None,
        }
        parts = _format_html_forecast_section(
            data, include_forecast=True, reference_date=date(2026, 8, 5)
        )
        html_body = "\n".join(parts)
        self.assertIn("private repos", html_body)
        self.assertIn("visibility-tag", html_body)
        self.assertIn("300.0 min", html_body)


if __name__ == "__main__":
    unittest.main()
