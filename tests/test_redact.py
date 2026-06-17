import unittest

from github_usage.redact import (
    REDACT_AMOUNT,
    REDACT_EMAIL,
    REDACT_REPO,
    REDACT_USERNAME,
    redact_report_data,
    redact_text,
)
from tests.conftest import load_export_report_data


class RedactReportDataTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()

    def test_redacts_username(self):
        result = redact_report_data(self.data)
        self.assertEqual(result["username"], REDACT_USERNAME)

    def test_redacts_repo_names_in_consumers(self):
        result = redact_report_data(self.data)
        for entry in result["repo_consumers"]["by_minutes"]:
            self.assertEqual(entry["repo"], REDACT_REPO)
        for entry in result["repo_consumers"]["by_cost"]:
            self.assertEqual(entry["repo"], REDACT_REPO)

    def test_redacts_repo_names_in_artifact_and_release_storage(self):
        result = redact_report_data(self.data)
        for entry in result["artifact_storage"]["top_repos"]:
            self.assertEqual(entry["repo"], REDACT_REPO)
        for entry in result["release_assets"]["top_repos"]:
            self.assertEqual(entry["repo"], REDACT_REPO)

    def test_preserves_numeric_costs(self):
        result = redact_report_data(self.data)
        self.assertEqual(result["actions"]["minutes"], 1250.0)
        self.assertEqual(result["monthly_costs"]["actions"]["gross"], 6.1)
        self.assertEqual(result["api_estimate"]["core_limit"], 5000)

    def test_redacts_dollar_amounts_in_warning_strings(self):
        result = redact_report_data(self.data)
        for warning in result["warnings"]:
            self.assertNotIn("$31.42", warning)
            self.assertNotIn("$25.00", warning)
            self.assertIn(REDACT_AMOUNT, warning)

    def test_is_deep_copy(self):
        result = redact_report_data(self.data)
        result["actions"]["minutes"] = -1.0
        result["repo_consumers"]["by_minutes"].append({"repo": "leak", "minutes": 1.0})
        self.assertEqual(self.data["actions"]["minutes"], 1250.0)
        self.assertEqual(self.data["repo_consumers"]["by_minutes"][-1]["repo"], "octocat/web")

    def test_idempotent(self):
        once = redact_report_data(self.data)
        twice = redact_report_data(once)
        self.assertEqual(once, twice)


class RedactTextTests(unittest.TestCase):
    def test_redacts_email_addresses(self):
        out = redact_text("Contact me at user@example.com for details.")
        self.assertIn(REDACT_EMAIL, out)
        self.assertNotIn("user@example.com", out)

    def test_redacts_dollar_amounts(self):
        out = redact_text("Total cost is $31.42, threshold is $25.00.")
        self.assertIn(REDACT_AMOUNT, out)
        self.assertNotIn("$31.42", out)
        self.assertNotIn("$25.00", out)

    def test_does_not_redact_ordinary_words(self):
        out = redact_text("The copilot summary is on page 3.")
        self.assertEqual(out, "The copilot summary is on page 3.")

    def test_idempotent(self):
        text = "Email me at user@example.com or pay $10.00."
        once = redact_text(text)
        twice = redact_text(once)
        self.assertEqual(once, twice)

    def test_redacts_multiple_dollar_amounts(self):
        out = redact_text("Items cost $1,000.00 and $2,500.00.")
        self.assertEqual(out.count(REDACT_AMOUNT), 2)


if __name__ == "__main__":
    unittest.main()
