import json
import unittest
from pathlib import Path
from unittest import mock

FIXTURES = Path(__file__).parent / "fixtures"


class EmailReportTests(unittest.TestCase):
    def test_format_report_email_renders_plain_text_sections(self):
        from github_usage.email_report import format_report_email

        data = json.loads((FIXTURES / "email_report_data.json").read_text())

        body = format_report_email(data)

        self.assertIn("GitHub Usage Report for octocat", body)
        self.assertIn("WARNING", body)
        self.assertIn("Actions", body)
        self.assertIn("Copilot Premium Requests", body)
        self.assertIn("Monthly Cost Estimate", body)
        self.assertIn("Top Repositories by Actions Minutes", body)
        self.assertIn("Unavailable Data", body)

    def test_default_subject_uses_username_and_date(self):
        from github_usage.email_report import default_subject

        subject = default_subject("octocat", "2026-06-15T14:30:00Z")

        self.assertEqual(subject, "GitHub Usage Report for octocat - 2026-06-15")

    def test_generated_line_handles_none_empty_and_unparseable(self):
        from datetime import UTC, datetime

        from github_usage.email_report import _generated_line

        today_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        for value in (None, "", "not-an-iso-string"):
            line = _generated_line(value)
            self.assertIn(today_prefix, line)
            self.assertNotIn("None", line)
            self.assertFalse(line.endswith(" "))
            self.assertTrue(line.startswith("Generated: "))

    def test_generated_line_renders_valid_iso_string(self):
        from github_usage.email_report import _generated_line

        line = _generated_line("2026-06-15T14:30:00Z")

        self.assertEqual(line, "Generated: 2026-06-15 14:30 UTC")

    def test_format_report_email_renders_today_when_generated_at_missing(self):
        from datetime import UTC, datetime

        from github_usage.email_report import format_report_email

        data = {
            "username": "octocat",
            "generated_at": None,
            "warnings": [],
            "errors": {},
            "actions": None,
            "copilot": None,
            "git_lfs": None,
            "monthly_costs": {"total": {"gross": 0.0, "discount": 0.0, "net": 0.0}},
            "repo_consumers": None,
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": [],
        }

        body = format_report_email(data)
        today_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        self.assertIn(today_prefix, body)
        self.assertNotIn("Generated: None", body)

    def test_send_email_closes_connection_and_raises_on_non_2xx(self):
        from github_usage.email_report import send_email

        conn = mock.Mock()
        resp = mock.Mock(status=400)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b'{"message":"domain is not verified"}'
        conn.getresponse.return_value = resp

        with (
            mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn),
            self.assertRaisesRegex(RuntimeError, "domain is not verified"),
        ):
            send_email("resend-key", "reports@example.com", "to@example.com", "Subject", "Body")

        conn.close.assert_called_once()

    def test_send_email_posts_text_payload(self):
        from github_usage.email_report import send_email

        conn = mock.Mock()
        resp = mock.Mock(status=201)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b'{"id":"email-id"}'
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn):
            send_email("resend-key", "reports@example.com", "to@example.com", "Subject", "Body")

        _, path = conn.request.call_args.args[:2]
        self.assertEqual(path, "/emails")
        payload = json.loads(conn.request.call_args.kwargs["body"])
        self.assertEqual(payload["to"], ["to@example.com"])
        self.assertEqual(payload["text"], "Body")
        conn.close.assert_called_once()

    def test_format_actions_section_renders_minutes_and_storage(self):
        from github_usage.email_report import _format_actions_section

        data = {
            "actions": {
                "minutes": 1250.0,
                "minutes_limit": 2000,
                "minutes_percent": 62.5,
                "storage_avg_mb": 312.0,
                "storage_limit_mb": 500,
                "storage_percent": 62.4,
            },
            "monthly_costs": {"actions": {"net": 1.23}},
        }
        lines = _format_actions_section(data)
        self.assertEqual(lines[0], "Actions")
        self.assertIn("1,250.0 / 2,000 (62.5%)", lines[1])
        self.assertIn("312.0 MB / 500 MB (62.4%)", lines[2])
        self.assertEqual(lines[3], "- Net cost: $1.2300")
        self.assertEqual(lines[4], "")
