"""Bounded controller-owned timeline for governed worker attempts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat


_WORKERS = frozenset({"kimi", "kimi-swarm", "gemini", "codex"})
_TASK_ID = re.compile(r"^TASK-[0-9]{3}$")
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_TERMINAL_REASONS = frozenset(
    {
        "authority_blocked",
        "cancelled",
        "completed",
        "credential_access_required",
        "launch_failed",
        "quota_or_capacity",
        "runtime_error",
        "timeout",
    }
)
_FAILURE_CLASSIFICATIONS = frozenset(
    {"EXECUTABLE_NOT_FOUND", "RUNTIME_ERROR", "SPAWN_ERROR", "UNAVAILABLE"}
)
_EXECUTABLE_RESOLUTIONS = frozenset(
    {"configured_override", "owner_home_fallback", "system_path", "unavailable"}
)
_RUNTIME_PATH_PROFILES = frozenset(
    {"codex_minimal", "controller_default", "gemini_minimal", "kimi_minimal"}
)
_MAX_BYTES = 512 * 1024
_MAX_RECORDS = 500
_RETENTION = timedelta(days=7)
_FUTURE_SKEW = timedelta(minutes=5)


class WorkerOperationsError(RuntimeError):
    """Raised when worker-operation state cannot be handled safely."""


@dataclass(frozen=True)
class WorkerOperationEvent:
    occurred_at: datetime
    task_id: str
    worker: str
    success: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None
    returncode: int | None = None
    terminal_reason: str | None = None
    failure_classification: str | None = None
    executable_resolution: str | None = None
    runtime_path_profile: str | None = None


def default_worker_operations_path(repo_root: Path) -> Path:
    """Return state outside the supplied worker repository."""
    root = Path(repo_root).resolve(strict=True)
    return root.parent / ".advancore-controller" / "worker-operations.jsonl"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise WorkerOperationsError("worker timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            details = os.lstat(current)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(details.st_mode):
            return True
    return False


def _open_verified_owner_directory(path: Path, *, create: bool) -> int:
    """Open *path* component-by-component without following any symlink."""
    absolute = path.absolute()
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, directory_flags)
    try:
        for part in absolute.parts[1:]:
            try:
                child = os.open(part, directory_flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(part, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        details = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or (not create and stat.S_IMODE(details.st_mode) & 0o077)
        ):
            raise WorkerOperationsError("worker timeline parent directory is unsafe")
        if create:
            os.fchmod(descriptor, 0o700)
        result = descriptor
        descriptor = -1
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class WorkerOperationsService:
    """Persist safe worker facts without prompts, output or environment data."""

    def __init__(self, repo_root: Path, state_path: Path | None = None):
        self.repo_root = Path(repo_root).resolve(strict=True)
        proposed = Path(state_path or default_worker_operations_path(self.repo_root))
        if not proposed.is_absolute():
            proposed = Path.cwd() / proposed
        if _has_symlink_component(proposed):
            raise WorkerOperationsError("worker timeline path is unsafe")
        self.path = proposed.resolve()
        if self.path == self.repo_root or self.repo_root in self.path.parents:
            raise WorkerOperationsError("worker timeline must be outside the workspace")

    def _validate(self, event: WorkerOperationEvent, now: datetime) -> WorkerOperationEvent:
        occurred = _utc(event.occurred_at)
        if not now - _RETENTION <= occurred <= now + _FUTURE_SKEW:
            raise WorkerOperationsError("worker event timestamp is outside the safe window")
        if not _TASK_ID.fullmatch(event.task_id) or event.worker not in _WORKERS:
            raise WorkerOperationsError("worker event identity is invalid")
        if not isinstance(event.success, bool):
            raise WorkerOperationsError("worker event success is invalid")
        classified_values = (
            (event.terminal_reason, _TERMINAL_REASONS),
            (event.failure_classification, _FAILURE_CLASSIFICATIONS),
            (event.executable_resolution, _EXECUTABLE_RESOLUTIONS),
            (event.runtime_path_profile, _RUNTIME_PATH_PROFILES),
        )
        for value, allowed in classified_values:
            if value is not None and (
                not isinstance(value, str)
                or not _SAFE_VALUE.fullmatch(value)
                or value not in allowed
            ):
                raise WorkerOperationsError("worker event metadata is invalid")
        if event.returncode is not None and (
            isinstance(event.returncode, bool)
            or not isinstance(event.returncode, int)
            or not -255 <= event.returncode <= 255
        ):
            raise WorkerOperationsError("worker return code is invalid")
        if event.elapsed_seconds is not None and (
            isinstance(event.elapsed_seconds, bool)
            or not isinstance(event.elapsed_seconds, (int, float))
            or not 0 <= event.elapsed_seconds <= 7200
        ):
            raise WorkerOperationsError("worker elapsed duration is invalid")
        started = _utc(event.started_at) if event.started_at else None
        finished = _utc(event.finished_at) if event.finished_at else None
        for timestamp in (started, finished):
            if timestamp is not None and not (
                now - _RETENTION <= timestamp <= now + _FUTURE_SKEW
            ):
                raise WorkerOperationsError(
                    "worker timing timestamp is outside the safe window"
                )
        if started and finished and finished < started:
            raise WorkerOperationsError("worker timing order is invalid")
        if started and started > occurred:
            raise WorkerOperationsError("worker start is after event occurrence")
        if finished and finished > occurred:
            raise WorkerOperationsError("worker finish is after event occurrence")
        return WorkerOperationEvent(
            occurred,
            event.task_id,
            event.worker,
            event.success,
            started,
            finished,
            float(event.elapsed_seconds) if event.elapsed_seconds is not None else None,
            event.returncode,
            event.terminal_reason,
            event.failure_classification,
            event.executable_resolution,
            event.runtime_path_profile,
        )

    @staticmethod
    def _payload(event: WorkerOperationEvent) -> dict[str, object]:
        payload = asdict(event)
        for name in ("occurred_at", "started_at", "finished_at"):
            value = payload[name]
            payload[name] = value.isoformat() if isinstance(value, datetime) else None
        return payload

    @classmethod
    def _sort_key(cls, event: WorkerOperationEvent) -> tuple[datetime, str]:
        """Order chronologically with a deterministic bounded-record tie-break."""
        return (
            event.occurred_at,
            json.dumps(cls._payload(event), separators=(",", ":"), sort_keys=True),
        )

    def _load(
        self, now: datetime, *, parent_descriptor: int | None = None
    ) -> list[WorkerOperationEvent]:
        descriptor: int | None = None
        try:
            if parent_descriptor is None:
                if not self.path.exists():
                    return []
                descriptor = os.open(
                    self.path,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
            else:
                descriptor = os.open(
                    self.path.name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_descriptor,
                )
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) & 0o077
                or details.st_nlink != 1
                or details.st_size > _MAX_BYTES
            ):
                raise WorkerOperationsError("worker timeline file is unsafe")
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                descriptor = None
                lines = handle.read().splitlines()
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError) as exc:
            raise WorkerOperationsError("worker timeline cannot be read") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        events: list[WorkerOperationEvent] = []
        for line in lines[-_MAX_RECORDS * 2 :]:
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    continue
                event = WorkerOperationEvent(
                    occurred_at=datetime.fromisoformat(str(raw["occurred_at"])),
                    task_id=raw["task_id"],
                    worker=raw["worker"],
                    success=raw["success"],
                    started_at=datetime.fromisoformat(raw["started_at"])
                    if raw.get("started_at") else None,
                    finished_at=datetime.fromisoformat(raw["finished_at"])
                    if raw.get("finished_at") else None,
                    elapsed_seconds=raw.get("elapsed_seconds"),
                    returncode=raw.get("returncode"),
                    terminal_reason=raw.get("terminal_reason"),
                    failure_classification=raw.get("failure_classification"),
                    executable_resolution=raw.get("executable_resolution"),
                    runtime_path_profile=raw.get("runtime_path_profile"),
                )
                events.append(self._validate(event, now))
            except (
                KeyError,
                RecursionError,
                TypeError,
                ValueError,
                WorkerOperationsError,
            ):
                continue
        events.sort(key=self._sort_key)
        return events[-_MAX_RECORDS:]

    def list_events(self, *, now: datetime | None = None) -> list[WorkerOperationEvent]:
        current = _utc(now or datetime.now(timezone.utc))
        try:
            parent_descriptor = _open_verified_owner_directory(
                self.path.parent, create=False
            )
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise WorkerOperationsError("worker timeline path is unsafe") from exc
        try:
            return self._load(current, parent_descriptor=parent_descriptor)
        finally:
            os.close(parent_descriptor)

    @contextmanager
    def _exclusive_lock(self):
        """Serialize the complete load/compact/replace transaction."""
        lock_path = self.path.with_name(self.path.name + ".lock")
        descriptor: int | None = None
        parent_descriptor: int | None = None
        try:
            parent_descriptor = _open_verified_owner_directory(
                self.path.parent, create=True
            )
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            for attempt in range(3):
                try:
                    descriptor = os.open(
                        lock_path.name, flags, 0o600, dir_fd=parent_descriptor
                    )
                    break
                except FileNotFoundError:
                    if attempt == 2:
                        raise
            if descriptor is None:  # pragma: no cover - defensive
                raise WorkerOperationsError("worker timeline lock file is unavailable")
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) & 0o077
                or details.st_nlink != 1
            ):
                raise WorkerOperationsError("worker timeline lock file is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield parent_descriptor
        except OSError as exc:
            raise WorkerOperationsError("worker timeline lock failed") from exc
        finally:
            if descriptor is not None:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(descriptor)
            if parent_descriptor is not None:
                os.close(parent_descriptor)

    def record(
        self, event: WorkerOperationEvent, *, now: datetime | None = None
    ) -> WorkerOperationEvent:
        current = _utc(now or datetime.now(timezone.utc))
        validated = self._validate(event, current)
        with self._exclusive_lock() as parent_descriptor:
            events = self._load(current, parent_descriptor=parent_descriptor)
            events.append(validated)
            events.sort(key=self._sort_key)
            events = events[-_MAX_RECORDS:]
            temporary_name = (
                f".{self.path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
            )
            temporary_descriptor: int | None = None
            try:
                temporary_flags = (
                    os.O_CREAT
                    | os.O_EXCL
                    | os.O_WRONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                temporary_descriptor = os.open(
                    temporary_name,
                    temporary_flags,
                    0o600,
                    dir_fd=parent_descriptor,
                )
                os.fchmod(temporary_descriptor, 0o600)
                with os.fdopen(
                    temporary_descriptor, "w", encoding="utf-8"
                ) as handle:
                    temporary_descriptor = None
                    for item in events:
                        handle.write(
                            json.dumps(self._payload(item), sort_keys=True) + "\n"
                        )
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(
                    temporary_name,
                    self.path.name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
                os.fsync(parent_descriptor)
            except OSError as exc:
                try:
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
                raise WorkerOperationsError(
                    "worker timeline cannot be written"
                ) from exc
            finally:
                if temporary_descriptor is not None:
                    os.close(temporary_descriptor)
        return validated
