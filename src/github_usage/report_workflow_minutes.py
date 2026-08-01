"""Per-workflow estimated Actions minutes from workflow run wall-clock times.

Estimates current-calendar-month usage for a single repository by summing
``updated_at - run_started_at`` (fallback ``created_at``) per completed run.
These are approximations — not GitHub billable minutes.
"""

from __future__ import annotations

from datetime import date, timedelta

from .storage import _parse_iso_datetime

WORKFLOW_CAVEAT = "(estimated from run wall-clock; not billable — will not match billed repo total)"


def _parse_iso(value: str | None):
    """Parse ISO timestamps as timezone-aware UTC (delegates to storage helper)."""
    return _parse_iso_datetime(value)


def _fetch_runs_cached(api, owner: str, name: str, created_range: str, *, cache: dict) -> list:
    """Return workflow runs for (owner, name, created_range), memoized in ``cache``.

    Callers must pass one shared ``cache`` dict from the report builder.
    Do not use ``cache or {}`` — a fresh dict defeats memoization.
    """
    key = (owner, name, created_range)
    if key not in cache:
        cache[key] = api.get_all_pages(
            f"/repos/{owner}/{name}/actions/runs",
            {"created": created_range, "per_page": 100},
        )
    return cache[key]


def _workflow_name_map(api, owner: str, name: str) -> dict:
    """Map workflow id → display name; return ``{}`` on API failure."""
    try:
        workflows = api.get_all_pages(f"/repos/{owner}/{name}/actions/workflows")
        return {
            wf["id"]: wf["name"] for wf in workflows if wf.get("id") is not None and wf.get("name")
        }
    except Exception:
        return {}


def fetch_workflow_minutes(api, owner: str, name: str, *, runs_cache: dict) -> dict | None:
    """Per-workflow estimated Actions minutes from run start→end times (current month).

    ``None`` when no usable completed runs.

    Computes ``created_range`` internally (same calendar-month logic as
    ``get_actions_from_runs``); do not leave it undefined in the call site.
    """
    first_day = date.today().replace(day=1)
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    created_range = f"{first_day.isoformat()}..{last_day.isoformat()}"
    runs = _fetch_runs_cached(api, owner, name, created_range, cache=runs_cache)
    wf_names = _workflow_name_map(api, owner, name)
    by_wf: dict = {}
    for run in runs:
        if run.get("status") != "completed":
            continue
        end = _parse_iso(run.get("updated_at"))
        start = _parse_iso(run.get("run_started_at")) or _parse_iso(run.get("created_at"))
        if not start or not end or end <= start:
            continue
        wf_id = run.get("workflow_id") or run.get("name") or "unknown"
        entry = by_wf.setdefault(wf_id, {"name": None, "runs": 0, "minutes": 0.0})
        entry["name"] = (
            entry["name"]
            or wf_names.get(wf_id)
            or run.get("name")
            or (f"Workflow #{wf_id}" if isinstance(wf_id, int) else "Unknown Workflow")
        )
        entry["runs"] += 1
        entry["minutes"] += (end - start).total_seconds() / 60
    if not by_wf:
        return None
    ranked = sorted(by_wf.values(), key=lambda e: (-e["minutes"], e["name"] or ""))
    return {
        "repo": f"{owner}/{name}",
        "total_minutes": round(sum(e["minutes"] for e in ranked), 1),
        "by_workflow": ranked,
    }


def workflow_breakdown_for_top_private(
    api, repo_consumers: dict | None, *, runs_cache: dict
) -> dict | None:
    """Fetch workflow breakdown for the top private consumer when minutes > 0."""
    if not repo_consumers:
        return None
    by_minutes_private = repo_consumers.get("by_minutes_private") or []
    if not by_minutes_private or by_minutes_private[0].get("minutes", 0) <= 0:
        return None
    repo = by_minutes_private[0].get("repo", "")
    if "/" not in repo:
        return None
    owner, name = repo.split("/", 1)
    return fetch_workflow_minutes(api, owner, name, runs_cache=runs_cache)


def render_workflow_breakdown(breakdown, *, limit: int = 10) -> None:
    """Print per-workflow estimated minutes for the top private repo consumer."""
    if not breakdown:
        return
    repo = breakdown.get("repo", "?")
    workflows = (breakdown.get("by_workflow") or [])[:limit]
    if not workflows:
        return
    total = float(breakdown.get("total_minutes") or 0.0)
    print(f"  Minutes by Workflow — Top Private Repo ({repo})")
    print(f"  {WORKFLOW_CAVEAT}")
    print("  " + "─" * 74)
    print(f"    Total (est): {total:.1f} min")
    for entry in workflows:
        minutes = float(entry.get("minutes") or 0.0)
        pct = minutes / total * 100.0 if total and total > 0 else 0.0
        name = entry.get("name") or "Unknown Workflow"
        print(f"    {name:<42} {minutes:>8.1f} min  ({pct:5.1f}%)")
    print()
