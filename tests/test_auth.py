import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class AuthTests(unittest.TestCase):
    def test_cli_argument_wins_over_environment(self):
        from github_usage import auth

        with (
            mock.patch.object(auth.sys, "argv", ["github-usage", "arg-token"]),
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}),
        ):
            self.assertEqual(auth.resolve_token(), "arg-token")

    def test_environment_token_wins_over_gh_cli(self):
        from github_usage import auth

        with (
            mock.patch.object(auth.sys, "argv", ["github-usage"]),
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}),
            mock.patch.object(auth.subprocess, "run") as run,
        ):
            self.assertEqual(auth.resolve_token(), "env-token")
            run.assert_not_called()

    def test_github_cli_config_token_is_used_as_last_resort(self):
        from github_usage import auth

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".config" / "github-cli"
            config_dir.mkdir(parents=True)
            (config_dir / "github.yaml").write_text("oauth_token: config-token\n")

            with (
                mock.patch.object(auth.sys, "argv", ["github-usage"]),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(auth.subprocess, "run", side_effect=FileNotFoundError),
                mock.patch.object(auth.Path, "home", return_value=Path(tmpdir)),
            ):
                self.assertEqual(auth.resolve_token(), "config-token")

    def test_legacy_resolve_token_delegates_to_auth_behavior(self):
        from github_usage import auth, legacy

        with (
            mock.patch.object(auth.sys, "argv", ["github-usage"]),
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}),
        ):
            self.assertEqual(legacy.resolve_token(), "env-token")


if __name__ == "__main__":
    unittest.main()
