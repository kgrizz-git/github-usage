"""Repository storage analysis helpers."""

from __future__ import annotations


def get_storage_analysis(api, repos):
    """Analyze storage per repo: artifacts, releases, LFS."""
    repo_storage = []
    for repo in repos:
        try:
            owner = repo.get("owner", {}).get("login")
            name = repo.get("name")
            if not owner or not name:
                continue
            full = repo.get("full_name") or f"{owner}/{name}"
            total_storage = 0.0
            items = []

            # Artifacts
            try:
                artifacts = api.get_all_pages(
                    f"/repos/{owner}/{name}/actions/artifacts",
                    {"per_page": 100},
                )
            except RuntimeError:
                artifacts = []
            for art in artifacts:
                size_bytes = art.get("size_in_bytes", 0)
                total_storage += size_bytes / (1024 * 1024 * 1024)
                items.append(
                    {
                        "type": "Artifact",
                        "name": art.get("name", "Unknown"),
                        "count": 1,
                        "storage": size_bytes / (1024 * 1024 * 1024),
                        "size": f"{size_bytes / (1024 * 1024):.0f} MB",
                    }
                )

            # Releases + assets
            try:
                releases = api.get_all_pages(
                    f"/repos/{owner}/{name}/releases",
                    {"per_page": 100},
                )
            except RuntimeError:
                releases = []
            for rel in releases:
                for asset in rel.get("assets", []):
                    size_bytes = asset.get("size", 0)
                    total_storage += size_bytes / (1024 * 1024 * 1024)
                    items.append(
                        {
                            "type": "Release Asset",
                            "name": asset.get("name", "Unknown"),
                            "count": 1,
                            "storage": size_bytes / (1024 * 1024 * 1024),
                            "size": f"{size_bytes / (1024 * 1024):.0f} MB",
                        }
                    )

            if total_storage > 0 or items:
                repo_storage.append(
                    {
                        "name": full,
                        "total_storage": total_storage,
                        "items": items,
                    }
                )
        except (KeyError, RuntimeError):
            continue

    return {"repos": repo_storage}
