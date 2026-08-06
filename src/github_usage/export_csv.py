"""CSV writer for report exports.

Writes a single CSV file with multiple sections. Each section is preceded
by a header row of the form ``### SECTION_NAME ###`` (single cell, single
line, 3 hash chars per side). Within each section, data is written as
key-value rows or sub-tables.

Invariants:
- Always writes a UTF-8 BOM at the start of the file (Excel-on-Windows
  compatibility; trade-off accepted).
- ``None`` section values are coalesced to ``{}`` / ``[]`` so callers do
  not have to handle missing sections.
- ``None`` cell values are written as empty cells.
- A trailing empty row is appended for POSIX compliance.
"""

from __future__ import annotations

import csv

from .export_visibility import (
    VISIBILITY_SPLIT_KEYS,
    annotated_sku_breakdown,
    sources_rows,
    storage_analysis_export_rows,
    visibility_summary_rows,
)
from .report_forecast_data import build_report_forecast
from .visibility import repo_visibility


def write(
    data: dict,
    file_obj,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    **kwargs,
) -> None:
    """Write the report data dict as CSV to ``file_obj``."""
    del kwargs
    file_obj.write("\ufeff")
    writer = csv.writer(file_obj)
    _write_sections(
        writer,
        data,
        include_forecast=include_forecast,
        premium_requests_limit=premium_requests_limit,
    )
    writer.writerow([])


def _coerce_section(value, default):
    """Return ``value`` if it is a dict/list, else ``default`` (handles ``None``)."""
    if value is None:
        return default
    return value


def _write_sections(
    writer: csv.writer,  # type: ignore[type-arg]
    data: dict,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
) -> None:
    _write_section_header(writer, "Report Metadata")
    _write_kv(writer, data, ["username", "period", "generated_at"])

    if include_forecast:
        _write_forecast_section(writer, data, premium_requests_limit=premium_requests_limit)

    _write_warnings_section(writer, data)
    _write_actions_section(writer, data)
    _write_storage_summary_section(writer, data)
    _write_copilot_section(writer, data)
    _write_git_lfs_section(writer, data)
    _write_monthly_costs_section(writer, data)
    _write_repo_consumers_sections(writer, data)
    _write_artifact_storage_section(writer, data)
    _write_storage_analysis_section(writer, data)
    _write_release_assets_section(writer, data)
    _write_key_insights_section(writer, data)
    _write_unavailable_data_section(writer, data)
    _write_sources_section(writer, data)


def _write_warnings_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Warnings")
    for warning in data.get("warnings") or []:
        writer.writerow([warning])


def _write_actions_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Actions Usage")
    actions = _coerce_section(data.get("actions"), {})
    for key, value in actions.items():
        if key in {"sku_breakdown", "skus"} | VISIBILITY_SPLIT_KEYS:
            continue
        writer.writerow([key, value])
    sku = annotated_sku_breakdown(actions.get("sku_breakdown") or {})
    if sku:
        _write_nested(writer, "sku_breakdown", "sku", sku)
        if any(str(name).endswith(" *") for name in sku):
            writer.writerow(
                [
                    "*",
                    "GitHub-hosted larger runner - always billed, not covered by free tier",
                ]
            )

    vis_rows = visibility_summary_rows(actions)
    if vis_rows:
        _write_section_header(writer, "Actions Usage by Visibility")
        for row in vis_rows:
            writer.writerow(row)


def _write_storage_summary_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    storage_summary = _coerce_section(data.get("storage_summary"), {})
    if storage_summary:
        _write_section_header(writer, "Storage Summary")
        for key, value in storage_summary.items():
            writer.writerow([key, value])


def _write_copilot_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Copilot Usage")
    copilot = _coerce_section(data.get("copilot"), {})
    for key, value in copilot.items():
        if key == "by_model":
            _write_copilot_by_model(writer, value)
        else:
            writer.writerow([key, value])


def _write_git_lfs_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Git LFS")
    git_lfs = _coerce_section(data.get("git_lfs"), {})
    for key, value in git_lfs.items():
        writer.writerow([key, value])


def _write_monthly_costs_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Monthly Costs")
    costs = _coerce_section(data.get("monthly_costs"), {})
    for category, amounts in costs.items():
        if isinstance(amounts, dict):
            writer.writerow([f"{category}_gross", amounts.get("gross", "")])
            writer.writerow([f"{category}_discount", amounts.get("discount", "")])
            writer.writerow([f"{category}_net", amounts.get("net", "")])
        else:
            writer.writerow([category, amounts])


def _write_consumer_row(writer, entry: dict) -> None:  # type: ignore[type-arg]
    writer.writerow(
        [
            entry.get("repo", ""),
            repo_visibility(entry),
            entry.get("minutes", ""),
            entry.get("gross", ""),
            entry.get("storage_avg_mb", ""),
        ]
    )


def _write_repo_consumers_sections(writer, data: dict) -> None:  # type: ignore[type-arg]
    consumers = _coerce_section(data.get("repo_consumers"), {})
    _write_section_header(writer, "Top Repos by Minutes")
    for entry in consumers.get("by_minutes") or []:
        _write_consumer_row(writer, entry)

    _write_section_header(writer, "Top Repos by Cost")
    for entry in consumers.get("by_cost") or []:
        _write_consumer_row(writer, entry)


def _write_artifact_storage_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Artifact Storage")
    artifacts = _coerce_section(data.get("artifact_storage"), {})
    for entry in artifacts.get("top_repos") or []:
        writer.writerow(
            [entry.get("repo", ""), repo_visibility(entry), entry.get("artifact_bytes", "")]
        )


def _write_storage_analysis_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    analysis_rows = storage_analysis_export_rows(data.get("storage_analysis"))
    if analysis_rows:
        _write_section_header(writer, "Storage Analysis")
        for row in analysis_rows:
            writer.writerow(row)


def _write_release_assets_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Release Assets")
    releases = _coerce_section(data.get("release_assets"), {})
    for entry in releases.get("top_repos") or []:
        writer.writerow(
            [
                entry.get("repo", ""),
                repo_visibility(entry),
                entry.get("release_asset_bytes", ""),
            ]
        )


def _write_key_insights_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Key Insights")
    for insight in data.get("insights") or []:
        writer.writerow([insight])


def _write_unavailable_data_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    _write_section_header(writer, "Unavailable Data")
    for error_key, error_msg in (data.get("errors") or {}).items():
        writer.writerow([error_key, error_msg])


def _write_sources_section(writer, data: dict) -> None:  # type: ignore[type-arg]
    sources = data.get("sources")
    source_rows = sources_rows(sources if isinstance(sources, dict) else None)
    if source_rows:
        _write_section_header(writer, "Sources")
        for row in source_rows:
            writer.writerow(row)


def _write_forecast_section(
    writer: csv.writer,  # type: ignore[type-arg]
    data: dict,
    *,
    premium_requests_limit: float | None = None,
) -> None:
    """Write a flattened forecast section derived from current usage values."""
    forecast = build_report_forecast(data, premium_requests_limit=premium_requests_limit)
    if forecast is None:
        return
    _write_section_header(writer, "Forecast")
    writer.writerow(["metric", "current", "projected", "limit", "run_out_day"])
    for metric_name in ("minutes", "storage_avg_mb", "premium_requests"):
        metric = forecast[metric_name]
        limit = metric["limit"]
        run_out = metric["run_out_day"]
        writer.writerow(
            [
                metric_name,
                metric["current"],
                metric["projected"],
                limit if limit is not None else "",
                run_out if run_out is not None else "",
            ]
        )


def _write_copilot_by_model(writer: csv.writer, by_model) -> None:  # type: ignore[type-arg]
    if not by_model:
        return
    writer.writerow(["by_model"])
    writer.writerow(["model", "requests", "gross", "discount", "net"])
    for model_name, model_data in by_model.items():
        if isinstance(model_data, dict):
            writer.writerow(
                [
                    model_name,
                    model_data.get("requests", ""),
                    model_data.get("gross", ""),
                    model_data.get("discount", ""),
                    model_data.get("net", ""),
                ]
            )
        else:
            writer.writerow([model_name, model_data])


def _write_section_header(writer: csv.writer, title: str) -> None:  # type: ignore[type-arg]
    """Write a section delimiter row like ``### Section Name ###`` (single cell)."""
    writer.writerow([f"### {title} ###"])


def _write_kv(writer: csv.writer, data: dict, keys: list) -> None:  # type: ignore[type-arg]
    for key in keys:
        value = data.get(key)
        if value is not None:
            writer.writerow([key, value])


def _write_nested(writer: csv.writer, section_name: str, row_label: str, nested) -> None:  # type: ignore[type-arg]
    """Write a nested dict as a sub-table with a header row.

    The dict key is included as the first column (``row_label``) so rows are
    self-identifying.
    """
    if not nested:
        return
    writer.writerow([section_name])
    sample = next(iter(nested.values()), None)
    if isinstance(sample, dict):
        cols = list(sample.keys())
        writer.writerow([row_label, *cols])
        for key, sku_data in nested.items():
            writer.writerow([key, *(sku_data.get(c) for c in cols)])
    else:
        for key, value in nested.items():
            writer.writerow([key, value])
