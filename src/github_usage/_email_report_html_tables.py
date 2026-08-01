"""HTML table helpers for email report sections (consumers, workflow breakdown)."""

from __future__ import annotations

import html

from .report_helpers import fmt_price
from .visibility import (
    group_by_visibility,
    repo_visibility,
    visibility_group_header,
    visibility_label,
)


def html_repo_cell(row: dict) -> str:
    """Render a repo name cell with optional visibility tag."""
    repo = html.escape(row["repo"])
    vis = repo_visibility(row)
    if vis == "public":
        return repo
    tag = html.escape(visibility_label(vis).strip())
    return f'{repo} <span class="visibility-tag">[{tag}]</span>'


def html_grouped_table(title: str, rows: list[dict], *, headers: list[str], value_fn) -> list[str]:
    """Build an HTML table, splitting by visibility when multiple groups exist."""
    parts = [f"<h2>{html.escape(title)}</h2>"]
    groups = group_by_visibility(rows)
    if len(groups) <= 1:
        parts.append("<table>")
        parts.append(f"<tr>{''.join(f'<th>{html.escape(h)}</th>' for h in headers)}</tr>")
        for row in rows:
            parts.append(value_fn(row))
        parts.append("</table>")
        return parts
    for vis, group_rows in groups.items():
        parts.append(f"<h3>{html.escape(visibility_group_header(vis))}</h3>")
        parts.append("<table>")
        parts.append(f"<tr>{''.join(f'<th>{html.escape(h)}</th>' for h in headers)}</tr>")
        for row in group_rows:
            parts.append(value_fn(row))
        parts.append("</table>")
    return parts


def html_flat_table(title: str, rows: list[dict], *, headers: list[str], value_fn) -> list[str]:
    """Build a single HTML table without visibility grouping (private-only lists)."""
    parts = [f"<h2>{html.escape(title)}</h2>", "<table>"]
    parts.append(f"<tr>{''.join(f'<th>{html.escape(h)}</th>' for h in headers)}</tr>")
    for row in rows:
        parts.append(value_fn(row))
    parts.append("</table>")
    return parts


def html_minutes_row(row: dict) -> str:
    return (
        f"<tr><td>{html_repo_cell(row)}</td>"
        f"<td>{row['minutes']:,.1f} min</td>"
        f"<td>{fmt_price(row['gross'])}</td>"
        f"<td>{row['storage_avg_mb']:,.1f} MB avg</td></tr>"
    )


def html_cost_consumer_row(row: dict) -> str:
    return (
        f"<tr><td>{html_repo_cell(row)}</td>"
        f"<td>{fmt_price(row['gross'])}</td>"
        f"<td>{row['minutes']:,.1f} min</td>"
        f"<td>{row['storage_avg_mb']:,.1f} MB avg</td></tr>"
    )


def html_storage_row(row: dict) -> str:
    return (
        f"<tr><td>{html_repo_cell(row)}</td>"
        f"<td>{row['storage_avg_mb']:,.1f} MB avg</td>"
        f"<td>{row['minutes']:,.1f} min</td>"
        f"<td>{fmt_price(row['gross'])}</td></tr>"
    )


# Phase 4e: workflow breakdown table helpers go here.


def html_workflow_row(entry: dict, *, total_minutes: float) -> str:
    """Render one workflow breakdown table row."""
    minutes = float(entry.get("minutes") or 0.0)
    pct = minutes / total_minutes * 100.0 if total_minutes and total_minutes > 0 else 0.0
    name = html.escape(str(entry.get("name") or "Unknown Workflow"))
    runs = int(entry.get("runs") or 0)
    return f"<tr><td>{name}</td><td>{runs}</td><td>{minutes:,.1f} min</td><td>{pct:.1f}%</td></tr>"


def html_workflow_breakdown_table(breakdown: dict, *, limit: int = 5) -> list[str]:
    """Build HTML table for per-workflow estimated minutes."""
    from .report_workflow_minutes import WORKFLOW_CAVEAT

    repo = html.escape(str(breakdown.get("repo") or "?"))
    workflows = (breakdown.get("by_workflow") or [])[:limit]
    if not workflows:
        return []
    total = float(breakdown.get("total_minutes") or 0.0)
    parts = [
        f"<h2>Minutes by Workflow — Top Private Repo ({repo})</h2>",
        f'<p class="meta">{html.escape(WORKFLOW_CAVEAT)}</p>',
        "<table>",
        "<tr><th>Workflow</th><th>Runs</th><th>Minutes (est)</th><th>%</th></tr>",
    ]
    for entry in workflows:
        parts.append(html_workflow_row(entry, total_minutes=total))
    parts.append("</table>")
    return parts
