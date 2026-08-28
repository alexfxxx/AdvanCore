"""Fail-closed launch boundary for one persistent Kimi Swarm worktree."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import re
import selectors
import secrets
import signal
import stat
import subprocess
import sys
import time
from typing import Callable, Iterator

from advancore.agent_runner.auto_pipeline import build_scope_result
from advancore.agent_runner.kimi_scope_manifest import (
    KimiScopeManifestError,
    build_kimi_scope_manifest,
    verify_kimi_scope_manifest,
)
from advancore.agent_runner.kimi_swarm_eligibility import (
    ManifestVerificationEvidence,
    SwarmEligibilityReason,
    SwarmWorkKind,
    evaluate_kimi_swarm_eligibility,
)
from advancore.agent_runner.persistent_worker_workspace import (
    PersistentWorkspaceReadiness,
    WorkspaceReadinessReason,
    inspect_persistent_kimi_workspace,
)
from advancore.agent_runner.scope_reservations import ScopeReservation
from advancore.agent_runner.task_queue import TaskQueueRecord
from advancore.agent_runner.worker import (
    EXECUTABLE_NOT_FOUND,
    MAX_WORKER_TIMEOUT_SECONDS,
    RUNTIME_ERROR,
    SPAWN_ERROR,
    KimiSwarmWorkerAdapter,
    WorkerResult,
    build_kimi_swarm_instruction,
)


class PersistentKimiLaunchStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    WORKER_FAILED = "WORKER_FAILED"
    POSTCHECK_FAILED = "POSTCHECK_FAILED"


class PersistentKimiLaunchReason(str, Enum):
    COMPLETED = "COMPLETED"
    WORKSPACE_NOT_READY = "WORKSPACE_NOT_READY"
    MANIFEST_NOT_VERIFIED = "MANIFEST_NOT_VERIFIED"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    WORKER_EXCEPTION = "WORKER_EXCEPTION"
    WORKER_FAILED = "WORKER_FAILED"
    GIT_STATE_UNAVAILABLE = "GIT_STATE_UNAVAILABLE"
    BRANCH_OR_HEAD_CHANGED = "BRANCH_OR_HEAD_CHANGED"
    STAGED_OR_AMBIGUOUS_CHANGES = "STAGED_OR_AMBIGUOUS_CHANGES"
    OUT_OF_SCOPE_CHANGES = "OUT_OF_SCOPE_CHANGES"
    MANIFEST_CHANGED = "MANIFEST_CHANGED"
    LAUNCH_ALREADY_CONSUMED = "LAUNCH_ALREADY_CONSUMED"


@dataclass(frozen=True)
class PersistentKimiLaunchResult:
    """Bounded result that deliberately excludes commands and process streams."""

    ok: bool
    status: PersistentKimiLaunchStatus
    reason: PersistentKimiLaunchReason | SwarmEligibilityReason
    changed_paths: tuple[str, ...] = ()
    scope_count: int = 0
    worker_terminal_reason: str | None = None
    worker_failure_classification: str | None = None
    worker_returncode: int | None = None
    worker_elapsed_seconds: float | None = None
    worker_cli_version: str | None = None


WorkerRunner = Callable[[str, Path, tuple[str, ...]], WorkerResult]
Clock = Callable[[], datetime]
_GIT = "/usr/bin/git"
_GIT_TIMEOUT_SECONDS = 5
_GIT_OUTPUT_MAX_BYTES = 64 * 1024
_GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
}
_MAX_RECEIPTS = 128
_MAX_RECEIPT_SCAN = 256
_MAX_RECEIPT_BYTES = 256
_RECEIPT_NAME = re.compile(r"^[0-9a-f]{64}\.receipt$")
_BOUND_HELPER_OUTPUT_MAX_BYTES = 4096
_BOUND_HELPER_SOURCE = (
    "import os,sys; os.fchdir(int(sys.argv[1])); "
    "sys.path.insert(0,os.getcwd()); "
    "from advancore.agent_runner.persistent_kimi_launch "
    "import _descriptor_worker_entry; _descriptor_worker_entry()"
)


@dataclass(frozen=True)
class _GitSnapshot:
    root: Path
    branch: str
    head: str
    changed_paths: tuple[str, ...]
    staged_or_ambiguous: bool


@dataclass(frozen=True)
class _DirectoryBinding:
    path: Path
    device: int
    inode: int
    descriptor: int


@dataclass(frozen=True)
class _WorkerMetadata:
    terminal_reason: str | None
    failure_classification: str | None
    returncode: int | None
    elapsed_seconds: float | None
    cli_version: str | None


@dataclass(frozen=True)
class _ReceiptEvidence:
    claimed_at: str
    reserved_at: str
    expires_at: str
    expires_epoch_microseconds: int


_TERMINAL_REASONS = frozenset(
    {
        "completed",
        "launch_failed",
        "credential_access_required",
        "authority_blocked",
        "quota_or_capacity",
        "timeout",
        "cancelled",
        "runtime_error",
    }
)
_FAILURE_CLASSIFICATIONS = frozenset(
    {EXECUTABLE_NOT_FOUND, SPAWN_ERROR, RUNTIME_ERROR}
)


class _LaunchReceiptError(RuntimeError):
    pass


class _LaunchAlreadyConsumed(_LaunchReceiptError):
    pass


def _default_worker_runner(
    instruction: str, workspace: Path, allowed_paths: tuple[str, ...]
) -> WorkerResult:
    adapter = KimiSwarmWorkerAdapter(allowed_scope=list(allowed_paths))
    return adapter.run(instruction, workspace)


def _default_state_root() -> Path:
    owner_home = Path(pwd.getpwuid(os.getuid()).pw_dir).absolute()
    if sys.platform == "darwin":
        return (
            owner_home
            / "Library"
            / "Application Support"
            / "AdvanCore"
            / "agent_runner"
            / "persistent-kimi-launch"
        )
    return (
        owner_home
        / ".local"
        / "state"
        / "advancore"
        / "agent_runner"
        / "persistent-kimi-launch"
    )


def _plain_utc(value: datetime) -> datetime | None:
    if type(value) is not datetime or value.tzinfo is None:
        return None
    try:
        converted = value.astimezone(timezone.utc)
        return datetime(
            converted.year,
            converted.month,
            converted.day,
            converted.hour,
            converted.minute,
            converted.second,
            converted.microsecond,
            tzinfo=timezone.utc,
        )
    except Exception:
        return None


def _epoch_microseconds(value: datetime) -> int:
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (
        (delta.days * 86_400 + delta.seconds) * 1_000_000
        + delta.microseconds
    )


def _receipt_evidence(
    queue_record: TaskQueueRecord, reservation: ScopeReservation
) -> _ReceiptEvidence | None:
    claimed = _plain_utc(queue_record.claimed_at) if queue_record.claimed_at else None
    reserved = _plain_utc(reservation.reserved_at)
    expires = _plain_utc(reservation.expires_at)
    if claimed is None or reserved is None or expires is None:
        return None
    return _ReceiptEvidence(
        claimed.isoformat(timespec="microseconds"),
        reserved.isoformat(timespec="microseconds"),
        expires.isoformat(timespec="microseconds"),
        _epoch_microseconds(expires),
    )


def _worker_metadata(worker: WorkerResult | None) -> _WorkerMetadata:
    if worker is None:
        return _WorkerMetadata(None, None, None, None, None)
    terminal_reason = (
        worker.terminal_reason
        if isinstance(worker.terminal_reason, str)
        and worker.terminal_reason in _TERMINAL_REASONS
        else None
    )
    failure_classification = (
        worker.failure_classification
        if isinstance(worker.failure_classification, str)
        and worker.failure_classification in _FAILURE_CLASSIFICATIONS
        else None
    )
    returncode = (
        worker.returncode
        if isinstance(worker.returncode, int)
        and not isinstance(worker.returncode, bool)
        and -255 <= worker.returncode <= 255
        else None
    )
    elapsed_seconds = (
        float(worker.elapsed_seconds)
        if isinstance(worker.elapsed_seconds, (int, float))
        and not isinstance(worker.elapsed_seconds, bool)
        and math.isfinite(worker.elapsed_seconds)
        and 0 <= worker.elapsed_seconds <= MAX_WORKER_TIMEOUT_SECONDS + 5
        else None
    )
    cli_version = (
        worker.cli_version
        if isinstance(worker.cli_version, str)
        and len(worker.cli_version) <= 32
        and re.fullmatch(
            r"Kimi v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", worker.cli_version
        )
        else None
    )
    return _WorkerMetadata(
        terminal_reason,
        failure_classification,
        returncode,
        elapsed_seconds,
        cli_version,
    )


def _descriptor_worker_entry() -> None:
    """Run the fixed Kimi adapter from a helper already fchdir-bound by FD."""
    try:
        raw = sys.stdin.buffer.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            raise ValueError("helper input exceeded its bound")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {
            "allowed_paths",
            "device",
            "inode",
            "instruction",
        }:
            raise ValueError("helper input is malformed")
        descriptor = int(sys.argv[1])
        details = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_dev != payload["device"]
            or details.st_ino != payload["inode"]
            or not isinstance(payload["instruction"], str)
            or not isinstance(payload["allowed_paths"], list)
            or not all(isinstance(value, str) for value in payload["allowed_paths"])
        ):
            raise ValueError("helper workspace binding is invalid")
        result = _default_worker_runner(
            payload["instruction"], Path("."), tuple(payload["allowed_paths"])
        )
        metadata = _worker_metadata(result)
        response = {
            "cli_version": metadata.cli_version,
            "elapsed_seconds": metadata.elapsed_seconds,
            "failure_classification": metadata.failure_classification,
            "returncode": metadata.returncode,
            "success": result.success is True,
            "terminal_reason": metadata.terminal_reason,
        }
    except Exception:
        response = {
            "cli_version": None,
            "elapsed_seconds": None,
            "failure_classification": SPAWN_ERROR,
            "returncode": None,
            "success": False,
            "terminal_reason": "launch_failed",
        }
    encoded = json.dumps(
        response, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    if len(encoded) <= _BOUND_HELPER_OUTPUT_MAX_BYTES:
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


def _run_descriptor_bound_worker(
    instruction: str,
    binding: _DirectoryBinding,
    allowed_paths: tuple[str, ...],
) -> WorkerResult:
    payload = json.dumps(
        {
            "allowed_paths": list(allowed_paths),
            "device": binding.device,
            "inode": binding.inode,
            "instruction": instruction,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", _BOUND_HELPER_SOURCE, str(binding.descriptor)],
            cwd="/",
            env=os.environ.copy(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=(binding.descriptor,),
            start_new_session=True,
        )
        output, _ = process.communicate(
            input=payload, timeout=MAX_WORKER_TIMEOUT_SECONDS + 30
        )
        if (
            process.returncode != 0
            or len(output) > _BOUND_HELPER_OUTPUT_MAX_BYTES
        ):
            raise ValueError("descriptor worker helper failed")
        response = json.loads(output.decode("ascii"))
        if not isinstance(response, dict) or set(response) != {
            "cli_version",
            "elapsed_seconds",
            "failure_classification",
            "returncode",
            "success",
            "terminal_reason",
        }:
            raise ValueError("descriptor worker helper result is malformed")
        candidate = WorkerResult(
            success=response["success"],
            terminal_reason=response["terminal_reason"],
            failure_classification=response["failure_classification"],
            returncode=response["returncode"],
            elapsed_seconds=response["elapsed_seconds"],
            cli_version=response["cli_version"],
        )
        metadata = _worker_metadata(candidate)
        if not isinstance(response["success"], bool):
            raise ValueError("descriptor worker helper result is malformed")
        return WorkerResult(
            success=response["success"],
            terminal_reason=metadata.terminal_reason or "runtime_error",
            failure_classification=metadata.failure_classification,
            returncode=metadata.returncode,
            elapsed_seconds=metadata.elapsed_seconds,
            cli_version=metadata.cli_version,
        )
    except Exception:
        if process is not None and process.poll() is None:
            _terminate_git(process)
        return WorkerResult(
            success=False,
            terminal_reason="launch_failed",
            failure_classification=SPAWN_ERROR,
        )


def _open_owner_directory_tree(path: Path) -> int:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            if part in {".", ".."}:
                raise _LaunchReceiptError("launch receipt path is unsafe")
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        details = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o077
        ):
            raise _LaunchReceiptError("launch receipt directory is unsafe")
        os.fchmod(descriptor, 0o700)
        result = descriptor
        descriptor = -1
        return result
    except _LaunchReceiptError:
        raise
    except OSError as exc:
        raise _LaunchReceiptError("launch receipt directory is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _open_directory_no_follow(path: Path) -> int:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            if part in {".", ".."}:
                raise OSError("unsafe directory path")
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        result = descriptor
        descriptor = -1
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _binding_matches(binding: _DirectoryBinding) -> bool:
    descriptor: int | None = None
    try:
        descriptor = _open_directory_no_follow(binding.path)
        details = os.fstat(descriptor)
        held = os.fstat(binding.descriptor)
        return (
            stat.S_ISDIR(details.st_mode)
            and details.st_uid == os.getuid()
            and (details.st_dev, details.st_ino)
            == (binding.device, binding.inode)
            == (held.st_dev, held.st_ino)
        )
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _bound_directory(path: Path) -> Iterator[_DirectoryBinding]:
    lexical = path.absolute()
    descriptor = _open_directory_no_follow(lexical)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid():
            raise OSError("unsafe workspace directory")
        binding = _DirectoryBinding(
            lexical, details.st_dev, details.st_ino, descriptor
        )
        if not _binding_matches(binding):
            raise OSError("workspace binding changed")
        yield binding
    finally:
        os.close(descriptor)


def _receipt_identity(
    *,
    task_id: str,
    evidence: _ReceiptEvidence,
    branch: str,
    allowed_paths: tuple[str, ...],
    workspace: _DirectoryBinding,
) -> str:
    workspace_token = hashlib.sha256(
        os.fsencode(str(workspace.path))
    ).hexdigest()
    payload = {
        "allowed_paths": list(allowed_paths),
        "branch": branch,
        "claim": evidence.claimed_at,
        "reservation_expires": evidence.expires_at,
        "reservation_started": evidence.reserved_at,
        "task_id": task_id,
        "workspace": workspace_token,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest() + ".receipt"


def _receipt_bytes(state: str, evidence: _ReceiptEvidence) -> bytes:
    return json.dumps(
        {
            "expires_epoch_microseconds": evidence.expires_epoch_microseconds,
            "state": state,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _read_receipt_expiry(directory: int, name: str) -> int:
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, dir_fd=directory)
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_nlink != 1
            or stat.S_IMODE(details.st_mode) & 0o077
            or details.st_size > _MAX_RECEIPT_BYTES
        ):
            raise _LaunchReceiptError("launch receipt is unsafe")
        content = os.read(descriptor, _MAX_RECEIPT_BYTES + 1)
        record = json.loads(content.decode("ascii"))
        if (
            not isinstance(record, dict)
            or set(record) != {"expires_epoch_microseconds", "state"}
            or not isinstance(record["expires_epoch_microseconds"], int)
            or isinstance(record["expires_epoch_microseconds"], bool)
            or record["state"] not in {"ACTIVE", "CONSUMED"}
        ):
            raise _LaunchReceiptError("launch receipt is malformed")
        return record["expires_epoch_microseconds"]
    except _LaunchReceiptError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _LaunchReceiptError("launch receipt cannot be read") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _compact_expired_receipts(directory: int, now_epoch_microseconds: int) -> int:
    entries = os.listdir(directory)
    if len(entries) > _MAX_RECEIPT_SCAN:
        raise _LaunchReceiptError("launch receipt scan bound exceeded")
    retained = 0
    removed = False
    for name in entries:
        if not isinstance(name, str) or not _RECEIPT_NAME.fullmatch(name):
            raise _LaunchReceiptError("launch receipt directory is malformed")
        if _read_receipt_expiry(directory, name) <= now_epoch_microseconds:
            try:
                os.unlink(name, dir_fd=directory)
            except OSError as exc:
                raise _LaunchReceiptError(
                    "expired launch receipt cannot be compacted"
                ) from exc
            removed = True
        else:
            retained += 1
    if removed:
        os.fsync(directory)
    return retained


def _state_root_is_separate(state_root: Path, *repositories: Path) -> bool:
    if any(part in {".", ".."} for part in state_root.parts):
        return False
    candidate = Path(os.path.abspath(os.fspath(state_root)))
    for repository in repositories:
        if any(part in {".", ".."} for part in repository.parts):
            return False
        root = Path(os.path.abspath(os.fspath(repository)))
        if (
            candidate == root
            or root in candidate.parents
            or candidate in root.parents
        ):
            return False
    return True


@contextmanager
def _launch_receipt(
    *,
    task_id: str,
    evidence: _ReceiptEvidence,
    branch: str,
    allowed_paths: tuple[str, ...],
    workspace: _DirectoryBinding,
    state_root: Path,
    controller_repository: Path,
    now_epoch_microseconds: int,
) -> Iterator[None]:
    if not _state_root_is_separate(
        state_root, controller_repository, workspace.path
    ):
        raise _LaunchReceiptError("launch receipt state overlaps a repository")
    directory = _open_owner_directory_tree(state_root)
    receipt: int | None = None
    try:
        if (
            _compact_expired_receipts(directory, now_epoch_microseconds)
            >= _MAX_RECEIPTS
        ):
            raise _LaunchReceiptError("launch receipt capacity reached")
        name = _receipt_identity(
            task_id=task_id,
            evidence=evidence,
            branch=branch,
            allowed_paths=allowed_paths,
            workspace=workspace,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            receipt = os.open(name, flags, 0o600, dir_fd=directory)
        except FileExistsError as exc:
            raise _LaunchAlreadyConsumed(
                "launch evidence was already consumed"
            ) from exc
        details = os.fstat(receipt)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_nlink != 1
            or stat.S_IMODE(details.st_mode) & 0o077
        ):
            raise _LaunchReceiptError("launch receipt is unsafe")
        os.write(receipt, _receipt_bytes("ACTIVE", evidence))
        os.fsync(receipt)
        os.fsync(directory)
        yield
    finally:
        if receipt is not None:
            try:
                os.lseek(receipt, 0, os.SEEK_SET)
                os.ftruncate(receipt, 0)
                os.write(receipt, _receipt_bytes("CONSUMED", evidence))
                os.fsync(receipt)
            finally:
                os.close(receipt)
        os.close(directory)


def _terminate_git(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=0.2)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        pass


def _git_bytes(binding: _DirectoryBinding, *arguments: str) -> bytes:
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
            cwd=binding.path,
            env=_GIT_ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if process.stdout is None:
            raise OSError("Git output is unavailable")
        if not _binding_matches(binding):
            raise OSError("Git workspace binding changed")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + _GIT_TIMEOUT_SECONDS
        stream_open = True
        while stream_open or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OSError("Git inspection timed out")
            for key, _ in selector.select(timeout=min(0.1, remaining)):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    stream_open = False
                    continue
                output.extend(chunk)
                if len(output) > _GIT_OUTPUT_MAX_BYTES:
                    raise OSError("Git inspection output exceeded its bound")
        if process.wait(timeout=0.2) != 0:
            raise OSError("Git inspection failed")
        if not _binding_matches(binding):
            raise OSError("Git workspace binding changed")
        return bytes(output)
    except (OSError, subprocess.SubprocessError):
        if process is not None:
            _terminate_git(process)
        raise
    finally:
        if selector is not None:
            selector.close()
        if process is not None and process.stdout is not None:
            process.stdout.close()


def _decode_identity(value: bytes) -> str:
    decoded = value.decode("utf-8", "strict").strip()
    if not decoded or "\x00" in decoded or "\n" in decoded or "\r" in decoded:
        raise ValueError("Git identity is malformed")
    return decoded


def _status_evidence(raw: bytes) -> tuple[tuple[str, ...], bool]:
    entries = raw.split(b"\0")
    if entries and entries[-1] == b"":
        entries.pop()
    paths: list[str] = []
    staged_or_ambiguous = False
    index = 0
    while index < len(entries):
        entry = entries[index]
        if len(entry) < 4 or entry[2:3] != b" ":
            raise ValueError("Git status entry is malformed")
        try:
            code = entry[:2].decode("ascii", "strict")
            path = entry[3:].decode("utf-8", "strict")
        except UnicodeError as exc:
            raise ValueError("Git status entry is malformed") from exc
        if not path or "\x00" in path or "\n" in path or "\r" in path:
            raise ValueError("Git status path is malformed")
        if code != "??" and code[0] != " ":
            staged_or_ambiguous = True
        paths.append(path)
        if "R" in code or "C" in code:
            index += 1
            if index >= len(entries):
                raise ValueError("Git rename evidence is incomplete")
            try:
                entries[index].decode("utf-8", "strict")
            except UnicodeError as exc:
                raise ValueError("Git rename evidence is malformed") from exc
            staged_or_ambiguous = True
        index += 1
    if len(paths) != len(set(paths)):
        raise ValueError("Git status contains duplicate paths")
    return tuple(sorted(paths)), staged_or_ambiguous


def _safe_git_snapshot(binding: _DirectoryBinding) -> _GitSnapshot:
    lexical = binding.path
    if not _binding_matches(binding):
        raise ValueError("Git worktree identity changed")
    root = Path(
        _decode_identity(_git_bytes(binding, "rev-parse", "--show-toplevel"))
    ).absolute()
    if root != lexical:
        raise ValueError("Git worktree identity changed")
    branch = _decode_identity(
        _git_bytes(binding, "symbolic-ref", "--quiet", "--short", "HEAD")
    )
    head = _decode_identity(_git_bytes(binding, "rev-parse", "--verify", "HEAD"))
    status = _git_bytes(
        binding,
        "-c",
        "status.showUntrackedFiles=all",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    changed_paths, staged = _status_evidence(status)
    final_branch = _decode_identity(
        _git_bytes(binding, "symbolic-ref", "--quiet", "--short", "HEAD")
    )
    final_head = _decode_identity(
        _git_bytes(binding, "rev-parse", "--verify", "HEAD")
    )
    if (branch, head) != (final_branch, final_head) or not _binding_matches(binding):
        raise ValueError("Git identity changed during inspection")
    return _GitSnapshot(root, branch, head, changed_paths, staged)


class PersistentKimiSwarmLaunchService:
    """Consume existing controller proofs and run one registered worker adapter."""

    def __init__(
        self,
        controller_repository: Path,
        worker_workspace: Path,
    ) -> None:
        self._controller_repository = Path(controller_repository)
        self._worker_workspace = Path(worker_workspace)
        self._worker_runner = _default_worker_runner
        self._clock = lambda: datetime.now(timezone.utc)
        self._state_root = _default_state_root()

    @classmethod
    def _for_testing(
        cls,
        controller_repository: Path,
        worker_workspace: Path,
        *,
        worker_runner: WorkerRunner,
        clock: Clock,
        state_root: Path | None = None,
    ) -> "PersistentKimiSwarmLaunchService":
        instance = cls(controller_repository, worker_workspace)
        instance._worker_runner = worker_runner
        instance._clock = clock
        instance._state_root = Path(
            state_root or Path(controller_repository).parent / "controller-test-state"
        )
        return instance

    @staticmethod
    def _preflight_failure(
        reason: PersistentKimiLaunchReason | SwarmEligibilityReason,
        scope_count: int = 0,
    ) -> PersistentKimiLaunchResult:
        return PersistentKimiLaunchResult(
            False,
            PersistentKimiLaunchStatus.PREFLIGHT_FAILED,
            reason,
            scope_count=scope_count,
        )

    @staticmethod
    def _postcheck_failure(
        reason: PersistentKimiLaunchReason,
        worker: WorkerResult | None,
        changed_paths: tuple[str, ...] = (),
        scope_count: int = 0,
    ) -> PersistentKimiLaunchResult:
        metadata = _worker_metadata(worker)
        return PersistentKimiLaunchResult(
            False,
            PersistentKimiLaunchStatus.POSTCHECK_FAILED,
            reason,
            changed_paths=changed_paths,
            scope_count=scope_count,
            worker_terminal_reason=metadata.terminal_reason,
            worker_failure_classification=metadata.failure_classification,
            worker_returncode=metadata.returncode,
            worker_elapsed_seconds=metadata.elapsed_seconds,
            worker_cli_version=metadata.cli_version,
        )

    def _workspace(self) -> PersistentWorkspaceReadiness:
        return inspect_persistent_kimi_workspace(
            self._controller_repository, self._worker_workspace
        )

    def _manifest_verified(
        self, task_id: str, allowed_paths: tuple[str, ...]
    ) -> bool:
        try:
            return verify_kimi_scope_manifest(
                self._worker_workspace, task_id, allowed_paths
            )
        except (KimiScopeManifestError, OSError, ValueError, TypeError):
            return False

    def _eligibility(
        self,
        *,
        task_id: str,
        work_kind: SwarmWorkKind,
        allowed_paths: tuple[str, ...],
        queue_record: TaskQueueRecord,
        reservation: ScopeReservation,
        workspace: PersistentWorkspaceReadiness,
        now: datetime,
    ):
        verification = ManifestVerificationEvidence(
            task_id=task_id,
            allowed_paths=allowed_paths,
            workspace_branch=workspace.branch or "",
            verified_at=now,
            verification_id=secrets.token_urlsafe(18),
        )
        return evaluate_kimi_swarm_eligibility(
            task_id=task_id,
            work_kind=work_kind,
            allowed_paths=allowed_paths,
            queue_record=queue_record,
            reservation=reservation,
            workspace=workspace,
            manifest_verification=verification,
            now=now,
        )

    def _run_bound(
        self,
        *,
        binding: _DirectoryBinding,
        task_id: str,
        task_path: str,
        paths: tuple[str, ...],
        receipt_evidence: _ReceiptEvidence,
        now_epoch_microseconds: int,
        branch: str,
        scope_count: int,
    ) -> PersistentKimiLaunchResult:
        try:
            pre_git = _safe_git_snapshot(binding)
        except Exception:
            return self._preflight_failure(
                PersistentKimiLaunchReason.GIT_STATE_UNAVAILABLE, scope_count
            )
        if pre_git.root != binding.path or pre_git.branch != branch:
            return self._preflight_failure(
                PersistentKimiLaunchReason.EVIDENCE_MISMATCH, scope_count
            )
        if pre_git.changed_paths or pre_git.staged_or_ambiguous:
            return self._preflight_failure(
                PersistentKimiLaunchReason.WORKSPACE_NOT_READY, scope_count
            )

        try:
            receipt_context = _launch_receipt(
                task_id=task_id,
                evidence=receipt_evidence,
                branch=branch,
                allowed_paths=paths,
                workspace=binding,
                state_root=self._state_root,
                controller_repository=self._controller_repository,
                now_epoch_microseconds=now_epoch_microseconds,
            )
            with receipt_context:
                launch_git = _safe_git_snapshot(binding)
                if launch_git != pre_git or not self._manifest_verified(task_id, paths):
                    return self._preflight_failure(
                        PersistentKimiLaunchReason.EVIDENCE_MISMATCH, scope_count
                    )

                instruction = build_kimi_swarm_instruction(task_path, list(paths))
                worker: WorkerResult | None = None
                worker_exception = False
                try:
                    if self._worker_runner is _default_worker_runner:
                        worker = _run_descriptor_bound_worker(
                            instruction, binding, paths
                        )
                    else:
                        if not _binding_matches(binding):
                            raise OSError("workspace binding changed before test seam")
                        worker = self._worker_runner(
                            instruction, binding.path, paths
                        )
                except Exception:
                    worker_exception = True
                if worker is not None and not isinstance(worker, WorkerResult):
                    worker = None
                    worker_exception = True

                try:
                    post_git = _safe_git_snapshot(binding)
                except Exception:
                    return self._postcheck_failure(
                        PersistentKimiLaunchReason.GIT_STATE_UNAVAILABLE,
                        worker,
                        scope_count=scope_count,
                    )
                changed_paths = post_git.changed_paths
                if (
                    post_git.root != pre_git.root
                    or post_git.branch != pre_git.branch
                    or post_git.head != pre_git.head
                ):
                    return self._postcheck_failure(
                        PersistentKimiLaunchReason.BRANCH_OR_HEAD_CHANGED,
                        worker,
                        changed_paths,
                        scope_count,
                    )
                if post_git.staged_or_ambiguous:
                    return self._postcheck_failure(
                        PersistentKimiLaunchReason.STAGED_OR_AMBIGUOUS_CHANGES,
                        worker,
                        changed_paths,
                        scope_count,
                    )
                scope = build_scope_result(list(paths), list(changed_paths))
                if not scope.ok:
                    return self._postcheck_failure(
                        PersistentKimiLaunchReason.OUT_OF_SCOPE_CHANGES,
                        worker,
                        changed_paths,
                        scope_count,
                    )
                if not self._manifest_verified(task_id, paths):
                    return self._postcheck_failure(
                        PersistentKimiLaunchReason.MANIFEST_CHANGED,
                        worker,
                        changed_paths,
                        scope_count,
                    )
                if worker_exception:
                    return PersistentKimiLaunchResult(
                        False,
                        PersistentKimiLaunchStatus.WORKER_FAILED,
                        PersistentKimiLaunchReason.WORKER_EXCEPTION,
                        changed_paths,
                        scope_count,
                    )
                if worker is None or not worker.success:
                    metadata = _worker_metadata(worker)
                    return PersistentKimiLaunchResult(
                        False,
                        PersistentKimiLaunchStatus.WORKER_FAILED,
                        PersistentKimiLaunchReason.WORKER_FAILED,
                        changed_paths,
                        scope_count,
                        worker_terminal_reason=metadata.terminal_reason,
                        worker_failure_classification=metadata.failure_classification,
                        worker_returncode=metadata.returncode,
                        worker_elapsed_seconds=metadata.elapsed_seconds,
                        worker_cli_version=metadata.cli_version,
                    )
                metadata = _worker_metadata(worker)
                return PersistentKimiLaunchResult(
                    True,
                    PersistentKimiLaunchStatus.COMPLETED,
                    PersistentKimiLaunchReason.COMPLETED,
                    changed_paths,
                    scope_count,
                    worker_terminal_reason=metadata.terminal_reason,
                    worker_returncode=metadata.returncode,
                    worker_elapsed_seconds=metadata.elapsed_seconds,
                    worker_cli_version=metadata.cli_version,
                )
        except _LaunchAlreadyConsumed:
            return self._preflight_failure(
                PersistentKimiLaunchReason.LAUNCH_ALREADY_CONSUMED, scope_count
            )
        except (OSError, _LaunchReceiptError):
            return self._preflight_failure(
                PersistentKimiLaunchReason.EVIDENCE_MISMATCH, scope_count
            )

    def launch(
        self,
        *,
        task_id: str,
        task_path: str,
        work_kind: SwarmWorkKind,
        allowed_paths: list[str] | tuple[str, ...],
        queue_record: TaskQueueRecord,
        reservation: ScopeReservation,
    ) -> PersistentKimiLaunchResult:
        """Run one Kimi Swarm task; never claim, fall back or publish."""
        try:
            paths = build_kimi_scope_manifest(
                task_id, allowed_paths
            ).allowed_paths
        except KimiScopeManifestError:
            return self._preflight_failure(SwarmEligibilityReason.SCOPE_INVALID)
        if (
            not isinstance(queue_record, TaskQueueRecord)
            or not isinstance(reservation, ScopeReservation)
            or not isinstance(task_path, str)
            or task_path != queue_record.task_path
        ):
            return self._preflight_failure(
                PersistentKimiLaunchReason.EVIDENCE_MISMATCH, len(paths)
            )
        receipt_evidence = _receipt_evidence(queue_record, reservation)
        first_now = _plain_utc(self._clock())
        if receipt_evidence is None or first_now is None:
            return self._preflight_failure(
                SwarmEligibilityReason.TIME_INVALID, len(paths)
            )
        workspace = self._workspace()
        if (
            not workspace.eligible
            or workspace.reason != WorkspaceReadinessReason.READY
            or workspace.branch is None
        ):
            return self._preflight_failure(
                PersistentKimiLaunchReason.WORKSPACE_NOT_READY
            )
        if not self._manifest_verified(task_id, paths):
            return self._preflight_failure(
                PersistentKimiLaunchReason.MANIFEST_NOT_VERIFIED, len(paths)
            )

        eligibility = self._eligibility(
            task_id=task_id,
            work_kind=work_kind,
            allowed_paths=paths,
            queue_record=queue_record,
            reservation=reservation,
            workspace=workspace,
            now=first_now,
        )
        if not eligibility.eligible:
            return self._preflight_failure(
                eligibility.reason, eligibility.scope_count
            )

        final_workspace = self._workspace()
        if final_workspace != workspace or not self._manifest_verified(task_id, paths):
            return self._preflight_failure(
                PersistentKimiLaunchReason.EVIDENCE_MISMATCH,
                eligibility.scope_count,
            )
        final_now = _plain_utc(self._clock())
        if final_now is None:
            return self._preflight_failure(
                SwarmEligibilityReason.TIME_INVALID, eligibility.scope_count
            )
        final_eligibility = self._eligibility(
            task_id=task_id,
            work_kind=work_kind,
            allowed_paths=paths,
            queue_record=queue_record,
            reservation=reservation,
            workspace=final_workspace,
            now=final_now,
        )
        if not final_eligibility.eligible:
            return self._preflight_failure(
                final_eligibility.reason, final_eligibility.scope_count
            )

        try:
            with _bound_directory(self._worker_workspace) as binding:
                return self._run_bound(
                    binding=binding,
                    task_id=task_id,
                    task_path=task_path,
                    paths=paths,
                    receipt_evidence=receipt_evidence,
                    now_epoch_microseconds=_epoch_microseconds(final_now),
                    branch=final_workspace.branch or "",
                    scope_count=final_eligibility.scope_count,
                )
        except OSError:
            return self._preflight_failure(
                PersistentKimiLaunchReason.EVIDENCE_MISMATCH,
                final_eligibility.scope_count,
            )
