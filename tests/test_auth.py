import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class AuthTests(unittest.TestCase):
    def test_cli_argument_wins_over_environment(self):
        from github_usage import legacy

        with mock.patch.object(legacy.sys, "argv", ["github-usage", "arg-token"]):
            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}):
                self.assertEqual(legacy.resolve_token(), "arg-token")

    def test_environment_token_wins_over_gh_cli(self):
        from github_usage import legacy

        with mock.patch.object(legacy.sys, "argv", ["github-usage"]):
            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}):
                with mock.patch.object(legacy.subprocess, "run") as run:
                    self.assertEqual(legacy.resolve_token(), "env-token")
                    run.assert_not_called()

    def test_github_cli_config_token_is_used_as_last_resort(self):
        from github_usage import legacy

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".config" / "github-cli"
            config_dir.mkdir(parents=True)
            (config_dir / "github.yaml").write_text("oauth_token: config-token\n")

            with mock.patch.object(legacy.sys, "argv", ["github-usage"]):
                with mock.patch.dict(os.environ, {}, clear=True):
                    with mock.patch.object(legacy.subprocess, "run", side_effect=FileNotFoundError):
                        with mock.patch.object(legacy.Path, "home", return_value=Path(tmpdir)):
                            self.assertEqual(legacy.resolve_token(), "config-token")


if __name__ == "__main__":
    unittest.main()
