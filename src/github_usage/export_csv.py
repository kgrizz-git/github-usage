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


def write(data: dict, file_obj) -> None:
    """Write the report data dict as CSV to ``file_obj``."""
    file_obj.write("\ufeff")
    writer = csv.writer(file_obj)
    _write_sections(writer, data)
    writer.writerow([])


def _coerce_section(value, default):
    """Return ``value`` if it is a dict/list, else ``default`` (handles ``None``)."""
    if value is None:
        return default
    return value


def _write_sections(writer: csv.writer, data: dict) -> None:
    _write_section_header(writer, "Report Metadata")
    _write_kv(writer, data, ["username", "period", "generated_at"])

    _write_section_header(writer, "Warnings")
    for warning in data.get("warnings") or []:
        writer.writerow([warning])

    _write_section_header(writer, "Actions Usage")
    actions = _coerce_section(data.get("actions"), {})
    for key, value in actions.items():
        if key == "sku_breakdown":
            _write_nested(writer, "sku_breakdown", "sku", value)
        else:
            writer.writerow([key, value])

    _write_section_header(writer, "Copilot Usage")
    copilot = _coerce_section(data.get("copilot"), {})
    for key, value in copilot.items():
        if key == "by_model":
            _write_copilot_by_model(writer, value)
        else:
            writer.writerow([key, value])

    _write_section_header(writer, "Git LFS")
    git_lfs = _coerce_section(data.get("git_lfs"), {})
    for key, value in git_lfs.items():
        writer.writerow([key, value])

    _write_section_header(writer, "Monthly Costs")
    costs = _coerce_section(data.get("monthly_costs"), {})
    for category, amounts in costs.items():
        if isinstance(amounts, dict):
            writer.writerow([f"{category}_gross", amounts.get("gross", "")])
            writer.writerow([f"{category}_discount", amounts.get("discount", "")])
            writer.writerow([f"{category}_net", amounts.get("net", "")])
        else:
            writer.writerow([category, amounts])

    _write_section_header(writer, "Top Repos by Minutes")
    consumers = _coerce_section(data.get("repo_consumers"), {})
    for entry in consumers.get("by_minutes") or []:
        writer.writerow(
            [
                entry.get("repo", ""),
                entry.get("minutes", ""),
                entry.get("gross", ""),
                entry.get("storage_avg_mb", ""),
            ]
        )

    _write_section_header(writer, "Top Repos by Cost")
    for entry in consumers.get("by_cost") or []:
        writer.writerow(
            [
                entry.get("repo", ""),
                entry.get("minutes", ""),
                entry.get("gross", ""),
                entry.get("storage_avg_mb", ""),
            ]
        )

    _write_section_header(writer, "Artifact Storage")
    artifacts = _coerce_section(data.get("artifact_storage"), {})
    for entry in artifacts.get("top_repos") or []:
        writer.writerow([entry.get("repo", ""), entry.get("artifact_bytes", "")])

    _write_section_header(writer, "Release Assets")
    releases = _coerce_section(data.get("release_assets"), {})
    for entry in releases.get("top_repos") or []:
        writer.writerow([entry.get("repo", ""), entry.get("release_asset_bytes", "")])

    _write_section_header(writer, "Key Insights")
    for insight in data.get("insights") or []:
        writer.writerow([insight])

    _write_section_header(writer, "Unavailable Data")
    for error_key, error_msg in (data.get("errors") or {}).items():
        writer.writerow([error_key, error_msg])


def _write_copilot_by_model(writer: csv.writer, by_model) -> None:
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


def _write_section_header(writer: csv.writer, title: str) -> None:
    """Write a section delimiter row like ``### Section Name ###`` (single cell)."""
    writer.writerow([f"### {title} ###"])


def _write_kv(writer: csv.writer, data: dict, keys: list) -> None:
    for key in keys:
        value = data.get(key)
        if value is not None:
            writer.writerow([key, value])


def _write_nested(writer: csv.writer, section_name: str, row_label: str, nested) -> None:
    """Write a nested dict as a sub-table with a header row.

    The dict key is included as the first column (``row_label``) so rows are
    self-identifying.
    """
    if not nested:
        return
    writer.writerow([section_name])
    sample = next(iter(nested.values()), None)
    if isinstance(sample, dict):
        writer.writerow([row_label, *sample.keys()])
        for key, sku_data in nested.items():
            writer.writerow([key, *sku_data.values()])
    else:
        for key, value in nested.items():
            writer.writerow([key, value])
