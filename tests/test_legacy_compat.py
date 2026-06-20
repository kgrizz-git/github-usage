import unittest


class LegacyCompatTests(unittest.TestCase):
    def test_legacy_reexports_existing_public_names(self):
        from github_usage import legacy

        self.assertEqual(legacy.GitHubAPI.__name__, "GitHubAPI")
        self.assertTrue(callable(legacy.resolve_token))
        self.assertTrue(callable(legacy.get_actions_per_repo))
        self.assertTrue(callable(legacy.main))

    @unittest.mock.patch("github_usage.legacy_report.GitHubAPI")
    @unittest.mock.patch("github_usage.legacy_report.resolve_token", return_value="fake")
    @unittest.mock.patch("github_usage.legacy_report.check_user_scope", return_value=False)
    def test_legacy_report_passes_timeout_and_max_retries(
        self, mock_check, mock_resolve, mock_api_class
    ):
        import contextlib

        from github_usage import legacy_report

        with contextlib.suppress(SystemExit):
            legacy_report.main(timeout=42.0, max_retries=5)

        mock_api_class.assert_called_once_with("fake", timeout=42.0, max_retries=5)
