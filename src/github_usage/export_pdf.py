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

from collections.abc import Callable

_MAX_SECTION_ROWS = 30

AddSectionFn = Callable[[str, list], None]


def _fmt_num(value) -> str:
    if value is None:
        return "N/A"
    try:
        return str(float(value))
    except (ValueError, TypeError):
        return str(value)


def _make_pdf_writer(pdf):
    """Return (add_section, fmt_num) closures bound to ``pdf``.

    Module-level section helpers take ``add_section`` as their first
    argument so they can render rows without constructing their own
    fpdf2 PDF.
    """
    from fpdf.enums import XPos, YPos

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

    return add_section, _fmt_num


def _write_cover_page(pdf, data: dict) -> None:
    from fpdf.enums import XPos, YPos

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


def _write_actions_page(add_section: AddSectionFn, data: dict) -> None:
    actions = data.get("actions") or {}
    if not actions:
        return
    minutes = actions.get("minutes")
    storage = actions.get("storage_avg_mb")
    add_section(
        "Actions",
        [
            (
                "Minutes",
                (
                    f"{_fmt_num(minutes)} / {_fmt_num(actions.get('minutes_limit'))} "
                    f"({_fmt_num(actions.get('minutes_percent'))}%)"
                    if minutes is not None
                    else "N/A"
                ),
            ),
            (
                "Storage",
                (
                    f"{_fmt_num(storage)} MB / {_fmt_num(actions.get('storage_limit_mb'))} MB "
                    f"({_fmt_num(actions.get('storage_percent'))}%)"
                    if storage is not None
                    else "N/A"
                ),
            ),
        ],
    )


def _write_copilot_page(add_section: AddSectionFn, data: dict) -> None:
    copilot = data.get("copilot") or {}
    if not copilot:
        return
    add_section(
        "Copilot",
        [
            ("Total Requests", _fmt_num(copilot.get("total_requests"))),
            ("Total Gross", _fmt_num(copilot.get("total_gross"))),
            ("Total Discount", _fmt_num(copilot.get("total_discount"))),
            ("Total Net", _fmt_num(copilot.get("total_net"))),
        ],
    )


def _write_git_lfs_page(add_section: AddSectionFn, data: dict) -> None:
    git_lfs = data.get("git_lfs") or {}
    if not git_lfs:
        return
    add_section(
        "Git LFS",
        [
            ("Total Gross", _fmt_num(git_lfs.get("total_gross"))),
            ("Total Discount", _fmt_num(git_lfs.get("total_discount"))),
            ("Total Net", _fmt_num(git_lfs.get("total_net"))),
        ],
    )


def _write_monthly_costs_page(add_section: AddSectionFn, data: dict) -> None:
    costs = data.get("monthly_costs") or {}
    rows = []
    for category in ("actions", "copilot", "git_lfs", "total"):
        cat = costs.get(category) or {}
        if cat:
            rows.append(
                (
                    category,
                    f"gross {_fmt_num(cat.get('gross', 0))}, "
                    f"discount {_fmt_num(cat.get('discount', 0))}, "
                    f"net {_fmt_num(cat.get('net', 0))}",
                )
            )
    if rows:
        add_section("Monthly Costs", rows)


def _write_consumers_page(add_section: AddSectionFn, data: dict) -> None:
    consumers = data.get("repo_consumers") or {}
    by_minutes = consumers.get("by_minutes") or []
    if by_minutes:
        rows = [
            (entry.get("repo", "unknown"), f"{_fmt_num(entry.get('minutes'))} minutes")
            for entry in by_minutes
        ]
        add_section("Top Repos by Minutes", rows)
    by_cost = consumers.get("by_cost") or []
    if by_cost:
        rows = [
            (entry.get("repo", "unknown"), f"${_fmt_num(entry.get('gross'))}") for entry in by_cost
        ]
        add_section("Top Repos by Cost", rows)


def _write_artifact_storage_page(add_section: AddSectionFn, data: dict) -> None:
    artifacts = data.get("artifact_storage") or {}
    artifact_repos = artifacts.get("top_repos") or []
    if artifact_repos:
        rows = [
            (entry.get("repo", "unknown"), f"{_fmt_num(entry.get('artifact_bytes'))} bytes")
            for entry in artifact_repos
        ]
        add_section("Artifact Storage", rows)


def _write_release_assets_page(add_section: AddSectionFn, data: dict) -> None:
    releases = data.get("release_assets") or {}
    release_repos = releases.get("top_repos") or []
    if release_repos:
        rows = [
            (entry.get("repo", "unknown"), f"{_fmt_num(entry.get('release_asset_bytes'))} bytes")
            for entry in release_repos
        ]
        add_section("Release Assets", rows)


def _write_insights_page(add_section: AddSectionFn, data: dict) -> None:
    insights = data.get("insights") or []
    if insights:
        add_section("Key Insights", [("Finding", insight) for insight in insights])


def _write_errors_page(add_section: AddSectionFn, data: dict) -> None:
    errors = data.get("errors") or {}
    if errors:
        add_section("Unavailable Data", list(errors.items()))


_SECTION_PAGES = (
    _write_actions_page,
    _write_copilot_page,
    _write_git_lfs_page,
    _write_monthly_costs_page,
    _write_consumers_page,
    _write_artifact_storage_page,
    _write_release_assets_page,
    _write_insights_page,
    _write_errors_page,
)


def write(data: dict, file_obj) -> None:
    """Write the report data dict as a multi-page PDF to ``file_obj``."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    add_section, _ = _make_pdf_writer(pdf)
    _write_cover_page(pdf, data)
    for page_writer in _SECTION_PAGES:
        page_writer(add_section, data)
    pdf.output(file_obj)
