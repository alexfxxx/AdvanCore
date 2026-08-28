"""Read-only readiness checks for a persistent governed worker worktree."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
import stat
import subprocess


_GIT = "/usr/bin/git"
_GIT_TIMEOUT_SECONDS = 5
_MAX_OUTPUT_BYTES = 4096
_FEATURE_BRANCH = re.compile(r"^task-[a-z0-9][a-z0-9-]{0,100}$")
_GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


class WorkspaceReadinessReason(str, Enum):
    READY = "READY"
    WORKSPACE_MISSING = "WORKSPACE_MISSING"
    WORKSPACE_UNSAFE = "WORKSPACE_UNSAFE"
    GIT_PROBE_FAILED = "GIT_PROBE_FAILED"
    FOREIGN_REPOSITORY = "FOREIGN_REPOSITORY"
    DIRTY_WORKTREE = "DIRTY_WORKTREE"
    DETACHED_HEAD = "DETACHED_HEAD"
    UNSAFE_BRANCH = "UNSAFE_BRANCH"


@dataclass(frozen=True)
class PersistentWorkspaceReadiness:
    """Bounded controller-facing result with no path, output or credential data."""

    eligible: bool
    reason: WorkspaceReadinessReason
    branch: str | None = None


class _ProbeFailure(RuntimeError):
    pass


def _has_symlink_component(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            details = os.lstat(current)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(details.st_mode):
            return True
    return False


def _git(repo: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            [_GIT, *arguments],
            cwd=repo,
            env=_GIT_ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ProbeFailure from exc
    if result.returncode != 0 or len(result.stdout) > _MAX_OUTPUT_BYTES:
        raise _ProbeFailure
    try:
        return result.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeError as exc:
        raise _ProbeFailure from exc


def _safe_directory(path: Path) -> Path | None:
    lexical = path.absolute()
    if _has_symlink_component(lexical):
        return None
    try:
        resolved = lexical.resolve(strict=True)
        details = resolved.stat()
    except OSError:
        return None
    if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid():
        return None
    return resolved


def _common_directory(repo: Path) -> Path:
    value = _git(repo, "rev-parse", "--git-common-dir")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo / candidate
    return candidate.resolve(strict=True)


def inspect_persistent_kimi_workspace(
    controller_repository: Path, worker_workspace: Path
) -> PersistentWorkspaceReadiness:
    """Inspect one existing Kimi worktree without modifying it.

    The caller must repeat this preflight immediately before governed launch;
    this function deliberately cannot create, clean, reset, switch or trust a
    worktree.
    """
    source = _safe_directory(Path(controller_repository))
    candidate_path = Path(worker_workspace)
    if not candidate_path.exists():
        return PersistentWorkspaceReadiness(
            False, WorkspaceReadinessReason.WORKSPACE_MISSING
        )
    candidate = _safe_directory(candidate_path)
    if source is None or candidate is None or candidate == source:
        return PersistentWorkspaceReadiness(
            False, WorkspaceReadinessReason.WORKSPACE_UNSAFE
        )

    try:
        if _git(source, "rev-parse", "--is-inside-work-tree") != "true":
            raise _ProbeFailure
        if _git(candidate, "rev-parse", "--is-inside-work-tree") != "true":
            raise _ProbeFailure
        if _common_directory(source) != _common_directory(candidate):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.FOREIGN_REPOSITORY
            )
        try:
            branch = _git(candidate, "symbolic-ref", "--quiet", "--short", "HEAD")
        except _ProbeFailure:
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.DETACHED_HEAD
            )
        if not _FEATURE_BRANCH.fullmatch(branch):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.UNSAFE_BRANCH
            )
        if _git(candidate, "status", "--porcelain=v1", "--untracked-files=all"):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.DIRTY_WORKTREE, branch
            )
    except (OSError, _ProbeFailure):
        return PersistentWorkspaceReadiness(
            False, WorkspaceReadinessReason.GIT_PROBE_FAILED
        )

    return PersistentWorkspaceReadiness(
        True, WorkspaceReadinessReason.READY, branch
    )
