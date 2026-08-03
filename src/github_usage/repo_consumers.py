"""Shared ranking helpers for repo-level Actions consumer data."""

from __future__ import annotations

_PRIVATE_VISIBILITIES = frozenset({"private", "internal"})


def _is_private_row(row: dict) -> bool:
    return row.get("visibility") in _PRIVATE_VISIBILITIES


def _sort_by_metric(rows: list[dict], metric: str, *, limit: int) -> list[dict]:
    """Sort rows by descending metric with deterministic repo tie-break."""
    return sorted(rows, key=lambda row: (-float(row[metric]), row["repo"]))[:limit]


def _sort_by_metric_legacy(rows: list[dict], metric: str, *, limit: int) -> list[dict]:
    """Preserve existing combined-list sort: metric only, no repo tie-break."""
    return sorted(rows, key=lambda row: row[metric], reverse=True)[:limit]


def build_consumer_rankings(rows: list[dict], *, limit: int) -> dict:
    """Rank consumer rows by minutes, gross, and storage — overall and private-only.

    Each row needs ``repo``, ``minutes``, ``gross``, ``storage_avg_mb``, ``visibility``.
    ``"internal"`` folds into private. Returns all five ranking keys (empty lists ok).
    Rows are not mutated. Sort: ``(-metric, repo)`` for new rankings; existing
    ``by_minutes`` / ``by_cost`` keep metric-only descending order.
    """
    private_rows = [row for row in rows if _is_private_row(row)]
    return {
        "by_minutes": _sort_by_metric_legacy(rows, "minutes", limit=limit),
        "by_cost": _sort_by_metric_legacy(rows, "gross", limit=limit),
        "by_storage": _sort_by_metric(rows, "storage_avg_mb", limit=limit),
        "by_minutes_private": _sort_by_metric(private_rows, "minutes", limit=limit),
        "by_storage_private": _sort_by_metric(private_rows, "storage_avg_mb", limit=limit),
    }


def private_list_is_redundant(combined: list, private: list) -> bool:
    """True when ``private`` is empty, or every row in ``combined`` is
    private/internal **and** ``len(private) <= len(combined)``.

    The length guard prevents skipping a longer private Top-N when the
    combined list is a shorter all-private Top-M (e.g. Top 5 vs Top 10).
    Renderers skip the private-only list when this returns True (constraint 2).
    """
    if not private:
        return True
    if len(private) > len(combined):
        return False
    return all(_is_private_row(row) for row in combined)
