import unittest


class LegacyCompatTests(unittest.TestCase):
    def test_legacy_reexports_existing_public_names(self):
        from github_usage import legacy

        self.assertEqual(legacy.GitHubAPI.__name__, "GitHubAPI")
        self.assertTrue(callable(legacy.resolve_token))
        self.assertTrue(callable(legacy.get_actions_per_repo))
        self.assertTrue(callable(legacy.main))
