"""Tests for CLI argument parsers."""

from __future__ import annotations

import unittest

from github_usage.cli_parsers import _email_parser, _legacy_parser


class EmailParserTests(unittest.TestCase):
    def test_include_forecast_flags(self):
        parser = _email_parser()
        args = parser.parse_args(["--include-forecast"])
        self.assertTrue(args.include_forecast)

        args = parser.parse_args(["--no-include-forecast"])
        self.assertTrue(args.no_include_forecast)

    def test_premium_requests_limit(self):
        parser = _email_parser()
        args = parser.parse_args(["--premium-requests-limit", "10000"])
        self.assertEqual(args.premium_requests_limit, 10000.0)

    def test_premium_requests_limit_defaults_to_none(self):
        parser = _email_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.premium_requests_limit)

    def test_email_only_public_and_only_private_mutually_exclusive(self):
        parser = _email_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--only-public", "--only-private"])

    def test_legacy_only_public_and_only_private_mutually_exclusive(self):
        parser = _legacy_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--only-public", "--only-private"])

    def test_email_only_public_flag(self):
        parser = _email_parser()
        args = parser.parse_args(["--only-public"])
        self.assertTrue(args.only_public)
        self.assertFalse(args.only_private)


if __name__ == "__main__":
    unittest.main()
