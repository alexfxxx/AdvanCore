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


@dataclass(frozen=True)
class _DirectoryBinding:
    path: Path
    device: int
    inode: int


class _ProbeFailure(RuntimeError):
    pass


def _open_directory_no_follow(path: Path) -> int:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        result = descriptor
        descriptor = -1
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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


def _safe_directory(path: Path) -> tuple[_DirectoryBinding | None, bool]:
    lexical = path.absolute()
    descriptor: int | None = None
    try:
        descriptor = _open_directory_no_follow(lexical)
        details = os.fstat(descriptor)
    except FileNotFoundError:
        return None, True
    except OSError:
        return None, False
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid():
        return None, False
    return _DirectoryBinding(lexical, details.st_dev, details.st_ino), False


def _common_directory(repo: Path) -> tuple[int, int]:
    value = _git(repo, "rev-parse", "--git-common-dir")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo / candidate
    binding, _ = _safe_directory(candidate)
    if binding is None:
        raise _ProbeFailure
    return binding.device, binding.inode


def inspect_persistent_kimi_workspace(
    controller_repository: Path, worker_workspace: Path
) -> PersistentWorkspaceReadiness:
    """Inspect one existing Kimi worktree without modifying it.

    The caller must repeat this preflight immediately before governed launch;
    this function deliberately cannot create, clean, reset, switch or trust a
    worktree.
    """
    source, _ = _safe_directory(Path(controller_repository))
    candidate, candidate_missing = _safe_directory(Path(worker_workspace))
    if candidate_missing:
        return PersistentWorkspaceReadiness(
            False, WorkspaceReadinessReason.WORKSPACE_MISSING
        )
    if (
        source is None
        or candidate is None
        or (candidate.device, candidate.inode) == (source.device, source.inode)
    ):
        return PersistentWorkspaceReadiness(
            False, WorkspaceReadinessReason.WORKSPACE_UNSAFE
        )

    try:
        if _git(source.path, "rev-parse", "--is-inside-work-tree") != "true":
            raise _ProbeFailure
        if _git(candidate.path, "rev-parse", "--is-inside-work-tree") != "true":
            raise _ProbeFailure
        if _common_directory(source.path) != _common_directory(candidate.path):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.FOREIGN_REPOSITORY
            )
        try:
            branch = _git(
                candidate.path, "symbolic-ref", "--quiet", "--short", "HEAD"
            )
        except _ProbeFailure:
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.DETACHED_HEAD
            )
        if not _FEATURE_BRANCH.fullmatch(branch):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.UNSAFE_BRANCH
            )
        if _git(
            candidate.path, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.DIRTY_WORKTREE, branch
            )
        final_candidate, _ = _safe_directory(candidate.path)
        if final_candidate is None or (
            final_candidate.device,
            final_candidate.inode,
        ) != (candidate.device, candidate.inode):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.WORKSPACE_UNSAFE
            )
    except (OSError, _ProbeFailure):
        return PersistentWorkspaceReadiness(
            False, WorkspaceReadinessReason.GIT_PROBE_FAILED
        )

    return PersistentWorkspaceReadiness(
        True, WorkspaceReadinessReason.READY, branch
    )
