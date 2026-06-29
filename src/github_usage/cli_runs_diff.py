"""Implementation of the ``github-usage runs --diff`` subcommand.

Compares the local state of ``.github/workflows/email-report*.yml`` against
the configured remote's default branch and reports per-file drift. Does
not require a GitHub token; only ``git`` on ``PATH`` and a git working
tree. Only ``git fetch <remote>`` is a network operation; it is opt-out
via ``--no-fetch`` or ``GITHUB_USAGE_SKIP_FETCH=1``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Mapping
from pathlib import Path

# Module-level env for all git subprocess calls. ``LC_ALL=C`` ensures
# stable sort order in porcelain output regardless of the user's locale.
GIT_ENV: dict[str, str] = {**os.environ, "LC_ALL": "C"}

# Valid drift categories. Asserted by tests.
DRIFT_CATEGORIES: frozenset[str] = frozenset(
    {
        "in-sync",
        "uncommitted",
        "staged",
        "untracked",
        "ahead",
        "behind",
        "remote-only",
        "diverged",
        "unknown",
    }
)

# Subprocess timeout for non-fetch git calls. ``git fetch`` uses a higher
# timeout (see ``fetch_remote``).
_SUBPROCESS_TIMEOUT = 30

# Sentinel summary used when a row cannot be classified because the remote
# default-branch ref is unavailable.
_NO_REMOTE_REF_SUMMARY = "no remote default branch ref available"

# Error messages emitted by ``main()`` to stderr.
ERR_GIT_MISSING = "Error: git is required for --diff but was not found on PATH."
ERR_NOT_GIT_REPO = "Error: --diff must be run from within a git repository."
ERR_OWNER_REPO_WITH_DIFF = "Error: --owner and --repo only apply to --api."
ERR_NO_FETCH_WITHOUT_DIFF = "Error: --no-fetch only applies to --diff."
ERR_PROFILE_NOT_FOUND_TEMPLATE = "Error: Profile '{name}' not found in configuration."
NO_GA_WORKFLOW_NOTICE_TEMPLATE = "notice: profile '{name}' has no GitHub Actions workflow"
FETCH_FALLBACK_WARNING_TEMPLATE = (
    "warning: fetch of {remote} failed; falling back to cached refs ({remote}/{default_branch})"
)


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = _SUBPROCESS_TIMEOUT,
    env: Mapping[str, str] = GIT_ENV,
) -> subprocess.CompletedProcess:
    """Run a git command and return the CompletedProcess.

    Resolves ``git`` to an absolute executable path first so subprocesses do not
    depend on ``PATH`` lookup semantics. Always uses ``check=False`` so callers
    handle non-zero exits via ``returncode``. Raises ``FileNotFoundError`` (no
    git binary) or ``subprocess.SubprocessError`` (timeout) which the caller is
    expected to catch.
    """
    git_executable = shutil.which("git")
    if git_executable is None:
        raise FileNotFoundError("git not found")
    return subprocess.run(  # nosec B404,B603
        [git_executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=dict(env),
    )


def resolve_remote_name(repo_root: Path) -> str:
    """Return the configured remote name for the current branch.

    Reads ``git config branch.<current>.remote`` (after
    ``git rev-parse --abbrev-ref HEAD``) and falls back to ``"origin"`` if
    the config key is missing or the lookup fails — this includes the
    detached-HEAD case, where ``git rev-parse --abbrev-ref HEAD`` returns
    ``"HEAD"`` rather than a branch name, so the subsequent config lookup
    is a guaranteed miss and the fallback applies. Never raises.
    """
    try:
        branch_proc = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return "origin"
    if not branch or branch == "HEAD":
        return "origin"
    try:
        config_proc = _run_git(["config", f"branch.{branch}.remote"], cwd=repo_root)
        if config_proc.returncode == 0:
            remote = config_proc.stdout.strip()
            if remote:
                return remote
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return "origin"


def resolve_default_branch(repo_root: Path, remote: str) -> str | None:
    """Return the first verified default-branch candidate, or ``None``.

    Tries ``git symbolic-ref refs/remotes/<remote>/HEAD`` first, then
    falls back to ``main`` and ``master``. Each candidate is verified
    with ``git rev-parse --verify refs/remotes/<remote>/<branch>`` before
    being selected, so picking ``main`` when only ``master`` exists
    locally does not fail every subsequent ``git ls-tree`` call. Returns
    ``None`` if none of the candidates exist locally.
    """
    try:
        sym_proc = _run_git(["symbolic-ref", f"refs/remotes/{remote}/HEAD"], cwd=repo_root)
        if sym_proc.returncode == 0:
            ref = sym_proc.stdout.strip()
            # ref looks like "refs/remotes/origin/main"; extract the branch.
            prefix = f"refs/remotes/{remote}/"
            if ref.startswith(prefix):
                return ref[len(prefix) :]
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    for candidate in ("main", "master"):
        ref = f"refs/remotes/{remote}/{candidate}"
        try:
            verify_proc = _run_git(["rev-parse", "--verify", ref], cwd=repo_root)
            if verify_proc.returncode == 0:
                return candidate
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
    return None


def fetch_remote(
    repo_root: Path,
    remote: str,
    *,
    skip_fetch: bool,
    env: Mapping[str, str],
) -> tuple[bool, bool]:
    """Run ``git fetch <remote>`` unless ``skip_fetch`` is True.

    Returns ``(fetched, using_cached_ref)``:
      - ``(True, False)`` — fresh fetch succeeded.
      - ``(False, False)`` — fetch was skipped, or failed and we have no
        cached ref to fall back on. The subsequent
        ``resolve_default_branch`` call will then fall back to whatever
        cached refs exist locally (or return ``None`` if none).

    The cached-ref check lives in ``resolve_default_branch`` (via
    ``git rev-parse --verify``); this function does not need to know
    about it. The fetch must run **before** ``resolve_default_branch``
    is called, so that the default-branch resolver sees fresh refs on
    first run. Never raises.
    """
    if skip_fetch:
        return False, False
    try:
        fetch_proc = _run_git(["fetch", remote], cwd=repo_root, timeout=60, env=env)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False, False
    return (fetch_proc.returncode == 0), False


def _normalize_path(p: str | Path, repo_root: Path) -> str:
    """Return ``p`` as a repo-relative POSIX string.

    Handles both absolute paths (from ``Path.glob``) and relative paths
    (from ``git ls-tree``/``ls-files``). The naive
    ``Path(p).relative_to(repo_root)`` would raise ``ValueError`` on
    the relative case because ``p`` does not start with the absolute
    ``repo_root``.
    """
    pp = Path(p)
    if pp.is_absolute():
        return pp.relative_to(repo_root).as_posix()
    return pp.as_posix()


def _git_status_porcelain(repo_root: Path, pathspec: str = ".github/workflows/") -> dict[str, str]:
    """Run ``git status --porcelain=v1 -- <pathspec>`` and return ``{path: line}``.

    Skipped (returns ``{}``) if the subprocess fails for any reason;
    callers must tolerate missing entries (a clean tracked file does
    not appear in ``git status`` output).
    """
    try:
        proc = _run_git(["status", "--porcelain=v1", "--", pathspec], cwd=repo_root)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    result: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        # Format: "XY path" where XY is the two-char status. Renames use
        # "XY old -> new"; we want the new path.
        if " -> " in line:
            _, _, new = line.partition(" -> ")
            status = line[:2]
            path = new.strip()
        else:
            status = line[:2]
            path = line[3:].strip()
        result[path] = status
    return result


def _classify_status(status: str) -> tuple[str, str] | None:
    """Return ``(drift, summary)`` for a porcelain status code, or ``None``.

    Precedence rules:
      - ``??`` → ``"untracked"``, summary ``"untracked file"``.
      - Y (working tree) non-space → ``"uncommitted"``, summary
        ``"uncommitted changes in working tree"``.
      - X (index) non-space and Y space → ``"staged"``, summary
        ``"staged changes in index"``.
      - Otherwise (empty or both spaces) → ``None`` (caller proceeds to
        blob comparison).
    """
    if not status:
        return None
    x, y = status[0], status[1] if len(status) > 1 else " "
    if x == "?" and y == "?":
        return "untracked", "untracked file"
    if y != " ":
        return "uncommitted", "uncommitted changes in working tree"
    if x != " ":
        return "staged", "staged changes in index"
    return None


def _classify_three_dot(
    *,
    ahead_diff: str,
    behind_diff: str,
    local_blob: str | None,
    remote_blob: str | None,
    default_branch: str | None,
) -> tuple[str, str]:
    """Return ``(drift, summary)`` from the three-dot diffs and blob presence."""
    if ahead_diff and behind_diff:
        return "diverged", "local and remote have diverged"
    if ahead_diff:
        if local_blob is None and remote_blob:
            return "ahead", "deleted locally, not pushed"
        if local_blob and remote_blob is None:
            return "ahead", "added locally, not pushed"
        return "ahead", "local has newer version"
    # behind_diff only (or both empty, which can't happen if hashes differ).
    if local_blob is None:
        return "remote-only", "added on remote, not pulled"
    if remote_blob is None:
        return "behind", "deleted on remote, not pulled"
    if default_branch is None:
        return "behind", _NO_REMOTE_REF_SUMMARY
    return "behind", "remote has newer version"


def _get_blob(repo_root: Path, ref: str | None, path: str) -> str | None:
    """Return the blob hash for ``path`` at ``ref``, or ``None`` if absent."""
    if not ref:
        return None
    try:
        proc = _run_git(["ls-tree", ref, "--", path], cwd=repo_root)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    if not out:
        return None
    # Format: "<mode> <type> <object>\t<file>"
    parts = out.split()
    if len(parts) < 3:
        return None
    return parts[2]


def _list_local_paths(repo_root: Path) -> list[str]:
    """Return repo-relative POSIX paths of local workflow files.

    Combines three sources so files in any local state are discovered:
      - ``git ls-tree -r HEAD`` (committed at HEAD, including those
        staged for deletion which ``git ls-files`` would omit).
      - ``git ls-files`` (tracked, indexed).
      - ``Path.glob`` (untracked, on-disk files).
    """
    paths: set[str] = set()
    try:
        proc = _run_git(
            ["ls-tree", "-r", "HEAD", "--", ".github/workflows/"],
            cwd=repo_root,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                # Format: "<mode> <type> <object>\t<file>"
                tab = line.find("\t")
                if tab == -1:
                    continue
                rel = line[tab + 1 :]
                if _WORKFLOW_GLOB.match(rel):
                    paths.add(_normalize_path(rel, repo_root))
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    try:
        proc = _run_git(
            ["ls-files", "--", ".github/workflows/email-report*.yml"],
            cwd=repo_root,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    paths.add(_normalize_path(line, repo_root))
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    workflows_dir = repo_root / ".github" / "workflows"
    if workflows_dir.is_dir():
        for wf in workflows_dir.glob("email-report*.yml"):
            paths.add(_normalize_path(wf, repo_root))
    return sorted(paths)


def _list_remote_paths(repo_root: Path, remote: str, default_branch: str | None) -> list[str]:
    """Return repo-relative POSIX paths of remote workflow files.

    Returns ``[]`` if ``default_branch`` is ``None`` (the caller should
    then degrade affected rows to ``unknown`` with the
    ``_NO_REMOTE_REF_SUMMARY``).
    """
    if not default_branch:
        return []
    try:
        proc = _run_git(
            [
                "ls-tree",
                "-r",
                f"{remote}/{default_branch}",
                "--",
                ".github/workflows/",
            ],
            cwd=repo_root,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    paths: set[str] = set()
    for line in proc.stdout.splitlines():
        tab = line.find("\t")
        if tab == -1:
            continue
        rel = line[tab + 1 :]
        if _WORKFLOW_GLOB.match(rel):
            paths.add(_normalize_path(rel, repo_root))
    return sorted(paths)


_WORKFLOW_GLOB = re.compile(r"\.github/workflows/email-report[^/]*\.yml$")


def classify_drift(
    repo_root: Path,
    remote: str,
    default_branch: str | None,
    *,
    candidate_path: Path | None = None,
) -> list[dict]:
    """Return one row per workflow file in scope.

    When ``candidate_path`` is set, the candidate set is exactly that
    single path. Otherwise the candidate set is the union of local
    paths and remote paths, both filtered to the ``email-report*.yml``
    glob. The output rows have ``path``, ``drift``, and ``summary``
    fields; ``drift`` is always one of ``DRIFT_CATEGORIES``.
    """
    if candidate_path is not None:
        candidates = [_normalize_path(candidate_path, repo_root)]
    else:
        local = _list_local_paths(repo_root)
        remote_paths = _list_remote_paths(repo_root, remote, default_branch)
        # Remote-first ordering, then local-only (per the plan).
        seen: set[str] = set()
        candidates = []
        for p in remote_paths + local:
            if p not in seen:
                seen.add(p)
                candidates.append(p)

    if not candidates:
        return []

    # Single batched git status call covers all candidate paths.
    status_map = _git_status_porcelain(repo_root)

    return [
        row
        for path in candidates
        for row in [_classify_one_path(repo_root, path, remote, default_branch, status_map)]
        if row is not None
    ]


def _classify_one_path(
    repo_root: Path,
    path: str,
    remote: str,
    default_branch: str | None,
    status_map: dict[str, str],
) -> dict | None:
    """Return a single drift row for ``path``, or ``None`` to skip it.

    Applies the per-file classification rules in order: porcelain
    status (uncommitted / staged / untracked), then blob comparison
    (in-sync), then three-dot diff direction (ahead / behind /
    remote-only / diverged), degrading to ``unknown`` when no remote
    ref is available.
    """
    status = status_map.get(path, "")
    classified = _classify_status(status)
    if classified is not None:
        drift, summary = classified
        return {"path": path, "drift": drift, "summary": summary}

    local_blob = _get_blob(repo_root, "HEAD", path)
    remote_blob = _get_blob(
        repo_root,
        f"{remote}/{default_branch}" if default_branch else None,
        path,
    )
    if local_blob is None and remote_blob is None:
        # File doesn't exist anywhere; skip silently.
        return None
    if local_blob is not None and local_blob == remote_blob:
        return {
            "path": path,
            "drift": "in-sync",
            "summary": f"in sync with {remote}/{default_branch or '<no-default-branch>'}",
        }

    if not default_branch:
        # No remote ref available; this row needs a remote check.
        return {
            "path": path,
            "drift": "unknown",
            "summary": _NO_REMOTE_REF_SUMMARY,
        }

    ahead_diff, behind_diff = _run_three_dot_diffs(repo_root, remote, default_branch, path)
    drift, summary = _classify_three_dot(
        ahead_diff=ahead_diff,
        behind_diff=behind_diff,
        local_blob=local_blob,
        remote_blob=remote_blob,
        default_branch=default_branch,
    )
    return {"path": path, "drift": drift, "summary": summary}


def _run_three_dot_diffs(
    repo_root: Path, remote: str, default_branch: str, path: str
) -> tuple[str, str]:
    """Run the two three-dot diffs for a single path. Returns ``(ahead, behind)``.

    Both outputs are empty strings when the underlying ``git diff`` call
    fails (non-zero exit, missing git, timeout, etc.); the caller
    handles "both empty" as a degenerate case in the three-dot
    classification rules.
    """
    ahead_diff = ""
    behind_diff = ""
    try:
        ahead_proc = _run_git(
            ["diff", f"{remote}/{default_branch}...HEAD", "--", path],
            cwd=repo_root,
        )
        ahead_diff = ahead_proc.stdout if ahead_proc.returncode == 0 else ""
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    try:
        behind_proc = _run_git(
            ["diff", f"HEAD...{remote}/{default_branch}", "--", path],
            cwd=repo_root,
        )
        behind_diff = behind_proc.stdout if behind_proc.returncode == 0 else ""
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return ahead_diff, behind_diff


def _print_drift(rows: list[dict], remote: str, default_branch: str | None) -> None:
    """Print a compact drift table to stdout."""
    if not rows:
        print("No drift detected.")
        return
    print("Drift:")
    for row in rows:
        print(f"  {row['path']} · {row['drift']} · {row['summary']}")


def render_drift(
    rows: list[dict],
    *,
    remote: str,
    default_branch: str | None,
    fetched: bool,
    using_cached_ref: bool,
    skipped_fetch: bool,
    as_json: bool = False,
) -> str:
    """Render the drift output as either JSON or human-readable text."""
    if as_json:
        payload = {
            "kind": "diff",
            "default_branch": default_branch,
            "remote": remote,
            "rows": rows,
            "fetched": fetched,
            "using_cached_ref": using_cached_ref,
            "skipped_fetch": skipped_fetch,
        }
        return json.dumps(payload, indent=2)
    import io

    buf = io.StringIO()
    saved_stdout = sys.stdout
    sys.stdout = buf
    try:
        _print_drift(rows, remote, default_branch)
    finally:
        sys.stdout = saved_stdout
    return buf.getvalue()


def check_prerequisites(repo_root: Path) -> str | None:
    """Return an error message string if prerequisites are missing, else ``None``.

    Used by ``cli_runs.main()`` to fail fast before any subprocess work
    when the environment is unsuitable for ``--diff``.
    """
    if shutil.which("git") is None:
        return ERR_GIT_MISSING
    if not (repo_root / ".git").exists():
        return ERR_NOT_GIT_REPO
    return None
