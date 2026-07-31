"""Tests for the Actions visibility split and runner-SKU classification."""

import unittest

from github_usage.usage_split import (
    classify_actions_sku,
    finalize_actions_split,
    flat_equivalent_gb_hours,
    is_standard_runner_sku,
    normalize_sku,
    split_rows_by_visibility,
    storage_allowance_gb_hours,
)


class IsStandardRunnerSkuTests(unittest.TestCase):
    def test_standard_spelled_out(self) -> None:
        for sku in (
            "actions_linux",
            "actions_linux_slim",
            "actions_linux_arm",
            "actions_windows",
            "actions_windows_arm",
            "actions_macos",
        ):
            self.assertTrue(is_standard_runner_sku(sku), sku)

    def test_actions_prefix_optional(self) -> None:
        self.assertTrue(is_standard_runner_sku("linux"))
        self.assertTrue(is_standard_runner_sku("linux_slim"))
        self.assertTrue(is_standard_runner_sku("windows"))
        self.assertTrue(is_standard_runner_sku("macos"))

    def test_larger_runner_skus_are_not_standard(self) -> None:
        for sku in (
            "linux_4_core",
            "windows_8_core",
            "macos_l",
            "linux_4_core_arm",
            "linux_4_core_gpu",
        ):
            self.assertFalse(is_standard_runner_sku(sku), sku)


class NormalizeSkuTests(unittest.TestCase):
    def test_strip_actions_prefix(self) -> None:
        self.assertEqual(normalize_sku("actions_linux"), "linux")
        self.assertEqual(normalize_sku("actions_linux_4_core_arm"), "linux_4_core_arm")

    def test_lowercase(self) -> None:
        self.assertEqual(normalize_sku("Actions_Linux"), "linux")

    def test_digit_word_boundary_defensive(self) -> None:
        self.assertEqual(normalize_sku("actions_linux_4core"), "linux_4_core")
        self.assertEqual(normalize_sku("linux_4core"), "linux_4_core")


class ClassifyActionsSkuTests(unittest.TestCase):
    def test_storage_unit(self) -> None:
        self.assertEqual(
            classify_actions_sku("anything", {"unitType": "gigabyte-hours"}), "storage"
        )

    def test_standard_compute(self) -> None:
        self.assertEqual(classify_actions_sku("actions_linux"), "standard")
        self.assertEqual(classify_actions_sku("actions_windows"), "standard")

    def test_larger_compute(self) -> None:
        self.assertEqual(classify_actions_sku("linux_4_core"), "larger")
        self.assertEqual(classify_actions_sku("windows_8_core", {"unitType": "minutes"}), "larger")

    def test_unknown_compute_role_is_larger(self) -> None:
        self.assertEqual(classify_actions_sku("mystery_sku"), "larger")
        # actions_cache_storage without an item dict is treated as larger by
        # the exclusion rule; with a gigabyte-hours item it is storage.
        self.assertEqual(classify_actions_sku("actions_cache_storage"), "larger")
        self.assertEqual(
            classify_actions_sku("actions_cache_storage", {"unitType": "gigabyte-hours"}),
            "storage",
        )


class SplitRowsByVisibilityTests(unittest.TestCase):
    def _row(
        self,
        repo: str,
        vis: str,
        minutes: float = 10.0,
        gb_hours: float = 0.5,
        sku: dict | None = None,
    ):
        row = {
            "repo": repo,
            "visibility": vis,
            "minutes": minutes,
            "storage_gb_hours": gb_hours,
        }
        if sku is not None:
            row["sku"] = sku
        return row

    def test_aggregates_minutes_storage_skus(self) -> None:
        rows = [
            self._row(
                "a",
                "private",
                minutes=100.0,
                gb_hours=1.0,
                sku={"actions_linux": {"unitType": "minutes"}},
            ),
            self._row(
                "b",
                "internal",
                minutes=50.0,
                gb_hours=2.0,
                sku={"actions_macos": {"unitType": "minutes"}},
            ),
            self._row(
                "c",
                "public",
                minutes=200.0,
                gb_hours=3.0,
                sku={"linux_4_core": {"unitType": "minutes"}},
            ),
        ]
        out = split_rows_by_visibility(rows)
        # internal folds into private (decisions #1)
        self.assertEqual(out["private"]["minutes"], 150.0)
        self.assertEqual(out["private"]["storage_gb_hours"], 3.0)
        self.assertEqual(out["public"]["minutes"], 200.0)
        self.assertEqual(out["public"]["storage_gb_hours"], 3.0)
        self.assertIn("actions_linux", out["private"]["skus"])
        self.assertIn("linux_4_core", out["public"]["skus"])

    def test_no_sku_key(self) -> None:
        rows = [self._row("a", "private", minutes=10.0), self._row("b", "public", minutes=20.0)]
        out = split_rows_by_visibility(rows, sku_key=None)
        self.assertNotIn("skus", out["private"])
        self.assertEqual(out["private"]["minutes"], 10.0)
        self.assertEqual(out["public"]["minutes"], 20.0)

    def test_alt_storage_key(self) -> None:
        rows = [
            {"visibility": "private", "minutes": 5.0, "storage_avg_mb": 12.5},
            {"visibility": "public", "minutes": 3.0, "storage_avg_mb": 6.25},
        ]
        out = split_rows_by_visibility(rows, storage_key="storage_avg_mb", sku_key=None)
        self.assertEqual(out["private"]["storage_avg_mb"], 12.5)
        self.assertEqual(out["public"]["storage_avg_mb"], 6.25)


class FinalizeActionsSplitTests(unittest.TestCase):
    def test_reconciles_positive_unattributed(self) -> None:
        split = {
            "private": {"minutes": 100.0, "storage_gb_hours": 1.0, "skus": {}},
            "public": {"minutes": 50.0, "storage_gb_hours": 0.5, "skus": {}},
        }
        out = finalize_actions_split(split, account_minutes=200.0, account_storage_gb_hours=5.0)
        self.assertEqual(out["private_minutes"], 100.0)
        self.assertEqual(out["public_minutes"], 50.0)
        self.assertEqual(out["unattributed_minutes"], 50.0)
        self.assertEqual(out["unattributed_storage_gb_hours"], 3.5)
        self.assertTrue(out["reconciled"])
        self.assertEqual(out["private_minutes_percent"], 5.0)
        self.assertFalse(out["filtered"])

    def test_clamps_negative_unattributed(self) -> None:
        split = {
            "private": {"minutes": 200.0, "storage_gb_hours": 5.0, "skus": {}},
            "public": {"minutes": 100.0, "storage_gb_hours": 1.0, "skus": {}},
        }
        out = finalize_actions_split(split, account_minutes=150.0, account_storage_gb_hours=3.0)
        self.assertEqual(out["unattributed_minutes"], 0.0)
        self.assertEqual(out["unattributed_storage_gb_hours"], 0.0)
        self.assertFalse(out["reconciled"])

    def test_larger_runner_skus_detected(self) -> None:
        split = {
            "private": {
                "minutes": 0.0,
                "storage_gb_hours": 0.0,
                "skus": {"linux_4_core": {"unitType": "minutes"}},
            },
            "public": {
                "minutes": 10.0,
                "storage_gb_hours": 0.0,
                "skus": {"linux_4_core_arm": {"unitType": "minutes"}},
            },
        }
        out = finalize_actions_split(split, account_minutes=10.0, account_storage_gb_hours=0.0)
        self.assertIn("linux_4_core", out["larger_runner_skus"])
        self.assertIn("linux_4_core_arm", out["larger_runner_skus"])

    def test_filtered_flag(self) -> None:
        split = {
            "private": {"minutes": 0.0, "storage_gb_hours": 0.0, "skus": {}},
            "public": {"minutes": 0.0, "storage_gb_hours": 0.0, "skus": {}},
        }
        out = finalize_actions_split(
            split, account_minutes=0.0, account_storage_gb_hours=0.0, filtered=True
        )
        self.assertTrue(out["filtered"])

    def test_custom_limit(self) -> None:
        split = {
            "private": {"minutes": 1000.0, "storage_gb_hours": 0.0, "skus": {}},
            "public": {"minutes": 0.0, "storage_gb_hours": 0.0, "skus": {}},
        }
        out = finalize_actions_split(
            split,
            account_minutes=1000.0,
            account_storage_gb_hours=0.0,
            private_minutes_limit=4000.0,
        )
        self.assertEqual(out["private_minutes_percent"], 25.0)


class StorageHelpersTests(unittest.TestCase):
    def test_allowance_30_31_28(self) -> None:
        self.assertAlmostEqual(storage_allowance_gb_hours(30), 360.0)
        self.assertAlmostEqual(storage_allowance_gb_hours(31), 372.0)
        self.assertAlmostEqual(storage_allowance_gb_hours(28), 336.0)

    def test_flat_equivalent(self) -> None:
        # 165.29 GB-hrs over 31 days -> 165.29 / (24*31)
        self.assertAlmostEqual(flat_equivalent_gb_hours(165.29, 31), 165.29 / (24 * 31), places=4)
        self.assertAlmostEqual(flat_equivalent_gb_hours(360.0, 30), 0.5, places=4)

    def test_flat_equivalent_zero_days(self) -> None:
        self.assertEqual(flat_equivalent_gb_hours(100.0, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
