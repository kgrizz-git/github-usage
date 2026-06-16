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
