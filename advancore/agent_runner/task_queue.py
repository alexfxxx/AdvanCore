"""Controller-owned metadata queue for already approved governed tasks.

The queue deliberately has no execution or publication capability. It records
only which approved task a controller may consider next.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
from typing import Iterator


_TASK_ID = re.compile(r"^TASK-[0-9]{3}$")
_TASK_PATH = re.compile(r"^tasks/(TASK-[0-9]{3})-[A-Za-z0-9_.-]+\.md$")
_TASK_STATUS = re.compile(r"^STATUS:\s*(\w+)\s*$", re.IGNORECASE)
_TASK_TITLE = re.compile(r"^#\s+(TASK-[0-9]{3})\s*[—–-]\s+.+$", re.IGNORECASE)
_WORKERS = frozenset({"kimi", "kimi-swarm", "gemini", "codex"})
_EXECUTABLE_TASK_STATUSES = frozenset({"READY", "REWORK"})
_MAX_BYTES = 512 * 1024
_MAX_TASK_BYTES = 256 * 1024
_MAX_RECORDS = 256
_FUTURE_SKEW = timedelta(minutes=5)
_STALE_CLAIM = timedelta(hours=2)


class TaskQueueError(RuntimeError):
    """Raised when queue state or a requested transition is unsafe."""


class TaskQueueStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class TaskQueueRecord:
    task_id: str
    task_path: str
    worker: str
    status: TaskQueueStatus
    enqueued_at: datetime
    claimed_at: datetime | None = None
    finished_at: datetime | None = None


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TaskQueueError("queue timestamps must be timezone-aware")
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


def _open_directory_no_follow(path: Path) -> int:
    """Bind an existing directory without following any path-component link."""
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        details = os.fstat(descriptor)
        if not stat.S_ISDIR(details.st_mode):
            raise TaskQueueError("queue directory path is unsafe")
        result = descriptor
        descriptor = -1
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _open_verified_owner_directory(path: Path) -> int:
    """Create and bind an owner-only directory tree without following links."""
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
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
        if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid():
            raise TaskQueueError("queue directory owner is unsafe")
        os.fchmod(descriptor, 0o700)
        result = descriptor
        descriptor = -1
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class GovernedTaskQueue:
    """Persist bounded task metadata; never launch or authorize a worker."""

    def __init__(self, repository_root: Path, state_path: Path):
        self.repository_root = Path(repository_root).resolve(strict=True)
        proposed = Path(state_path)
        if not proposed.is_absolute():
            proposed = Path.cwd() / proposed
        proposed = proposed.absolute()
        if _has_symlink_component(proposed):
            raise TaskQueueError("queue path contains a symbolic link")
        self.state_path = proposed
        if (
            self.state_path == self.repository_root
            or self.repository_root in self.state_path.parents
        ):
            raise TaskQueueError("queue state must be outside the repository")
        self.lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[int]:
        parent_descriptor: int | None = None
        descriptor: int | None = None
        try:
            parent_descriptor = _open_verified_owner_directory(
                self.state_path.parent
            )
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(
                self.lock_path.name, flags, 0o600, dir_fd=parent_descriptor
            )
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or details.st_nlink != 1
                or stat.S_IMODE(details.st_mode) & 0o077
            ):
                raise TaskQueueError("queue lock file is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield parent_descriptor
        except TaskQueueError:
            raise
        except OSError as exc:
            raise TaskQueueError("queue lock cannot be opened safely") from exc
        finally:
            if descriptor is not None:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(descriptor)
            if parent_descriptor is not None:
                os.close(parent_descriptor)

    def _validate_record(self, record: TaskQueueRecord, now: datetime) -> TaskQueueRecord:
        match = _TASK_PATH.fullmatch(record.task_path)
        path = PurePosixPath(record.task_path)
        if (
            not _TASK_ID.fullmatch(record.task_id)
            or match is None
            or match.group(1) != record.task_id
            or path.is_absolute()
            or ".." in path.parts
            or record.worker not in _WORKERS
            or not isinstance(record.status, TaskQueueStatus)
        ):
            raise TaskQueueError("queue record identity is invalid")
        enqueued = _utc(record.enqueued_at)
        claimed = _utc(record.claimed_at) if record.claimed_at else None
        finished = _utc(record.finished_at) if record.finished_at else None
        if any(
            value > now + _FUTURE_SKEW
            for value in (enqueued, claimed, finished)
            if value is not None
        ):
            raise TaskQueueError("queue record is future-dated")
        if claimed is not None and claimed < enqueued:
            raise TaskQueueError("claim predates enqueue")
        if finished is not None and finished < (claimed or enqueued):
            raise TaskQueueError("finish predates queue transition")
        expected = {
            TaskQueueStatus.QUEUED: (False, False),
            TaskQueueStatus.RUNNING: (True, False),
            TaskQueueStatus.COMPLETED: (True, True),
            TaskQueueStatus.BLOCKED: (None, True),
        }[record.status]
        claimed_expected, finished_expected = expected
        if claimed_expected is not None and (claimed is not None) != claimed_expected:
            raise TaskQueueError("queue timestamps do not match status")
        if (finished is not None) != finished_expected:
            raise TaskQueueError("queue timestamps do not match status")
        return replace(
            record,
            enqueued_at=enqueued,
            claimed_at=claimed,
            finished_at=finished,
        )

    def _validate_governed_task_file(self, task_id: str, task_path: str) -> None:
        """Require a real, direct, approved task specification before queueing."""
        match = _TASK_PATH.fullmatch(task_path)
        if match is None or match.group(1) != task_id:
            raise TaskQueueError("governed task path is invalid")
        root_descriptor: int | None = None
        tasks_descriptor: int | None = None
        descriptor: int | None = None
        try:
            root_descriptor = _open_directory_no_follow(self.repository_root)
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            directory_flags |= getattr(os, "O_NOFOLLOW", 0)
            tasks_descriptor = os.open(
                "tasks", directory_flags, dir_fd=root_descriptor
            )
            descriptor = os.open(
                PurePosixPath(task_path).name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=tasks_descriptor,
            )
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_nlink != 1
                or details.st_size > _MAX_TASK_BYTES
            ):
                raise TaskQueueError("governed task file is unsafe")
            chunks: list[bytes] = []
            remaining = _MAX_TASK_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            if len(content) > _MAX_TASK_BYTES:
                raise TaskQueueError("governed task file exceeds its size limit")
            text = content.decode("utf-8")
        except TaskQueueError:
            raise
        except (OSError, UnicodeError) as exc:
            raise TaskQueueError("governed task file cannot be opened safely") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if tasks_descriptor is not None:
                os.close(tasks_descriptor)
            if root_descriptor is not None:
                os.close(root_descriptor)

        statuses = [
            match.group(1).upper()
            for line in text.splitlines()
            if (match := _TASK_STATUS.fullmatch(line)) is not None
        ]
        title_ids = [
            match.group(1).upper()
            for line in text.splitlines()
            if (match := _TASK_TITLE.fullmatch(line)) is not None
        ]
        if title_ids != [task_id]:
            raise TaskQueueError("governed task title is missing or mismatched")
        if len(statuses) != 1 or statuses[0] not in _EXECUTABLE_TASK_STATUSES:
            raise TaskQueueError("governed task is not approved for execution")

    def _load_unlocked(
        self, now: datetime, parent_descriptor: int
    ) -> list[TaskQueueRecord]:
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.state_path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or details.st_nlink != 1
                or stat.S_IMODE(details.st_mode) & 0o077
                or details.st_size > _MAX_BYTES
            ):
                raise TaskQueueError("queue state file is unsafe")
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                descriptor = None
                raw = json.load(handle)
        except FileNotFoundError:
            return []
        except TaskQueueError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise TaskQueueError("queue state cannot be read") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if not isinstance(raw, list) or len(raw) > _MAX_RECORDS:
            raise TaskQueueError("queue state is not a bounded list")
        records: list[TaskQueueRecord] = []
        seen: set[str] = set()
        try:
            for item in raw:
                if not isinstance(item, dict) or set(item) != {
                    "task_id",
                    "task_path",
                    "worker",
                    "status",
                    "enqueued_at",
                    "claimed_at",
                    "finished_at",
                }:
                    raise TaskQueueError("queue record shape is invalid")
                record = TaskQueueRecord(
                    task_id=item["task_id"],
                    task_path=item["task_path"],
                    worker=item["worker"],
                    status=TaskQueueStatus(item["status"]),
                    enqueued_at=datetime.fromisoformat(item["enqueued_at"]),
                    claimed_at=(
                        datetime.fromisoformat(item["claimed_at"])
                        if item["claimed_at"]
                        else None
                    ),
                    finished_at=(
                        datetime.fromisoformat(item["finished_at"])
                        if item["finished_at"]
                        else None
                    ),
                )
                record = self._validate_record(record, now)
                if record.task_id in seen:
                    raise TaskQueueError("queue contains a duplicate task")
                seen.add(record.task_id)
                records.append(record)
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskQueueError("queue record is malformed") from exc
        if any(
            later.enqueued_at < earlier.enqueued_at
            for earlier, later in zip(records, records[1:])
        ):
            raise TaskQueueError("queue order is invalid")
        if sum(record.status == TaskQueueStatus.RUNNING for record in records) > 1:
            raise TaskQueueError("queue contains multiple running claims")
        return records

    def _write_unlocked(
        self, records: list[TaskQueueRecord], now: datetime, parent_descriptor: int
    ) -> None:
        if len(records) > _MAX_RECORDS:
            raise TaskQueueError("queue record limit reached")
        payload: list[dict[str, object]] = []
        validated = [self._validate_record(record, now) for record in records]
        if any(
            later.enqueued_at < earlier.enqueued_at
            for earlier, later in zip(validated, validated[1:])
        ):
            raise TaskQueueError("queue order is invalid")
        for record in validated:
            item = asdict(record)
            item["status"] = record.status.value
            for name in ("enqueued_at", "claimed_at", "finished_at"):
                value = item[name]
                item[name] = value.isoformat() if isinstance(value, datetime) else None
            payload.append(item)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        if len(encoded.encode("utf-8")) > _MAX_BYTES:
            raise TaskQueueError("queue state exceeds its size limit")
        temporary_name = (
            f".{self.state_path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        )
        temporary_descriptor: int | None = None
        try:
            temporary_descriptor = os.open(
                temporary_name,
                os.O_CREAT
                | os.O_EXCL
                | os.O_WRONLY
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_descriptor,
            )
            with os.fdopen(temporary_descriptor, "w", encoding="utf-8") as handle:
                temporary_descriptor = None
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(
                temporary_name,
                self.state_path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.fsync(parent_descriptor)
        except OSError as exc:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except OSError:
                pass
            raise TaskQueueError("queue state cannot be written") from exc
        finally:
            if temporary_descriptor is not None:
                os.close(temporary_descriptor)

    def list_records(self, *, now: datetime | None = None) -> list[TaskQueueRecord]:
        current = _utc(now or datetime.now(timezone.utc))
        with self._locked(exclusive=False) as parent_descriptor:
            return self._load_unlocked(current, parent_descriptor)

    def enqueue(
        self,
        task_id: str,
        task_path: str,
        worker: str,
        *,
        now: datetime | None = None,
    ) -> TaskQueueRecord:
        current = _utc(now or datetime.now(timezone.utc))
        record = self._validate_record(
            TaskQueueRecord(
                task_id, task_path, worker, TaskQueueStatus.QUEUED, current
            ),
            current,
        )
        with self._locked(exclusive=True) as parent_descriptor:
            records = self._load_unlocked(current, parent_descriptor)
            self._validate_governed_task_file(task_id, task_path)
            if any(item.task_id == task_id for item in records):
                raise TaskQueueError("task is already present in the queue")
            if len(records) >= _MAX_RECORDS:
                raise TaskQueueError("queue record limit reached")
            if records and current < records[-1].enqueued_at:
                raise TaskQueueError("enqueue timestamp moved backward")
            records.append(record)
            self._write_unlocked(records, current, parent_descriptor)
        return record

    def claim_next(self, *, now: datetime | None = None) -> TaskQueueRecord | None:
        current = _utc(now or datetime.now(timezone.utc))
        with self._locked(exclusive=True) as parent_descriptor:
            records = self._load_unlocked(current, parent_descriptor)
            changed = False
            for index, record in enumerate(records):
                if record.status != TaskQueueStatus.RUNNING:
                    continue
                if record.claimed_at is None:
                    raise TaskQueueError("running queue record lacks claim time")
                if current < record.claimed_at:
                    raise TaskQueueError("claim evaluation time moved backward")
                if current - record.claimed_at >= _STALE_CLAIM:
                    records[index] = self._validate_record(
                        replace(
                            record,
                            status=TaskQueueStatus.BLOCKED,
                            finished_at=current,
                        ),
                        current,
                    )
                    changed = True
                else:
                    return None
            for index, record in enumerate(records):
                if record.status == TaskQueueStatus.QUEUED:
                    if current < record.enqueued_at:
                        raise TaskQueueError("claim predates enqueue")
                    self._validate_governed_task_file(
                        record.task_id, record.task_path
                    )
                    claimed = self._validate_record(
                        replace(
                            record,
                            status=TaskQueueStatus.RUNNING,
                            claimed_at=current,
                        ),
                        current,
                    )
                    records[index] = claimed
                    self._write_unlocked(records, current, parent_descriptor)
                    return claimed
            if changed:
                self._write_unlocked(records, current, parent_descriptor)
            return None

    def _finish(
        self, task_id: str, status: TaskQueueStatus, current: datetime
    ) -> TaskQueueRecord:
        if not _TASK_ID.fullmatch(task_id):
            raise TaskQueueError("task identifier is invalid")
        with self._locked(exclusive=True) as parent_descriptor:
            records = self._load_unlocked(current, parent_descriptor)
            for index, record in enumerate(records):
                if record.task_id != task_id:
                    continue
                allowed = (
                    record.status == TaskQueueStatus.RUNNING
                    if status == TaskQueueStatus.COMPLETED
                    else record.status
                    in {TaskQueueStatus.QUEUED, TaskQueueStatus.RUNNING}
                )
                if not allowed:
                    raise TaskQueueError("requested queue transition is invalid")
                transition_time = record.claimed_at or record.enqueued_at
                if current < transition_time:
                    raise TaskQueueError("finish predates queue transition")
                finished = self._validate_record(
                    replace(record, status=status, finished_at=current), current
                )
                records[index] = finished
                self._write_unlocked(records, current, parent_descriptor)
                return finished
            raise TaskQueueError("task is not present in the queue")

    def complete(
        self, task_id: str, *, now: datetime | None = None
    ) -> TaskQueueRecord:
        return self._finish(
            task_id,
            TaskQueueStatus.COMPLETED,
            _utc(now or datetime.now(timezone.utc)),
        )

    def block(
        self, task_id: str, *, now: datetime | None = None
    ) -> TaskQueueRecord:
        return self._finish(
            task_id,
            TaskQueueStatus.BLOCKED,
            _utc(now or datetime.now(timezone.utc)),
        )
