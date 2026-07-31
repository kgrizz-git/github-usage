"""Shared private-usage / visibility helpers for report exports.

Keeps CSV, XLSX, and PDF writers from duplicating the same summary rows.
"""

from __future__ import annotations

from .usage_split import REPORT_SOURCES, classify_actions_sku


def has_visibility_split(actions: dict | None) -> bool:
    """True when the actions dict carries private/public split keys."""
    return bool(actions) and "private_minutes" in (actions or {})


def annotate_sku_name(sku: str, item: dict | None = None) -> str:
    """Append `` *`` for larger-runner compute SKUs."""
    if classify_actions_sku(str(sku), item if isinstance(item, dict) else None) == "larger":
        return f"{sku} *"
    return str(sku)


def visibility_summary_rows(actions: dict | None) -> list[list]:
    """Return CSV-style ``[label, value]`` rows for Actions Usage by Visibility."""
    if not has_visibility_split(actions):
        return []
    payload = actions if isinstance(actions, dict) else {}
    rows = [
        ["private_minutes", payload.get("private_minutes", 0.0)],
        ["private_minutes_limit", 2000],
        ["private_minutes_percent", payload.get("private_minutes_percent", 0.0)],
        ["public_minutes", payload.get("public_minutes", 0.0)],
        ["unattributed_minutes", payload.get("unattributed_minutes", 0.0)],
        ["private_storage_avg_mb", payload.get("private_storage_avg_mb", 0.0)],
        ["public_storage_avg_mb", payload.get("public_storage_avg_mb", 0.0)],
        ["private_storage_gb_hours", payload.get("private_storage_gb_hours", 0.0)],
        ["public_storage_gb_hours", payload.get("public_storage_gb_hours", 0.0)],
        ["unattributed_storage_gb_hours", payload.get("unattributed_storage_gb_hours", 0.0)],
    ]
    larger = payload.get("larger_runner_skus") or []
    if larger:
        rows.append(["larger_runner_skus", ", ".join(str(s) for s in larger)])
    return rows


def visibility_summary_label_values(actions: dict | None) -> list[tuple[str, str]]:
    """Return PDF-style ``(label, value)`` pairs for the visibility summary."""
    rows = visibility_summary_rows(actions)
    return [(str(label), str(value if value is not None else "")) for label, value in rows]


def storage_summary_label_values(storage_summary: dict | None) -> list[tuple[str, str]]:
    """Return PDF-style rows for the ``storage_summary`` framing block."""
    if not storage_summary:
        return []
    return [
        ("Private GB-hrs", str(storage_summary.get("private_gb_hours", ""))),
        ("Public GB-hrs", str(storage_summary.get("public_gb_hours", ""))),
        ("Unattributed GB-hrs", str(storage_summary.get("unattributed_gb_hours", ""))),
        ("Allowance GB-hrs", str(storage_summary.get("allowance_gb_hours", ""))),
        ("Private avg MB", str(storage_summary.get("private_avg_mb", ""))),
        ("Public avg MB", str(storage_summary.get("public_avg_mb", ""))),
        (
            "Retention default (days)",
            str(storage_summary.get("retention_default_days", 90)),
        ),
    ]


def annotated_sku_breakdown(sku_breakdown: dict | None) -> dict:
    """Return a copy of ``sku_breakdown`` with larger-runner SKU names marked ``*``."""
    out: dict = {}
    for sku, item in (sku_breakdown or {}).items():
        out[annotate_sku_name(str(sku), item if isinstance(item, dict) else None)] = item
    return out


def sources_rows(sources: dict | None = None) -> list[list]:
    """Return ``[name, url]`` rows for the Sources export section."""
    payload = sources or REPORT_SOURCES
    return [[key, url] for key, url in payload.items()]


def storage_analysis_export_rows(storage_analysis: dict | None) -> list[list]:
    """Header + rows for storage_analysis with artifact/release/expiry columns."""
    repos = (storage_analysis or {}).get("repos") or []
    if not repos:
        return []
    header = [
        "repo",
        "visibility",
        "artifact_storage_gb",
        "release_storage_gb",
        "total_storage_gb",
        "artifact_count",
        "expired_count",
        "expiring_soon_count",
        "earliest_expiry",
        "retention_days",
    ]
    rows = [header]
    for repo in repos:
        rows.append(
            [
                repo.get("name", ""),
                repo.get("visibility", ""),
                repo.get("artifact_storage_gb", ""),
                repo.get("release_storage_gb", ""),
                repo.get("total_storage", ""),
                repo.get("artifact_count", ""),
                repo.get("expired_count", ""),
                repo.get("expiring_soon_count", ""),
                repo.get("earliest_expiry", ""),
                repo.get("retention_days", ""),
            ]
        )
    return rows


def per_visibility_sku_rows(actions: dict | None) -> list[list]:
    """SKU × visibility table from ``actions['skus']`` when present."""
    if not actions:
        return []
    skus = actions.get("skus") or {}
    if not skus:
        return []
    rows = [["sku", "visibility", "grossQuantity", "grossAmount", "netAmount", "unitType"]]
    for vis in ("private", "public"):
        for sku, item in (skus.get(vis) or {}).items():
            if not isinstance(item, dict):
                continue
            rows.append(
                [
                    annotate_sku_name(str(sku), item),
                    vis,
                    item.get("grossQuantity", ""),
                    item.get("grossAmount", ""),
                    item.get("netAmount", ""),
                    item.get("unitType", ""),
                ]
            )
    return rows if len(rows) > 1 else []
