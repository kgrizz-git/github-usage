"""Private-repo consumer findings and recommendations for the final summary."""

from __future__ import annotations

from .repo_consumers import private_list_is_redundant
from .visibility import visibility_label


def _repo_label(full: str, visibility_by_repo: dict[str, str] | None) -> str:
    if not visibility_by_repo:
        return full
    return f"{full}{visibility_label(visibility_by_repo.get(full, 'public'))}"


def _pct_of_private_minutes(minutes: float, private_minutes: float | None) -> float:
    return minutes / private_minutes * 100.0 if private_minutes and private_minutes > 0 else 0.0


def private_consumer_findings(
    repo_consumers: dict | None,
    private_minutes: float | None,
    visibility_by_repo: dict[str, str] | None,
) -> list[str]:
    """Return private-only Actions/storage consumer findings when not redundant."""
    if not repo_consumers:
        return []
    findings: list[str] = []
    by_minutes = repo_consumers.get("by_minutes") or []
    by_minutes_private = repo_consumers.get("by_minutes_private") or []
    if by_minutes_private and not private_list_is_redundant(by_minutes[:5], by_minutes_private[:5]):
        top_priv = by_minutes_private[0]
        label = _repo_label(top_priv["repo"], visibility_by_repo)
        pct_priv = _pct_of_private_minutes(top_priv["minutes"], private_minutes)
        findings.append(
            f"Biggest private Actions consumer: {label} "
            f"at {top_priv['minutes']:.0f} min ({pct_priv:.1f}% of private minutes)."
        )
    by_storage = repo_consumers.get("by_storage") or []
    by_storage_private = repo_consumers.get("by_storage_private") or []
    if by_storage_private and not private_list_is_redundant(by_storage[:5], by_storage_private[:5]):
        top_st_priv = by_storage_private[0]
        label = _repo_label(top_st_priv["repo"], visibility_by_repo)
        findings.append(
            f"Biggest private storage consumer: {label} ({top_st_priv['storage_avg_mb']:.1f} MB)."
        )
    return findings


def private_concentration_recommendation(
    repo_consumers: dict | None,
    private_minutes: float,
    visibility_by_repo: dict[str, str] | None,
) -> list[str]:
    """Recommend self-hosted runners when top 2 private repos dominate private minutes."""
    by_minutes_private = (repo_consumers or {}).get("by_minutes_private") or []
    if len(by_minutes_private) <= 1 or not private_minutes or private_minutes <= 0:
        return []
    top2_sum = by_minutes_private[0]["minutes"] + by_minutes_private[1]["minutes"]
    if top2_sum / private_minutes * 100 <= 70:
        return []
    top_labels = ", ".join(
        _repo_label(row["repo"], visibility_by_repo) for row in by_minutes_private[:2]
    )
    return [
        f"Top 2 private repos ({top_labels}) consume "
        f"{top2_sum / private_minutes * 100:.0f}% of private Actions minutes — "
        "consider self-hosted runners."
    ]
