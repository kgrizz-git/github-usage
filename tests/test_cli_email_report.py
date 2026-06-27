"""Tests for cli_email_report helpers."""

from __future__ import annotations

import argparse
import os
import unittest
from unittest import mock

from github_usage.cli_email_report import _send_email


class SendEmailTests(unittest.TestCase):
    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(timeout=30.0, max_retries=3)

    def test_uses_explicit_parameters(self):
        with (
            mock.patch("github_usage.cli_email_report.email_report.send_email") as send_email,
            mock.patch.dict(
                os.environ,
                {
                    "RESEND_API_KEY": "re_key",
                    "RESEND_FROM": "from@example.com",
                    "REPORT_EMAIL": "env@example.com",
                    "REPORT_SUBJECT": "Env Subject",
                },
                clear=True,
            ),
            mock.patch("builtins.print"),
        ):
            _send_email(
                self._args(),
                "body",
                None,
                "octocat",
                "2026-06-27T00:00:00Z",
                subject="Custom Subject",
                recipient="to@example.com",
                from_addr="override@example.com",
            )
        send_email.assert_called_once_with(
            "re_key",
            "override@example.com",
            "to@example.com",
            "Custom Subject",
            "body",
            html=None,
            timeout=30.0,
            max_retries=3,
        )

    def test_falls_back_to_environment(self):
        with (
            mock.patch("github_usage.cli_email_report.email_report.send_email") as send_email,
            mock.patch(
                "github_usage.cli_email_report.email_report.default_subject",
                return_value="Default Subject",
            ),
            mock.patch.dict(
                os.environ,
                {
                    "RESEND_API_KEY": "re_key",
                    "RESEND_FROM": "from@example.com",
                    "REPORT_EMAIL": "env@example.com",
                },
                clear=True,
            ),
            mock.patch("builtins.print"),
        ):
            _send_email(self._args(), "body", None, "octocat", "2026-06-27T00:00:00Z")
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args[0][2], "env@example.com")
        self.assertEqual(send_email.call_args[0][3], "Default Subject")
