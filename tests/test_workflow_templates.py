import plistlib
import stat
import unittest
from pathlib import Path


class WorkflowTemplateTests(unittest.TestCase):
    def test_email_report_workflow_uses_safe_secret_names_and_dispatch_inputs(self):
        workflow = Path(".github/workflows/email-report.yml").read_text()

        self.assertIn("GH_USAGE_TOKEN", workflow)
        self.assertNotIn("secrets.GITHUB_TOKEN", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("include_consumers:", workflow)
        self.assertIn("include_artifact_storage:", workflow)
        self.assertIn("include_release_assets:", workflow)
        self.assertIn("only_public:", workflow)
        self.assertIn("only_private:", workflow)
        self.assertIn("--only-public", workflow)

    def test_checked_in_workflow_and_template_use_only_recipient_secret(self):
        for name in ("email-report.yml", "email-report.yml.template"):
            with self.subTest(file=name):
                workflow = (Path(".github/workflows") / name).read_text()
                self.assertIn("REPORT_EMAIL: ${{ secrets.REPORT_EMAIL }}", workflow)
                self.assertNotIn("inputs.report_email", workflow)
                self.assertNotIn("      report_email:", workflow)

    def test_launchd_email_report_runs_monday_morning(self):
        plist_path = Path("launchd/com.github.github-usage.email-report.plist")
        script_path = Path("scripts/send-email-report.sh")

        self.assertTrue(script_path.is_file())
        self.assertTrue(script_path.stat().st_mode & stat.S_IXUSR)

        payload = plistlib.loads(plist_path.read_bytes())
        interval = payload["StartCalendarInterval"]
        self.assertEqual(interval["Weekday"], 1)
        self.assertEqual(interval["Hour"], 9)
        self.assertEqual(interval["Minute"], 0)
        self.assertIn("send-email-report.sh", payload["ProgramArguments"][0])
