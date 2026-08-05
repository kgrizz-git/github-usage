import json
import unittest
from pathlib import Path
from unittest import mock

from tests._consumer_fixtures import (
    all_private_top_consumers,
    mixed_pub_priv_consumers,
    single_private_redundant_consumers,
)

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

        from github_usage._email_report_common import _generated_line

        today_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        for value in (None, "", "not-an-iso-string"):
            line = _generated_line(value)
            self.assertIn(today_prefix, line)
            self.assertNotIn("None", line)
            self.assertFalse(line.endswith(" "))
            self.assertTrue(line.startswith("Generated: "))

    def test_generated_line_renders_valid_iso_string(self):
        from github_usage._email_report_common import _generated_line

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
        from github_usage.email_report_text import _format_actions_section

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

    def test_format_html_report_renders_html_sections(self):
        from github_usage.email_report import format_html_report

        data = json.loads((FIXTURES / "email_report_data.json").read_text())
        html = format_html_report(data)
        self.assertIn("GitHub Usage Report for octocat", html)
        self.assertIn("Actions", html)
        self.assertIn("Copilot Premium Requests", html)
        self.assertIn("Monthly Cost Estimate", html)
        self.assertIn("Top Repositories by Actions Minutes", html)
        self.assertIn("Top Repositories by Actions Cost", html)
        self.assertIn("Actions Artifact Storage", html)
        self.assertIn("Release Asset Inventory", html)
        self.assertIn("Key Insights", html)
        self.assertIn("Unavailable Data", html)
        self.assertIn("octocat/api", html)

    def test_format_html_report_contains_valid_html_structure(self):
        from github_usage.email_report import format_html_report

        data = json.loads((FIXTURES / "email_report_data.json").read_text())
        html = format_html_report(data)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="en">', html)
        self.assertIn("<head>", html)
        self.assertIn('<meta charset="utf-8">', html)
        self.assertIn("<title>GitHub Usage Report</title>", html)
        self.assertIn("<style>", html)
        self.assertIn("<body>", html)
        self.assertTrue(html.rstrip().endswith("</html>"))

    def test_format_html_report_renders_minimal_data(self):
        from datetime import UTC, datetime

        from github_usage.email_report import format_html_report

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
        html = format_html_report(data)
        today_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        self.assertIn(today_prefix, html)
        self.assertNotIn("Generated: None", html)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertTrue(html.rstrip().endswith("</html>"))

    def test_format_html_report_escapes_special_chars(self):
        from github_usage.email_report import format_html_report

        data = {
            "username": "<octo&cat>",
            "generated_at": None,
            "warnings": ["rate <0.5% & stable", "uses \"double\" and 'single' quotes"],
            "errors": {},
            "actions": None,
            "copilot": None,
            "git_lfs": None,
            "monthly_costs": None,
            "repo_consumers": {
                "by_minutes": [
                    {"repo": "org/foo&bar", "minutes": 1.0, "gross": 0.0, "storage_avg_mb": 0.0}
                ],
                "by_cost": [],
            },
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": ['<b>bold</b> insight with & and "quotes"'],
        }
        html = format_html_report(data)
        self.assertIn("&lt;octo&amp;cat&gt;", html)
        self.assertIn("org/foo&amp;bar", html)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt; insight with &amp; and &quot;quotes&quot;", html)
        self.assertIn("rate &lt;0.5% &amp; stable", html)
        self.assertIn("&quot;double&quot; and &#x27;single&#x27; quotes", html)
        self.assertNotIn("<octo&cat>", html)
        self.assertNotIn("<b>bold</b> insight", html)

    def test_format_html_report_well_formed_html(self):
        from html.parser import HTMLParser

        from github_usage.email_report import format_html_report

        void_elements = frozenset(
            {
                "area",
                "base",
                "br",
                "col",
                "embed",
                "hr",
                "img",
                "input",
                "link",
                "meta",
                "source",
                "track",
                "wbr",
            }
        )

        class _WellFormedHTMLValidator(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.stack: list[str] = []
                self.errors: list[str] = []

            def handle_starttag(self, tag, attrs):
                if tag not in void_elements:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if tag in void_elements:
                    return
                if not self.stack:
                    self.errors.append(f"Unexpected close tag: </{tag}>")
                    return
                expected = self.stack.pop()
                if expected != tag:
                    self.errors.append(f"Mismatched tag: expected </{expected}>, got </{tag}>")

        data = json.loads((FIXTURES / "email_report_data.json").read_text())
        html = format_html_report(data)
        validator = _WellFormedHTMLValidator()
        validator.feed(html)
        self.assertEqual(validator.errors, [], msg=f"HTML parse errors: {validator.errors}")
        self.assertEqual(validator.stack, [], msg=f"Unclosed tags: {validator.stack}")

    def test_section_html_formatters_order_matches_text_formatters(self):
        from github_usage import email_report_html, email_report_text

        text_formatters = email_report_text._SECTION_FORMATTERS
        html_formatters = email_report_html._SECTION_HTML_FORMATTERS
        self.assertEqual(len(text_formatters), len(html_formatters))
        for text_fn, html_fn in zip(text_formatters, html_formatters, strict=False):
            text_name = text_fn.__name__
            expected_html_name = "_format_html_" + text_name[len("_format_") :]
            self.assertEqual(html_fn.__name__, expected_html_name)

    def test_send_email_posts_html_payload_when_provided(self):
        from github_usage.email_report import send_email

        conn = mock.Mock()
        resp = mock.Mock(status=201)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b'{"id":"email-id"}'
        conn.getresponse.return_value = resp

        html_body = "<html><body>HTML</body></html>"
        with mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn):
            send_email(
                "resend-key",
                "reports@example.com",
                "to@example.com",
                "Subject",
                "Plain body",
                html=html_body,
            )

        _, path = conn.request.call_args.args[:2]
        self.assertEqual(path, "/emails")
        payload = json.loads(conn.request.call_args.kwargs["body"])
        self.assertEqual(payload["to"], ["to@example.com"])
        self.assertEqual(payload["from"], "reports@example.com")
        self.assertEqual(payload["subject"], "Subject")
        self.assertEqual(payload["text"], "Plain body")
        self.assertEqual(payload["html"], html_body)
        conn.close.assert_called_once()

    def test_send_email_posts_text_only_when_html_none(self):
        from github_usage.email_report import send_email

        conn = mock.Mock()
        resp = mock.Mock(status=201)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b'{"id":"email-id"}'
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn):
            send_email(
                "resend-key",
                "reports@example.com",
                "to@example.com",
                "Subject",
                "Plain body",
                html=None,
            )

        payload = json.loads(conn.request.call_args.kwargs["body"])
        self.assertNotIn("html", payload)
        self.assertEqual(payload["text"], "Plain body")
        self.assertEqual(payload["to"], ["to@example.com"])
        conn.close.assert_called_once()

    def test_format_report_email_includes_forecast(self):
        from datetime import date

        from github_usage.email_report import format_report_email

        data = {
            "username": "octocat",
            "generated_at": None,
            "warnings": [],
            "errors": {},
            "actions": {
                "minutes": 1000.0,
                "minutes_limit": 2000,
                "minutes_percent": 50.0,
                "storage_avg_mb": 250.0,
                "storage_limit_mb": 500,
                "storage_percent": 50.0,
            },
            "copilot": {"total_requests": 100.0},
            "git_lfs": None,
            "monthly_costs": {"total": {"gross": 0.0, "discount": 0.0, "net": 0.0}},
            "repo_consumers": None,
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": [],
        }
        body = format_report_email(
            data, premium_requests_limit=1000.0, reference_date=date(2026, 7, 15)
        )
        self.assertIn("Monthly Forecast", body)
        self.assertIn("Actions Minutes", body)
        self.assertIn("Storage (avg MB)", body)
        self.assertIn("Premium Requests", body)
        self.assertIn("day 15 of 31", body)

    def test_format_report_email_omits_forecast_before_day_3(self):
        from datetime import date

        from github_usage.email_report import format_report_email

        data = {
            "username": "octocat",
            "generated_at": None,
            "warnings": [],
            "errors": {},
            "actions": {"minutes": 100.0, "storage_avg_mb": 50.0},
            "copilot": {"total_requests": 10.0},
            "git_lfs": None,
            "monthly_costs": {"total": {"gross": 0.0, "discount": 0.0, "net": 0.0}},
            "repo_consumers": None,
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": [],
        }
        body = format_report_email(
            data, premium_requests_limit=1000.0, reference_date=date(2026, 7, 2)
        )
        self.assertNotIn("Monthly Forecast", body)

    def test_format_report_email_reference_date_overrides_generated_at(self):
        from datetime import date

        from github_usage.email_report import format_report_email

        data = {
            "username": "octocat",
            "generated_at": "2026-01-15T00:00:00Z",
            "warnings": [],
            "errors": {},
            "actions": {"minutes": 100.0, "storage_avg_mb": 50.0},
            "copilot": {"total_requests": 10.0},
            "git_lfs": None,
            "monthly_costs": {"total": {"gross": 0.0, "discount": 0.0, "net": 0.0}},
            "repo_consumers": None,
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": [],
        }
        body = format_report_email(
            data, premium_requests_limit=None, reference_date=date(2026, 7, 20)
        )
        self.assertIn("day 20 of 31", body)

    def test_format_report_email_premium_limit_controls_run_out(self):
        from datetime import date

        from github_usage.email_report import format_report_email

        data = {
            "username": "octocat",
            "generated_at": None,
            "warnings": [],
            "errors": {},
            "actions": {"minutes": 100.0, "storage_avg_mb": 50.0},
            "copilot": {"total_requests": 500.0},
            "git_lfs": None,
            "monthly_costs": {"total": {"gross": 0.0, "discount": 0.0, "net": 0.0}},
            "repo_consumers": None,
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": [],
        }
        body_with_limit = format_report_email(
            data, premium_requests_limit=1000.0, reference_date=date(2026, 7, 15)
        )
        self.assertIn("1,000", body_with_limit)
        self.assertRegex(body_with_limit, r"Premium Requests\s+.*\s+.*\s+1,000\s+day")

        body_without_limit = format_report_email(
            data, premium_requests_limit=None, reference_date=date(2026, 7, 15)
        )
        self.assertIn("Premium Requests", body_without_limit)
        self.assertRegex(body_without_limit, r"Premium Requests\s+.*\s+.*\s+--")

    def test_format_html_report_includes_forecast(self):
        from datetime import date

        from github_usage.email_report import format_html_report

        data = {
            "username": "octocat",
            "generated_at": None,
            "warnings": [],
            "errors": {},
            "actions": {"minutes": 100.0, "storage_avg_mb": 50.0},
            "copilot": {"total_requests": 10.0},
            "git_lfs": None,
            "monthly_costs": {"total": {"gross": 0.0, "discount": 0.0, "net": 0.0}},
            "repo_consumers": None,
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": [],
        }
        html = format_html_report(
            data, premium_requests_limit=1000.0, reference_date=date(2026, 7, 15)
        )
        self.assertIn("Monthly Forecast", html)
        self.assertIn("Day 15 of 31", html)
        self.assertIn("Actions Minutes", html)

    def test_billing_context_note_in_text_email(self):
        from github_usage.email_report_text import _format_billing_context_section

        lines = _format_billing_context_section({})
        self.assertEqual(lines[0], "Billing Note")
        self.assertIn("free for public repositories", lines[1])
        self.assertIn("monthly quota", lines[2])
        self.assertIn("docs.github.com", lines[3])

    def test_billing_context_note_in_html_email(self):
        from github_usage.email_report_html import _format_html_billing_context_section

        parts = _format_html_billing_context_section({})
        self.assertIn("<h2>Billing Note</h2>", parts)
        joined = "\n".join(parts)
        self.assertIn("free for public repositories", joined)
        self.assertIn("monthly quota", joined)
        self.assertIn("docs.github.com", joined)

    def test_consumers_grouped_by_visibility_text(self):
        from github_usage.email_report_text import _format_consumers_section

        data = {
            "repo_consumers": {
                "by_minutes": [
                    {
                        "repo": "org/private",
                        "visibility": "private",
                        "minutes": 100.0,
                        "gross": 1.0,
                        "storage_avg_mb": 10.0,
                    },
                    {
                        "repo": "org/public",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                ],
                "by_cost": [
                    {
                        "repo": "org/private",
                        "visibility": "private",
                        "minutes": 100.0,
                        "gross": 1.0,
                        "storage_avg_mb": 10.0,
                    },
                    {
                        "repo": "org/public",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                ],
            }
        }
        lines = _format_consumers_section(data)
        text = "\n".join(lines)
        self.assertIn("Private Repos:", text)
        self.assertIn("Public Repos:", text)
        self.assertIn("org/private [private]", text)
        self.assertIn("org/public", text)
        self.assertNotIn("org/public [private]", text)

    def test_consumers_grouped_by_visibility_html(self):
        from github_usage.email_report_html import _format_html_consumers_section

        data = {
            "repo_consumers": {
                "by_minutes": [
                    {
                        "repo": "org/private",
                        "visibility": "private",
                        "minutes": 100.0,
                        "gross": 1.0,
                        "storage_avg_mb": 10.0,
                    },
                    {
                        "repo": "org/public",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                ],
                "by_cost": [
                    {
                        "repo": "org/private",
                        "visibility": "private",
                        "minutes": 100.0,
                        "gross": 1.0,
                        "storage_avg_mb": 10.0,
                    },
                    {
                        "repo": "org/public",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                ],
            }
        }
        parts = _format_html_consumers_section(data)
        joined = "\n".join(parts)
        self.assertIn("Private Repos:", joined)
        self.assertIn("Public Repos:", joined)
        self.assertIn("visibility-tag", joined)
        self.assertIn("org/private", joined)
        self.assertIn("org/public", joined)

    def test_single_visibility_no_group_headers_text(self):
        from github_usage.email_report_text import _format_consumers_section

        data = {
            "repo_consumers": {
                "by_minutes": [
                    {
                        "repo": "org/pub1",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                    {
                        "repo": "org/pub2",
                        "visibility": "public",
                        "minutes": 30.0,
                        "gross": 0.0,
                        "storage_avg_mb": 3.0,
                    },
                ],
                "by_cost": [],
            }
        }
        lines = _format_consumers_section(data)
        text = "\n".join(lines)
        self.assertNotIn("Private Repos:", text)
        self.assertNotIn("Public Repos:", text)

    def test_single_visibility_no_group_headers_html(self):
        from github_usage.email_report_html import _format_html_consumers_section

        data = {
            "repo_consumers": {
                "by_minutes": [
                    {
                        "repo": "org/pub1",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                ],
                "by_cost": [],
            }
        }
        parts = _format_html_consumers_section(data)
        joined = "\n".join(parts)
        self.assertNotIn("Private Repos:", joined)
        self.assertNotIn("Public Repos:", joined)

    def test_artifact_storage_grouped_by_visibility_text(self):
        from github_usage.email_report_text import _format_artifact_storage_section

        data = {
            "artifact_storage": {
                "top_repos": [
                    {"repo": "org/private", "visibility": "private", "artifact_bytes": 104857600},
                    {"repo": "org/public", "visibility": "public", "artifact_bytes": 52428800},
                ]
            }
        }
        lines = _format_artifact_storage_section(data)
        text = "\n".join(lines)
        self.assertIn("Private Repos:", text)
        self.assertIn("Public Repos:", text)

    def test_artifact_storage_grouped_by_visibility_html(self):
        from github_usage.email_report_html import _format_html_artifact_storage_section

        data = {
            "artifact_storage": {
                "top_repos": [
                    {"repo": "org/private", "visibility": "private", "artifact_bytes": 104857600},
                    {"repo": "org/public", "visibility": "public", "artifact_bytes": 52428800},
                ]
            }
        }
        parts = _format_html_artifact_storage_section(data)
        joined = "\n".join(parts)
        self.assertIn("Private Repos:", joined)
        self.assertIn("Public Repos:", joined)

    def test_release_assets_grouped_by_visibility_text(self):
        from github_usage.email_report_text import _format_release_assets_section

        data = {
            "release_assets": {
                "top_repos": [
                    {
                        "repo": "org/private",
                        "visibility": "private",
                        "release_asset_bytes": 104857600,
                    },
                    {"repo": "org/public", "visibility": "public", "release_asset_bytes": 52428800},
                ]
            }
        }
        lines = _format_release_assets_section(data)
        text = "\n".join(lines)
        self.assertIn("Private Repos:", text)
        self.assertIn("Public Repos:", text)

    def test_release_assets_grouped_by_visibility_html(self):
        from github_usage.email_report_html import _format_html_release_assets_section

        data = {
            "release_assets": {
                "top_repos": [
                    {
                        "repo": "org/private",
                        "visibility": "private",
                        "release_asset_bytes": 104857600,
                    },
                    {"repo": "org/public", "visibility": "public", "release_asset_bytes": 52428800},
                ]
            }
        }
        parts = _format_html_release_assets_section(data)
        joined = "\n".join(parts)
        self.assertIn("Private Repos:", joined)
        self.assertIn("Public Repos:", joined)

    def _mixed_visibility_repo_consumers(self) -> dict:
        return mixed_pub_priv_consumers(by_cost_mode="both")

    def test_consumers_section_includes_storage_and_private_lists_text(self):
        from github_usage.email_report_text import _format_consumers_section

        data = {"repo_consumers": self._mixed_visibility_repo_consumers()}
        text = "\n".join(_format_consumers_section(data))
        self.assertIn("Top Repositories by Actions Storage (all)", text)
        self.assertIn("Top Private Repositories by Actions Minutes", text)
        self.assertIn("Top Private Repositories by Actions Storage", text)
        self.assertIn("octocat/priv [private]", text)
        self.assertIn("80.0 MB avg storage", text)

    def test_consumers_section_skips_redundant_private_lists_text(self):
        from github_usage.email_report_text import _format_consumers_section

        text = "\n".join(_format_consumers_section({"repo_consumers": all_private_top_consumers()}))
        self.assertIn("Top Repositories by Actions Storage (all)", text)
        self.assertNotIn("Top Private Repositories by Actions Minutes", text)
        self.assertNotIn("Top Private Repositories by Actions Storage", text)

    def test_consumers_section_unchanged_without_new_keys_text(self):
        from github_usage.email_report_text import _format_consumers_section

        data = {
            "repo_consumers": {
                "by_minutes": [
                    {
                        "repo": "org/pub",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                ],
                "by_cost": [],
            }
        }
        text = "\n".join(_format_consumers_section(data))
        self.assertIn("Top Repositories by Actions Minutes", text)
        self.assertNotIn("Top Repositories by Actions Storage (all)", text)
        self.assertNotIn("Top Private Repositories by Actions Minutes", text)
        self.assertNotIn("Top Private Repositories by Actions Storage", text)

    def test_consumers_section_includes_storage_and_private_lists_html(self):
        from github_usage.email_report_html import _format_html_consumers_section

        data = {"repo_consumers": self._mixed_visibility_repo_consumers()}
        joined = "\n".join(_format_html_consumers_section(data))
        self.assertIn("Top Repositories by Actions Storage (all)", joined)
        self.assertIn("Top Private Repositories by Actions Minutes", joined)
        self.assertIn("Top Private Repositories by Actions Storage", joined)
        self.assertIn("octocat/priv", joined)
        self.assertIn("80.0 MB avg", joined)

    def test_consumers_section_skips_redundant_private_lists_html(self):
        from github_usage.email_report_html import _format_html_consumers_section

        joined = "\n".join(
            _format_html_consumers_section({"repo_consumers": single_private_redundant_consumers()})
        )
        self.assertIn("Top Repositories by Actions Storage (all)", joined)
        self.assertNotIn("Top Private Repositories by Actions Minutes", joined)
        self.assertNotIn("Top Private Repositories by Actions Storage", joined)

    def test_consumers_section_unchanged_without_new_keys_html(self):
        from github_usage.email_report_html import _format_html_consumers_section

        data = {
            "repo_consumers": {
                "by_minutes": [
                    {
                        "repo": "org/pub",
                        "visibility": "public",
                        "minutes": 50.0,
                        "gross": 0.0,
                        "storage_avg_mb": 5.0,
                    },
                ],
                "by_cost": [],
            }
        }
        joined = "\n".join(_format_html_consumers_section(data))
        self.assertIn("Top Repositories by Actions Minutes", joined)
        self.assertNotIn("Top Repositories by Actions Storage (all)", joined)
        self.assertNotIn("Top Private Repositories by Actions Minutes", joined)
        self.assertNotIn("Top Private Repositories by Actions Storage", joined)

    def test_html_table_helpers_live_in_dedicated_module(self):
        from github_usage import _email_report_html_tables as tables

        self.assertTrue(callable(tables.html_grouped_table))
        self.assertTrue(callable(tables.html_storage_row))


if __name__ == "__main__":
    unittest.main()
