"""PDF writer for report exports.

Writes a multi-page PDF with a cover page and one page per major section.
Requires fpdf2 >= 2.7 (uses ``XPos``/``YPos`` enums).

Invariants:
- Numeric values are cast via :func:`float` to handle string-formatted
  numbers in serialized data.
- ``None`` values display as ``"N/A"``.
- Sections exceeding :data:`_MAX_SECTION_ROWS` are truncated with a note.
- The orchestrator routes stdout output through ``sys.stdout.buffer``
  (binary mode); the writer itself just calls ``pdf.output(file_obj)``.
"""

from __future__ import annotations

_MAX_SECTION_ROWS = 30


def write(data: dict, file_obj) -> None:
    """Write the report data dict as a multi-page PDF to ``file_obj``."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    def add_section(title: str, rows: list) -> None:
        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=14)
        pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(5)
        pdf.set_font("Helvetica", size=10)
        for label, value in rows[:_MAX_SECTION_ROWS]:
            pdf.cell(60, 7, f"{label}:", new_x=XPos.END)
            pdf.cell(0, 7, str(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)
        if len(rows) > _MAX_SECTION_ROWS:
            pdf.set_font("Helvetica", style="I", size=9)
            pdf.cell(
                0,
                7,
                f"(truncated: {len(rows) - _MAX_SECTION_ROWS} more rows)",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    def fmt_num(value) -> str:
        if value is None:
            return "N/A"
        try:
            return str(float(value))
        except (ValueError, TypeError):
            return str(value)

    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=18)
    pdf.cell(0, 12, "GitHub Usage Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    pdf.set_font("Helvetica", size=12)
    for label, value in [
        ("Username", data.get("username", "")),
        ("Period", data.get("period", "")),
        ("Generated", data.get("generated_at", "")),
    ]:
        pdf.cell(40, 7, f"{label}:", new_x=XPos.END)
        pdf.cell(0, 7, str(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    actions = data.get("actions") or {}
    if actions:
        minutes = actions.get("minutes")
        storage = actions.get("storage_avg_mb")
        add_section(
            "Actions",
            [
                (
                    "Minutes",
                    (
                        f"{fmt_num(minutes)} / {fmt_num(actions.get('minutes_limit'))} "
                        f"({fmt_num(actions.get('minutes_percent'))}%)"
                        if minutes is not None
                        else "N/A"
                    ),
                ),
                (
                    "Storage",
                    (
                        f"{fmt_num(storage)} MB / {fmt_num(actions.get('storage_limit_mb'))} MB "
                        f"({fmt_num(actions.get('storage_percent'))}%)"
                        if storage is not None
                        else "N/A"
                    ),
                ),
            ],
        )

    copilot = data.get("copilot") or {}
    copilot_rows = []
    if copilot:
        copilot_rows.append(("Total Requests", fmt_num(copilot.get("total_requests"))))
        copilot_rows.append(("Total Gross", fmt_num(copilot.get("total_gross"))))
        copilot_rows.append(("Total Discount", fmt_num(copilot.get("total_discount"))))
        copilot_rows.append(("Total Net", fmt_num(copilot.get("total_net"))))
    if copilot_rows:
        add_section("Copilot", copilot_rows)

    git_lfs = data.get("git_lfs") or {}
    git_lfs_rows = []
    if git_lfs:
        git_lfs_rows.append(("Total Gross", fmt_num(git_lfs.get("total_gross"))))
        git_lfs_rows.append(("Total Discount", fmt_num(git_lfs.get("total_discount"))))
        git_lfs_rows.append(("Total Net", fmt_num(git_lfs.get("total_net"))))
    if git_lfs_rows:
        add_section("Git LFS", git_lfs_rows)

    costs = data.get("monthly_costs") or {}
    cost_rows = []
    for category in ("actions", "copilot", "git_lfs", "total"):
        cat = costs.get(category) or {}
        if cat:
            cost_rows.append(
                (
                    category,
                    f"gross {fmt_num(cat.get('gross', 0))}, "
                    f"discount {fmt_num(cat.get('discount', 0))}, "
                    f"net {fmt_num(cat.get('net', 0))}",
                )
            )
    if cost_rows:
        add_section("Monthly Costs", cost_rows)

    consumers = data.get("repo_consumers") or {}
    by_minutes = consumers.get("by_minutes") or []
    if by_minutes:
        rows = [
            (entry.get("repo", "unknown"), f"{fmt_num(entry.get('minutes'))} minutes")
            for entry in by_minutes
        ]
        add_section("Top Repos by Minutes", rows)
    by_cost = consumers.get("by_cost") or []
    if by_cost:
        rows = [
            (entry.get("repo", "unknown"), f"${fmt_num(entry.get('gross'))}") for entry in by_cost
        ]
        add_section("Top Repos by Cost", rows)

    artifacts = data.get("artifact_storage") or {}
    artifact_repos = artifacts.get("top_repos") or []
    if artifact_repos:
        rows = [
            (entry.get("repo", "unknown"), f"{fmt_num(entry.get('artifact_bytes'))} bytes")
            for entry in artifact_repos
        ]
        add_section("Artifact Storage", rows)

    releases = data.get("release_assets") or {}
    release_repos = releases.get("top_repos") or []
    if release_repos:
        rows = [
            (entry.get("repo", "unknown"), f"{fmt_num(entry.get('release_asset_bytes'))} bytes")
            for entry in release_repos
        ]
        add_section("Release Assets", rows)

    insights = data.get("insights") or []
    if insights:
        add_section("Key Insights", [("Finding", insight) for insight in insights])

    errors = data.get("errors") or {}
    if errors:
        add_section("Unavailable Data", list(errors.items()))

    pdf.output(file_obj)
