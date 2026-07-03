"""Tests for on-disk report data caching."""

from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from github_usage.report_cache import (
    cache_entry_path,
    email_cache_params,
    is_cache_fresh,
    legacy_cache_params,
    load_cache_settings,
    load_cached_report,
    resolve_cache_max_age,
    store_cached_report,
)
from github_usage.setup_config import SetupPaths


def _paths(root: Path) -> SetupPaths:
    return SetupPaths.from_root(root)


class ReportCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._cache_env = unittest.mock.patch.dict(
            os.environ, {"GITHUB_USAGE_DISABLE_CACHE": "0"}, clear=False
        )
        self._cache_env.start()

    def tearDown(self) -> None:
        self._cache_env.stop()

    def test_store_and_load_fresh_legacy_cache(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            token = "fake-token"
            params = legacy_cache_params(max_repos=100)
            data = {"username": "octocat", "actions": {"minutes": 1.0}}
            store_cached_report(
                paths,
                kind="legacy",
                token=token,
                params=params,
                username="octocat",
                data=data,
                cached_at=datetime.now(tz=UTC),
            )
            loaded, username, hit = load_cached_report(
                paths,
                kind="legacy",
                token=token,
                params=params,
                max_age_seconds=3600,
            )
            self.assertTrue(hit.from_cache)
            self.assertEqual(username, "octocat")
            self.assertEqual(loaded, data)

    def test_refresh_bypasses_cache(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            token = "fake-token"
            params = legacy_cache_params(max_repos=50)
            store_cached_report(
                paths,
                kind="legacy",
                token=token,
                params=params,
                username="octocat",
                data={"value": 1},
            )
            loaded, _username, hit = load_cached_report(
                paths,
                kind="legacy",
                token=token,
                params=params,
                max_age_seconds=3600,
                refresh=True,
            )
            self.assertFalse(hit.from_cache)
            self.assertIsNone(loaded)

    def test_expired_cache_is_miss(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            token = "fake-token"
            params = email_cache_params(
                include_actions=True,
                include_copilot=True,
                include_lfs=True,
                include_consumers=False,
                include_artifact_storage=False,
                include_release_assets=False,
                max_repos=100,
                warn_over=None,
            )
            old = datetime.now(tz=UTC) - timedelta(hours=2)
            store_cached_report(
                paths,
                kind="email",
                token=token,
                params=params,
                username="octocat",
                data={"value": 1},
                cached_at=old,
            )
            loaded, _username, hit = load_cached_report(
                paths,
                kind="email",
                token=token,
                params=params,
                max_age_seconds=3600,
            )
            self.assertFalse(hit.from_cache)
            self.assertIsNone(loaded)

    def test_cache_disabled_when_max_age_zero(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            token = "fake-token"
            params = legacy_cache_params(max_repos=100)
            store_cached_report(
                paths,
                kind="legacy",
                token=token,
                params=params,
                username="octocat",
                data={"value": 1},
            )
            loaded, _username, hit = load_cached_report(
                paths,
                kind="legacy",
                token=token,
                params=params,
                max_age_seconds=0,
            )
            self.assertFalse(hit.from_cache)
            self.assertIsNone(loaded)

    def test_different_params_use_different_cache_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            token = "fake-token"
            params_a = legacy_cache_params(max_repos=100)
            params_b = legacy_cache_params(max_repos=50)
            path_a = cache_entry_path(paths, kind="legacy", token=token, params=params_a)
            path_b = cache_entry_path(paths, kind="legacy", token=token, params=params_b)
            self.assertNotEqual(path_a, path_b)

    def test_load_cache_settings_from_config_toml(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            paths.config_dir.mkdir(parents=True)
            paths.config_file.write_text(
                "[cache]\nmax_age_seconds = 120\n",
                encoding="utf-8",
            )
            settings = load_cache_settings(paths)
            self.assertEqual(settings.max_age_seconds, 120)
            self.assertEqual(resolve_cache_max_age(paths), 120)

    def test_cache_disabled_via_environment(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            token = "fake-token"
            params = legacy_cache_params(max_repos=100)
            with unittest.mock.patch.dict(os.environ, {"GITHUB_USAGE_DISABLE_CACHE": "1"}):
                store_cached_report(
                    paths,
                    kind="legacy",
                    token=token,
                    params=params,
                    username="octocat",
                    data={"value": 1},
                )
                loaded, _username, hit = load_cached_report(
                    paths,
                    kind="legacy",
                    token=token,
                    params=params,
                    max_age_seconds=3600,
                )
            self.assertFalse(hit.from_cache)
            self.assertIsNone(loaded)

    def test_is_cache_fresh(self) -> None:
        now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
        cached_at = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        self.assertTrue(is_cache_fresh(cached_at, 3600, now=now))
        self.assertFalse(is_cache_fresh(cached_at, 900, now=now))
