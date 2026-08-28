"""Read-only readiness checks for a persistent governed worker worktree."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time


_GIT = "/usr/bin/git"
_GIT_TIMEOUT_SECONDS = 5
_TERMINATION_GRACE_SECONDS = 0.2
_MAX_OUTPUT_BYTES = 4096
_FEATURE_BRANCH = re.compile(r"^task-[a-z0-9][a-z0-9-]{0,100}$")
_GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
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


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    group_id = process.pid
    try:
        os.killpg(group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + _TERMINATION_GRACE_SECONDS
    while time.monotonic() < deadline and _process_group_exists(group_id):
        time.sleep(0.01)
    if _process_group_exists(group_id):
        try:
            os.killpg(group_id, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=_TERMINATION_GRACE_SECONDS)
    except (subprocess.TimeoutExpired, ProcessLookupError):
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
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    output = bytearray()
    try:
        process = subprocess.Popen(
            [
                _GIT,
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                *arguments,
            ],
            cwd=repo,
            env=_GIT_ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if process.stdout is None:  # pragma: no cover - defensive
            raise _ProbeFailure
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + _GIT_TIMEOUT_SECONDS
        stream_open = True
        while stream_open or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _ProbeFailure
            for key, _ in selector.select(timeout=min(0.1, remaining)):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    stream_open = False
                    continue
                output.extend(chunk)
                if len(output) > _MAX_OUTPUT_BYTES:
                    raise _ProbeFailure
        returncode = process.wait(timeout=0.1)
        if returncode != 0:
            raise _ProbeFailure
    except (OSError, subprocess.SubprocessError, _ProbeFailure) as exc:
        if process is not None:
            _terminate_process_group(process)
        raise _ProbeFailure from exc
    finally:
        if selector is not None:
            selector.close()
        if process is not None and process.stdout is not None:
            process.stdout.close()
    try:
        return bytes(output).decode("utf-8", errors="strict").strip()
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


def _is_registered_worktree(source: Path, candidate: _DirectoryBinding) -> bool:
    listing = _git(source, "worktree", "list", "--porcelain", "-z")
    registered_paths = [
        field[len("worktree ") :]
        for field in listing.split("\0")
        if field.startswith("worktree ")
    ]
    for value in registered_paths:
        binding, _ = _safe_directory(Path(value))
        if binding is None:
            continue
        if binding.path != candidate.path:
            continue
        if (binding.device, binding.inode) == (candidate.device, candidate.inode):
            return True
    return False


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
        top_level = _git(candidate.path, "rev-parse", "--show-toplevel")
        top_binding, _ = _safe_directory(Path(top_level))
        if top_binding is None or (
            top_binding.device,
            top_binding.inode,
        ) != (candidate.device, candidate.inode):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.WORKSPACE_UNSAFE
            )
        if _common_directory(source.path) != _common_directory(candidate.path):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.FOREIGN_REPOSITORY
            )
        if not _is_registered_worktree(source.path, candidate):
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.WORKSPACE_UNSAFE
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
        first_status = _git(
            candidate.path, "status", "--porcelain=v1", "--untracked-files=all"
        )
        if first_status:
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
        final_branch = _git(
            candidate.path, "symbolic-ref", "--quiet", "--short", "HEAD"
        )
        final_status = _git(
            candidate.path, "status", "--porcelain=v1", "--untracked-files=all"
        )
        if final_branch != branch:
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.WORKSPACE_UNSAFE
            )
        if final_status:
            return PersistentWorkspaceReadiness(
                False, WorkspaceReadinessReason.DIRTY_WORKTREE, final_branch
            )
        last_candidate, _ = _safe_directory(candidate.path)
        if last_candidate is None or (
            last_candidate.device,
            last_candidate.inode,
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
