"""Controller-owned reservations for non-overlapping governed file scopes."""

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
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_.@+/-]{1,200}$")
_WORKERS = frozenset({"kimi", "kimi-swarm", "gemini", "codex"})
_MAX_BYTES = 256 * 1024
_MAX_RECORDS = 128
_MAX_PATHS = 64
_LEASE = timedelta(hours=4)
_RETENTION = timedelta(days=7)
_FUTURE_SKEW = timedelta(minutes=5)


class ScopeReservationError(RuntimeError):
    """Raised when reservation state or a requested operation is unsafe."""


class ReservationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"


@dataclass(frozen=True)
class ScopeReservation:
    task_id: str
    worker: str
    paths: tuple[str, ...]
    status: ReservationStatus
    reserved_at: datetime
    expires_at: datetime
    released_at: datetime | None = None


def default_scope_reservations_path(repository_root: Path) -> Path:
    root = Path(repository_root).resolve(strict=True)
    return root.parent / ".advancore-controller" / "scope-reservations.json"


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ScopeReservationError("reservation timestamps must be timezone-aware")
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


def _validate_scope_path(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_PATH.fullmatch(value):
        raise ScopeReservationError("scope path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value.endswith("/")
        or ".." in path.parts
        or "." in path.parts
        or "//" in value
        or any(character in value for character in "*?[]{}")
    ):
        raise ScopeReservationError("scope path is unsafe")
    return value


def _paths_overlap(left: str, right: str) -> bool:
    left_path = PurePosixPath(left)
    right_path = PurePosixPath(right)
    return (
        left_path == right_path
        or left_path in right_path.parents
        or right_path in left_path.parents
    )


class ScopeReservationService:
    """Reserve file scopes without acquiring any execution authority."""

    def __init__(
        self, repository_root: Path, state_path: Path | None = None
    ) -> None:
        self.repository_root = Path(repository_root).resolve(strict=True)
        proposed = Path(
            state_path or default_scope_reservations_path(self.repository_root)
        )
        if not proposed.is_absolute():
            proposed = Path.cwd() / proposed
        if _has_symlink_component(proposed):
            raise ScopeReservationError("reservation path contains a symbolic link")
        self.state_path = proposed.resolve()
        if (
            self.state_path == self.repository_root
            or self.repository_root in self.state_path.parents
        ):
            raise ScopeReservationError("reservation state must be outside repository")
        self.lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        descriptor: int | None = None
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if _has_symlink_component(self.state_path.parent):
                raise ScopeReservationError("reservation directory became unsafe")
            parent_details = self.state_path.parent.stat()
            if parent_details.st_uid != os.getuid():
                raise ScopeReservationError("reservation directory owner is unsafe")
            os.chmod(self.state_path.parent, 0o700)
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.lock_path, flags, 0o600)
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or details.st_nlink != 1
                or stat.S_IMODE(details.st_mode) & 0o077
            ):
                raise ScopeReservationError("reservation lock is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        except ScopeReservationError:
            raise
        except OSError as exc:
            raise ScopeReservationError("reservation lock failed") from exc
        finally:
            if descriptor is not None:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)

    def _validate(
        self, reservation: ScopeReservation, now: datetime
    ) -> ScopeReservation:
        if (
            not _TASK_ID.fullmatch(reservation.task_id)
            or reservation.worker not in _WORKERS
            or not isinstance(reservation.status, ReservationStatus)
            or not isinstance(reservation.paths, tuple)
            or not 1 <= len(reservation.paths) <= _MAX_PATHS
        ):
            raise ScopeReservationError("reservation identity is invalid")
        paths = tuple(_validate_scope_path(value) for value in reservation.paths)
        if len(set(paths)) != len(paths) or paths != tuple(sorted(paths)):
            raise ScopeReservationError("reservation paths must be unique and sorted")
        reserved = _utc(reservation.reserved_at)
        expires = _utc(reservation.expires_at)
        released = _utc(reservation.released_at) if reservation.released_at else None
        if reserved > now + _FUTURE_SKEW or expires > reserved + _LEASE:
            raise ScopeReservationError("reservation timing is invalid")
        if expires <= reserved or (released is not None and released < reserved):
            raise ScopeReservationError("reservation timing order is invalid")
        if reservation.status == ReservationStatus.ACTIVE and released is not None:
            raise ScopeReservationError("active reservation cannot be released")
        if reservation.status == ReservationStatus.RELEASED and released is None:
            raise ScopeReservationError("released reservation lacks timestamp")
        return replace(
            reservation,
            paths=paths,
            reserved_at=reserved,
            expires_at=expires,
            released_at=released,
        )

    def _load_unlocked(self, now: datetime) -> list[ScopeReservation]:
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
                raise ScopeReservationError("reservation state file is unsafe")
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except ScopeReservationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ScopeReservationError("reservation state cannot be read") from exc
        if not isinstance(raw, list) or len(raw) > _MAX_RECORDS:
            raise ScopeReservationError("reservation state is not a bounded list")
        records: list[ScopeReservation] = []
        try:
            for item in raw:
                if not isinstance(item, dict) or set(item) != {
                    "task_id",
                    "worker",
                    "paths",
                    "status",
                    "reserved_at",
                    "expires_at",
                    "released_at",
                }:
                    raise ScopeReservationError("reservation record shape is invalid")
                record = ScopeReservation(
                    task_id=item["task_id"],
                    worker=item["worker"],
                    paths=tuple(item["paths"]),
                    status=ReservationStatus(item["status"]),
                    reserved_at=datetime.fromisoformat(item["reserved_at"]),
                    expires_at=datetime.fromisoformat(item["expires_at"]),
                    released_at=(
                        datetime.fromisoformat(item["released_at"])
                        if item["released_at"]
                        else None
                    ),
                )
                records.append(self._validate(record, now))
        except (KeyError, TypeError, ValueError) as exc:
            raise ScopeReservationError("reservation record is malformed") from exc
        if records != sorted(records, key=lambda item: item.reserved_at):
            raise ScopeReservationError("reservation state order is invalid")
        active_tasks = [
            record.task_id
            for record in records
            if record.status == ReservationStatus.ACTIVE
        ]
        if len(active_tasks) != len(set(active_tasks)):
            raise ScopeReservationError("duplicate active task reservation")
        return records

    def _write_unlocked(self, records: list[ScopeReservation]) -> None:
        if len(records) > _MAX_RECORDS:
            raise ScopeReservationError("reservation record limit reached")
        payload: list[dict[str, object]] = []
        for record in records:
            item = asdict(record)
            item["paths"] = list(record.paths)
            item["status"] = record.status.value
            for name in ("reserved_at", "expires_at", "released_at"):
                value = item[name]
                item[name] = value.isoformat() if isinstance(value, datetime) else None
            payload.append(item)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        if len(encoded.encode("utf-8")) > _MAX_BYTES:
            raise ScopeReservationError("reservation state exceeds its size limit")
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
            raise ScopeReservationError("reservation state cannot be written") from exc

    @staticmethod
    def _expire_and_compact(
        records: list[ScopeReservation], now: datetime
    ) -> tuple[list[ScopeReservation], bool]:
        changed = False
        retained: list[ScopeReservation] = []
        for record in records:
            if (
                record.status == ReservationStatus.ACTIVE
                and record.expires_at <= now
            ):
                record = replace(
                    record,
                    status=ReservationStatus.RELEASED,
                    released_at=now,
                )
                changed = True
            if (
                record.status == ReservationStatus.RELEASED
                and record.released_at is not None
                and record.released_at < now - _RETENTION
            ):
                changed = True
                continue
            retained.append(record)
        return retained, changed

    def list_reservations(
        self, *, now: datetime | None = None
    ) -> list[ScopeReservation]:
        current = _utc(now or datetime.now(timezone.utc))
        with self._locked():
            records = self._load_unlocked(current)
            records, changed = self._expire_and_compact(records, current)
            if changed:
                self._write_unlocked(records)
            return records

    def reserve(
        self,
        task_id: str,
        worker: str,
        paths: list[str] | tuple[str, ...],
        *,
        now: datetime | None = None,
    ) -> ScopeReservation:
        current = _utc(now or datetime.now(timezone.utc))
        proposed = self._validate(
            ScopeReservation(
                task_id=task_id,
                worker=worker,
                paths=tuple(sorted(paths)),
                status=ReservationStatus.ACTIVE,
                reserved_at=current,
                expires_at=current + _LEASE,
            ),
            current,
        )
        with self._locked():
            records = self._load_unlocked(current)
            records, _ = self._expire_and_compact(records, current)
            for record in records:
                if record.status != ReservationStatus.ACTIVE:
                    continue
                if record.task_id == task_id:
                    raise ScopeReservationError("task already has an active reservation")
                if any(
                    _paths_overlap(left, right)
                    for left in proposed.paths
                    for right in record.paths
                ):
                    raise ScopeReservationError(
                        f"scope overlaps active reservation for {record.task_id}"
                    )
            if len(records) >= _MAX_RECORDS:
                raise ScopeReservationError("reservation record limit reached")
            records.append(proposed)
            self._write_unlocked(records)
        return proposed

    def release(
        self, task_id: str, *, now: datetime | None = None
    ) -> ScopeReservation:
        current = _utc(now or datetime.now(timezone.utc))
        if not _TASK_ID.fullmatch(task_id):
            raise ScopeReservationError("task identifier is invalid")
        with self._locked():
            records = self._load_unlocked(current)
            records, _ = self._expire_and_compact(records, current)
            for index, record in enumerate(records):
                if record.task_id != task_id or record.status != ReservationStatus.ACTIVE:
                    continue
                released = self._validate(
                    replace(
                        record,
                        status=ReservationStatus.RELEASED,
                        released_at=current,
                    ),
                    current,
                )
                records[index] = released
                self._write_unlocked(records)
                return released
            raise ScopeReservationError("active task reservation was not found")
