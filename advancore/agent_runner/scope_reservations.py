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
import secrets
import stat
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
            raise ScopeReservationError("reservation directory owner is unsafe")
        os.fchmod(descriptor, 0o700)
        result = descriptor
        descriptor = -1
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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
    def _locked(self) -> Iterator[int]:
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
                raise ScopeReservationError("reservation lock is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield parent_descriptor
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
            if parent_descriptor is not None:
                os.close(parent_descriptor)

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
        for value in paths:
            candidate = self.repository_root / PurePosixPath(value)
            if _has_symlink_component(candidate):
                raise ScopeReservationError(
                    "reservation scope contains a symbolic-link alias"
                )
            resolved = candidate.resolve(strict=False)
            if (
                resolved == self.repository_root
                or self.repository_root not in resolved.parents
            ):
                raise ScopeReservationError("reservation scope escapes repository")
        reserved = _utc(reservation.reserved_at)
        expires = _utc(reservation.expires_at)
        released = _utc(reservation.released_at) if reservation.released_at else None
        if (
            reserved > now + _FUTURE_SKEW
            or expires > reserved + _LEASE
            or (released is not None and released > now + _FUTURE_SKEW)
        ):
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

    def _load_unlocked(
        self, now: datetime, parent_descriptor: int
    ) -> list[ScopeReservation]:
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
                raise ScopeReservationError("reservation state file is unsafe")
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                descriptor = None
                raw = json.load(handle)
        except FileNotFoundError:
            return []
        except ScopeReservationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ScopeReservationError("reservation state cannot be read") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
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
        active = [
            record for record in records if record.status == ReservationStatus.ACTIVE
        ]
        for index, left in enumerate(active):
            for right in active[index + 1 :]:
                if any(
                    _paths_overlap(left_path, right_path)
                    for left_path in left.paths
                    for right_path in right.paths
                ):
                    raise ScopeReservationError(
                        "persisted active reservation scopes overlap"
                    )
        return records

    def _write_unlocked(
        self, records: list[ScopeReservation], parent_descriptor: int
    ) -> None:
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
            raise ScopeReservationError("reservation state cannot be written") from exc
        finally:
            if temporary_descriptor is not None:
                os.close(temporary_descriptor)

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
        with self._locked() as parent_descriptor:
            records = self._load_unlocked(current, parent_descriptor)
            records, changed = self._expire_and_compact(records, current)
            if changed:
                self._write_unlocked(records, parent_descriptor)
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
        with self._locked() as parent_descriptor:
            records = self._load_unlocked(current, parent_descriptor)
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
            if records and current < records[-1].reserved_at:
                raise ScopeReservationError("reservation timestamp moved backward")
            records.append(proposed)
            self._write_unlocked(records, parent_descriptor)
        return proposed

    def release(
        self, task_id: str, *, now: datetime | None = None
    ) -> ScopeReservation:
        current = _utc(now or datetime.now(timezone.utc))
        if not _TASK_ID.fullmatch(task_id):
            raise ScopeReservationError("task identifier is invalid")
        with self._locked() as parent_descriptor:
            records = self._load_unlocked(current, parent_descriptor)
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
                self._write_unlocked(records, parent_descriptor)
                return released
            raise ScopeReservationError("active task reservation was not found")
