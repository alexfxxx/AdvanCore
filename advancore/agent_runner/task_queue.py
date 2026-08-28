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
import stat
import tempfile
from typing import Iterator


_TASK_ID = re.compile(r"^TASK-[0-9]{3}$")
_TASK_PATH = re.compile(r"^tasks/(TASK-[0-9]{3})-[A-Za-z0-9_.-]+\.md$")
_WORKERS = frozenset({"kimi", "kimi-swarm", "gemini", "codex"})
_MAX_BYTES = 512 * 1024
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


class GovernedTaskQueue:
    """Persist bounded task metadata; never launch or authorize a worker."""

    def __init__(self, repository_root: Path, state_path: Path):
        self.repository_root = Path(repository_root).resolve(strict=True)
        proposed = Path(state_path)
        if not proposed.is_absolute():
            proposed = Path.cwd() / proposed
        if _has_symlink_component(proposed):
            raise TaskQueueError("queue path contains a symbolic link")
        self.state_path = proposed.resolve()
        if (
            self.state_path == self.repository_root
            or self.repository_root in self.state_path.parents
        ):
            raise TaskQueueError("queue state must be outside the repository")
        self.lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if _has_symlink_component(self.state_path.parent):
                raise TaskQueueError("queue directory became unsafe")
            os.chmod(self.state_path.parent, 0o700)
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.lock_path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
        except TaskQueueError:
            raise
        except OSError as exc:
            raise TaskQueueError("queue lock cannot be opened safely") from exc
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        except OSError as exc:
            raise TaskQueueError("queue lock failed") from exc
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

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

    def _load_unlocked(self, now: datetime) -> list[TaskQueueRecord]:
        if not self.state_path.exists():
            return []
        try:
            details = self.state_path.lstat()
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or details.st_nlink != 1
                or stat.S_IMODE(details.st_mode) & 0o077
                or details.st_size > _MAX_BYTES
            ):
                raise TaskQueueError("queue state file is unsafe")
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except TaskQueueError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TaskQueueError("queue state cannot be read") from exc
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
        if records != sorted(records, key=lambda item: (item.enqueued_at, item.task_id)):
            raise TaskQueueError("queue order is invalid")
        return records

    def _write_unlocked(self, records: list[TaskQueueRecord]) -> None:
        if len(records) > _MAX_RECORDS:
            raise TaskQueueError("queue record limit reached")
        payload: list[dict[str, object]] = []
        for record in records:
            item = asdict(record)
            item["status"] = record.status.value
            for name in ("enqueued_at", "claimed_at", "finished_at"):
                value = item[name]
                item[name] = value.isoformat() if isinstance(value, datetime) else None
            payload.append(item)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        if len(encoded.encode("utf-8")) > _MAX_BYTES:
            raise TaskQueueError("queue state exceeds its size limit")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.state_path.parent, delete=False
            ) as handle:
                temporary = Path(handle.name)
                os.chmod(temporary, 0o600)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
            os.chmod(self.state_path, 0o600)
        except OSError as exc:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            raise TaskQueueError("queue state cannot be written") from exc

    def list_records(self, *, now: datetime | None = None) -> list[TaskQueueRecord]:
        current = _utc(now or datetime.now(timezone.utc))
        with self._locked(exclusive=False):
            return self._load_unlocked(current)

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
        with self._locked(exclusive=True):
            records = self._load_unlocked(current)
            if any(item.task_id == task_id for item in records):
                raise TaskQueueError("task is already present in the queue")
            if len(records) >= _MAX_RECORDS:
                raise TaskQueueError("queue record limit reached")
            records.append(record)
            records.sort(key=lambda item: (item.enqueued_at, item.task_id))
            self._write_unlocked(records)
        return record

    def claim_next(self, *, now: datetime | None = None) -> TaskQueueRecord | None:
        current = _utc(now or datetime.now(timezone.utc))
        with self._locked(exclusive=True):
            records = self._load_unlocked(current)
            changed = False
            for index, record in enumerate(records):
                if record.status != TaskQueueStatus.RUNNING:
                    continue
                if record.claimed_at is None:
                    raise TaskQueueError("running queue record lacks claim time")
                if current - record.claimed_at >= _STALE_CLAIM:
                    records[index] = replace(
                        record,
                        status=TaskQueueStatus.BLOCKED,
                        finished_at=current,
                    )
                    changed = True
                else:
                    return None
            for index, record in enumerate(records):
                if record.status == TaskQueueStatus.QUEUED:
                    claimed = replace(
                        record,
                        status=TaskQueueStatus.RUNNING,
                        claimed_at=current,
                    )
                    records[index] = claimed
                    self._write_unlocked(records)
                    return claimed
            if changed:
                self._write_unlocked(records)
            return None

    def _finish(
        self, task_id: str, status: TaskQueueStatus, current: datetime
    ) -> TaskQueueRecord:
        if not _TASK_ID.fullmatch(task_id):
            raise TaskQueueError("task identifier is invalid")
        with self._locked(exclusive=True):
            records = self._load_unlocked(current)
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
                finished = replace(record, status=status, finished_at=current)
                records[index] = finished
                self._write_unlocked(records)
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
