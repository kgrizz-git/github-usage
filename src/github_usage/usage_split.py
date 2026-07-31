"""Private-vs-public visibility split and runner-SKU classification for Actions billing.

Builds on the shipped ``visibility.repo_visibility`` helper (which folds the
``private`` boolean fallback). Billing aggregates here intentionally collapse
``internal`` into ``private`` for free-tier limit math; the per-repo inventory
in ``render_repo_actions_table`` keeps three separate groups via
``visibility.group_by_visibility`` (a deliberate, documented divergence — see
the plan's Resolved Decisions).
"""

from __future__ import annotations

from .report_helpers import sanitize_item_amounts
from .visibility import repo_visibility

STANDARD_RUNNER_SKUS = frozenset(
    {
        "actions_linux",
        "actions_linux_slim",
        "actions_linux_arm",
        "actions_windows",
        "actions_windows_arm",
        "actions_macos",
    }
)

_PRIVATE_STORAGE_LIMIT_GB = 0.5
_PRIVATE_MINUTES_LIMIT = 2000

LARGER_RUNNER_ALIASES = {
    "linux_4_core": "Linux 4-core",
    "linux_8_core": "Linux 8-core",
    "linux_16_core": "Linux 16-core",
    "macos_l": "macOS 12-core",
    "macos_xl": "macOS 5-core (M2 Pro)",
    "linux_4_core_gpu": "Linux 4-core GPU",
    "windows_4_core_gpu": "Windows 4-core GPU",
}

REPORT_SOURCES = {
    "actions_billing": (
        "https://docs.github.com/en/billing/managing-billing-for-github-actions/"
        "about-billing-for-github-actions"
    ),
    "runner_pricing": ("https://docs.github.com/en/billing/reference/actions-runner-pricing"),
    "releases_storage": (
        "https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases"
    ),
    "packages_billing": (
        "https://docs.github.com/en/packages/learn-github-packages/about-github-packages"
    ),
}


def normalize_sku(sku: str) -> str:
    """Lowercase and strip a leading ``actions_``/``actions`` prefix so API and
    reference-table spellings compare equal. Collapses digit-word boundaries
    (``4core`` -> ``4_core``) as a defensive guard; the pricing reference
    always uses the underscore form, so this is a no-op for live SKUs.

    Standard runner SKUs are kept in their canonical ``actions_*`` form in
    :data:`STANDARD_RUNNER_SKUS`; therefore :func:`is_standard_runner_sku`
    compares the **raw** lowercase form against that set, not the normalized
    one. ``normalize_sku`` is used to find a human-readable alias for
    larger-runner display only.
    """
    s = (sku or "").lower().strip()
    for prefix in ("actions_", "actions"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    for d in [c for c in s if c.isdigit()]:
        s = s.replace(f"{d}core", f"{d}_core")
    return s.lstrip("_")


def is_standard_runner_sku(sku: str) -> bool:
    """True for the documented standard GitHub-hosted runner SKUs.

    Compares the lowercased raw SKU against :data:`STANDARD_RUNNER_SKUS`
    (which stores the canonical ``actions_*`` form). A missing ``actions_``
    prefix is also accepted so callers that have already stripped the prefix
    match correctly.
    """
    raw = (sku or "").lower().strip()
    if raw in STANDARD_RUNNER_SKUS:
        return True
    return normalize_sku(raw) in {k.replace("actions_", "") for k in STANDARD_RUNNER_SKUS}


def classify_actions_sku(sku: str, item: dict | None = None) -> str:
    """Classify a billing SKU as ``"standard"``, ``"larger"``, or ``"storage"``.

    ``gigabyte-hours`` items are storage. Compute (minutes-unit) SKUs outside
    the documented standard set are treated as ``"larger"`` — larger runners
    are always billed, so a false ``"larger"`` is the safe direction.
    """
    if item is not None and item.get("unitType") == "gigabyte-hours":
        return "storage"
    return "standard" if is_standard_runner_sku(sku) else "larger"


def split_rows_by_visibility(
    rows: list[dict],
    *,
    minutes_key: str = "minutes",
    storage_key: str | None = "storage_gb_hours",
    sku_key: str | None = "sku",
) -> dict[str, dict]:
    """Aggregate per-repo rows by visibility into
    ``{visibility: {minutes, <storage_key>, skus: {...}}}``.

    Visibility resolution delegates to ``visibility.repo_visibility(row)``;
    ``"internal"`` folds into ``"private"`` for billing purposes. Skips SKU
    aggregation when ``sku_key`` is ``None``.
    """
    out: dict[str, dict] = {"private": {"minutes": 0.0}, "public": {"minutes": 0.0}}
    if storage_key is not None:
        out["private"][storage_key] = 0.0
        out["public"][storage_key] = 0.0
    if sku_key is not None:
        out["private"]["skus"] = {}
        out["public"]["skus"] = {}

    for row in rows or []:
        vis = repo_visibility(row)
        if vis == "internal":
            vis = "private"
        if vis not in out:
            out[vis] = {"minutes": 0.0}
            if storage_key is not None:
                out[vis][storage_key] = 0.0
            if sku_key is not None:
                out[vis]["skus"] = {}
        out[vis]["minutes"] += float(row.get(minutes_key, 0.0) or 0.0)
        if storage_key is not None:
            out[vis][storage_key] += float(row.get(storage_key, 0.0) or 0.0)
        if sku_key is not None:
            skus = row.get(sku_key) or {}
            for sku, item in skus.items():
                out[vis]["skus"][sku] = sanitize_item_amounts(item)
    return out


def _larger_runner_skus(split: dict[str, dict]) -> list[str]:
    seen: set[str] = set()
    for vis in ("private", "public"):
        for sku in split.get(vis, {}).get("skus") or {}:
            if classify_actions_sku(sku) == "larger":
                seen.add(sku)
    return sorted(seen)


def finalize_actions_split(
    split: dict[str, dict],
    *,
    account_minutes: float,
    account_storage_gb_hours: float,
    private_minutes_limit: float = _PRIVATE_MINUTES_LIMIT,
    storage_limit_gb: float = _PRIVATE_STORAGE_LIMIT_GB,
    filtered: bool = False,
) -> dict:
    """Return the split augmented with ``unattributed`` (account minus scanned
    sum) and ``private_minutes_percent``/``larger_runner_skus``/``filtered``.

    Account totals are authoritative; ``unattributed`` absorbs the remainder.
    A negative remainder is clamped to 0 and ``reconciled`` is set false.
    """
    priv = split.get("private", {"minutes": 0.0})
    pub = split.get("public", {"minutes": 0.0})
    private_minutes = float(priv.get("minutes", 0.0) or 0.0)
    public_minutes = float(pub.get("minutes", 0.0) or 0.0)
    scanned = private_minutes + public_minutes

    unattributed_minutes = max(0.0, account_minutes - scanned)
    reconciled = scanned <= account_minutes

    private_storage = float(priv.get("storage_gb_hours", 0.0) or 0.0)
    public_storage = float(pub.get("storage_gb_hours", 0.0) or 0.0)
    scanned_storage = private_storage + public_storage
    unattributed_storage = max(0.0, account_storage_gb_hours - scanned_storage)
    reconciled_storage = scanned_storage <= account_storage_gb_hours

    private_storage_avg_mb = private_storage  # GB-hrs over a full month ~ avg MB scaling
    public_storage_avg_mb = public_storage

    pct = (private_minutes / private_minutes_limit * 100.0) if private_minutes_limit else 0.0

    return {
        "private_minutes": private_minutes,
        "public_minutes": public_minutes,
        "unattributed_minutes": unattributed_minutes,
        "private_minutes_percent": pct,
        "private_storage_gb_hours": private_storage,
        "public_storage_gb_hours": public_storage,
        "unattributed_storage_gb_hours": unattributed_storage,
        "private_storage_avg_mb": private_storage_avg_mb,
        "public_storage_avg_mb": public_storage_avg_mb,
        "larger_runner_skus": _larger_runner_skus(split),
        "filtered": filtered,
        "reconciled": reconciled and reconciled_storage,
        "skus": {
            "private": split.get("private", {}).get("skus", {}),
            "public": split.get("public", {}).get("skus", {}),
        },
    }


def storage_allowance_gb_hours(days_in_month: int) -> float:
    """Full private artifact allowance expressed as GB-hrs: 0.5 GB flat all
    month = ``0.5 * 24 * days`` (360 for 30 days, 372 for 31, 336 for a
    28-day February). Callers must pass ``days_in_month(reference_date)`` so a
    prior-month/``--as-of`` report matches the usage month.
    """
    return _PRIVATE_STORAGE_LIMIT_GB * 24.0 * days_in_month


def flat_equivalent_gb_hours(gb_hours: float, days_in_month: int) -> float:
    """GB that would have to sit flat all month to produce ``gb_hours``
    (e.g. 165.29 GB-hrs with 31 days ≈ 0.22 GB ≈ 230 MB flat all month).
    Assumes the input GB-hours accrued over a full billing cycle of
    ``days_in_month`` days — a mid-month snapshot understates the
    flat-equivalent.
    """
    hours = 24 * days_in_month
    return gb_hours / hours if hours > 0 else 0.0


def attach_actions_visibility_split(
    report: dict,
    repo_actions: list[dict],
    *,
    only_public: bool = False,
    only_private: bool = False,
) -> dict:
    """Attach the visibility split to ``report["actions"]`` in place.

    Skips when ``actions`` is ``None`` (fetch error). Reuses the AGENTS.md
    single-source-of-truth rule: storage_summary headroom is filled by
    build_legacy_report_data (Phase 2c), not here.
    """
    actions = report.get("actions")
    if not actions:
        return report
    split = split_rows_by_visibility(repo_actions)
    finalized = finalize_actions_split(
        split,
        account_minutes=float(actions.get("minutes", 0.0) or 0.0),
        account_storage_gb_hours=float(actions.get("storage_gb_hours", 0.0) or 0.0),
        filtered=only_public or only_private,
    )
    merged = dict(actions)
    merged.update(finalized)
    report["actions"] = merged
    return report
