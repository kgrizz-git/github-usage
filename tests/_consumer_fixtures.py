"""Shared repo_consumers test fixtures (reduces cross-file duplication for Sonar)."""

from __future__ import annotations


def consumer_row(
    repo: str,
    *,
    minutes: float,
    gross: float,
    storage_avg_mb: float,
    visibility: str,
) -> dict:
    """Build one repo_consumers ranking row."""
    return {
        "repo": repo,
        "minutes": minutes,
        "gross": gross,
        "storage_avg_mb": storage_avg_mb,
        "visibility": visibility,
    }


def mixed_pub_priv_consumers(*, by_cost_mode: str = "pub_only") -> dict:
    """octocat/pub + octocat/priv rankings used across report/email/legacy tests."""
    pub = consumer_row(
        "octocat/pub",
        minutes=500.0,
        gross=5.0,
        storage_avg_mb=10.0,
        visibility="public",
    )
    priv = consumer_row(
        "octocat/priv",
        minutes=300.0,
        gross=3.0,
        storage_avg_mb=80.0,
        visibility="private",
    )
    result: dict = {
        "by_minutes": [pub, priv],
        "by_minutes_private": [priv],
        "by_storage": [priv, pub],
        "by_storage_private": [priv],
    }
    if by_cost_mode == "pub_only":
        result["by_cost"] = [pub]
    elif by_cost_mode == "both":
        result["by_cost"] = [pub, priv]
    else:
        result["by_cost"] = []
    return result


def mixed_pub_priv_repo_data() -> list:
    """repo_data 6-tuples matching mixed_pub_priv_consumers."""
    return [
        ("octocat/pub", 500.0, 0.0, 10.0, 5.0, {}),
        ("octocat/priv", 300.0, 0.0, 80.0, 3.0, {}),
    ]


def all_private_top_consumers(
    *,
    priv1_minutes: float = 500.0,
    priv2_minutes: float = 300.0,
    priv1_storage: float = 80.0,
    priv2_storage: float = 60.0,
    priv1_gross: float = 5.0,
    priv2_gross: float = 3.0,
) -> dict:
    """All-private rankings (redundant private-list skip cases)."""
    priv1 = consumer_row(
        "octocat/priv1",
        minutes=priv1_minutes,
        gross=priv1_gross,
        storage_avg_mb=priv1_storage,
        visibility="private",
    )
    priv2 = consumer_row(
        "octocat/priv2",
        minutes=priv2_minutes,
        gross=priv2_gross,
        storage_avg_mb=priv2_storage,
        visibility="private",
    )
    rows = [priv1, priv2]
    return {
        "by_minutes": list(rows),
        "by_minutes_private": list(rows),
        "by_storage": list(rows),
        "by_storage_private": list(rows),
        "by_cost": [],
    }


def all_private_repo_data(
    *,
    priv1_minutes: float = 500.0,
    priv2_minutes: float = 300.0,
    priv1_storage: float = 80.0,
    priv2_storage: float = 60.0,
    priv1_gross: float = 5.0,
    priv2_gross: float = 3.0,
) -> list:
    """repo_data 6-tuples matching all_private_top_consumers."""
    return [
        ("octocat/priv1", priv1_minutes, 0.0, priv1_storage, priv1_gross, {}),
        ("octocat/priv2", priv2_minutes, 0.0, priv2_storage, priv2_gross, {}),
    ]


def pub_priv_partial_consumers() -> dict:
    """Mixed visibility with private-only sublists (zero-division guard tests)."""
    pub = consumer_row(
        "octocat/pub",
        minutes=100.0,
        gross=1.0,
        storage_avg_mb=5.0,
        visibility="public",
    )
    priv = consumer_row(
        "octocat/priv",
        minutes=50.0,
        gross=0.5,
        storage_avg_mb=3.0,
        visibility="private",
    )
    return {
        "by_minutes": [pub, priv],
        "by_minutes_private": [priv],
        "by_storage": [pub],
        "by_storage_private": [priv],
    }


def findings_pub_priv_consumers() -> dict:
    """Pub + priv mix for private consumer findings (no by_cost)."""
    pub = consumer_row(
        "octocat/pub",
        minutes=500.0,
        gross=5.0,
        storage_avg_mb=10.0,
        visibility="public",
    )
    priv = consumer_row(
        "octocat/priv",
        minutes=300.0,
        gross=3.0,
        storage_avg_mb=80.0,
        visibility="private",
    )
    return {
        "by_minutes": [pub, priv],
        "by_minutes_private": [priv],
        "by_storage": [pub],
        "by_storage_private": [priv],
    }


def single_private_redundant_consumers() -> dict:
    """One private repo duplicated across all lists (HTML redundant-list tests)."""
    priv = consumer_row(
        "octocat/priv1",
        minutes=500.0,
        gross=5.0,
        storage_avg_mb=80.0,
        visibility="private",
    )
    return {
        "by_minutes": [priv],
        "by_cost": [],
        "by_minutes_private": [priv],
        "by_storage": [priv],
        "by_storage_private": [priv],
    }


def legacy_mixed_consumer_data(*, private_minutes: float = 400.0) -> dict:
    """Minimal legacy report dict with mixed pub/priv repo_consumers."""
    return {
        "actions": {"private_minutes": private_minutes},
        "repo_consumers": mixed_pub_priv_consumers(by_cost_mode="pub_only"),
        "repo_actions": [],
        "storage_analysis": {"repos": []},
        "artifact_storage": {},
    }


def legacy_all_private_consumer_data(*, private_minutes: float = 800.0) -> dict:
    """Legacy report dict with all-private redundant repo_consumers."""
    return {
        "actions": {"private_minutes": private_minutes},
        "repo_consumers": all_private_top_consumers(),
        "repo_actions": [],
        "storage_analysis": {"repos": []},
        "artifact_storage": {},
    }
