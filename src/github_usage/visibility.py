"""Visibility helpers for public/private/internal repository grouping and filtering."""

from __future__ import annotations

VISIBILITY_ORDER = ["private", "internal", "public"]

_GROUP_HEADERS = {
    "private": "Private Repos:",
    "internal": "Internal Repos:",
    "public": "Public Repos:",
}


def repo_visibility(repo: dict, key: str = "visibility") -> str:
    """Resolve visibility from a GitHub repo or enriched row dict.

    Prefer an explicit ``visibility`` string. If missing, infer from the
    ``private`` boolean (``True`` → ``"private"``, else ``"public"``).
    On GHES without ``visibility``, internal repos may appear as private —
    best-effort.
    """
    raw = repo.get(key)
    if isinstance(raw, str) and raw:
        return raw
    return "private" if repo.get("private") else "public"


def group_by_visibility(rows: list[dict], key: str = "visibility") -> dict[str, list[dict]]:
    """Group rows by visibility: private, internal, public, then any unknown keys."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        vis = repo_visibility(row, key=key)
        groups.setdefault(vis, []).append(row)
    result = {v: groups[v] for v in VISIBILITY_ORDER if v in groups}
    for vis, items in groups.items():
        if vis not in result:
            result[vis] = items
    return result


def visibility_group_header(visibility: str) -> str:
    """Return a display header for a visibility group table."""
    return _GROUP_HEADERS.get(visibility, f"{visibility.title()} Repos:")


def visibility_label(visibility: str) -> str:
    """Return a display suffix like ``' [private]'``, or ``''`` for public."""
    if visibility == "public":
        return ""
    return f" [{visibility}]"


def filter_repos_by_visibility(
    repos: list[dict],
    *,
    only_public: bool = False,
    only_private: bool = False,
) -> list[dict]:
    """Filter repos by visibility. No-op when neither flag is set.

    ``only_private`` includes both ``private`` and ``internal``.
    Callers must not set both flags (CLI/GUI enforce mutual exclusion).
    """
    if only_public:
        return [r for r in repos if repo_visibility(r) == "public"]
    if only_private:
        return [r for r in repos if repo_visibility(r) in ("private", "internal")]
    return repos
