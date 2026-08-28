"""Bounded controller-owned timeline for governed worker attempts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
import tempfile


_WORKERS = frozenset({"kimi", "kimi-swarm", "gemini", "codex"})
_TASK_ID = re.compile(r"^TASK-[0-9]{3}$")
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
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
        for value in (
            event.terminal_reason,
            event.failure_classification,
            event.executable_resolution,
            event.runtime_path_profile,
        ):
            if value is not None and not _SAFE_VALUE.fullmatch(value):
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
        if started and finished and finished < started:
            raise WorkerOperationsError("worker timing order is invalid")
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

    def _load(self, now: datetime) -> list[WorkerOperationEvent]:
        if not self.path.exists():
            return []
        try:
            details = self.path.lstat()
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) & 0o077
                or details.st_nlink != 1
                or details.st_size > _MAX_BYTES
            ):
                raise WorkerOperationsError("worker timeline file is unsafe")
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise WorkerOperationsError("worker timeline cannot be read") from exc
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
            except (KeyError, TypeError, ValueError, WorkerOperationsError):
                continue
        events.sort(key=lambda item: item.occurred_at)
        return events[-_MAX_RECORDS:]

    def list_events(self, *, now: datetime | None = None) -> list[WorkerOperationEvent]:
        current = _utc(now or datetime.now(timezone.utc))
        return self._load(current)

    def record(
        self, event: WorkerOperationEvent, *, now: datetime | None = None
    ) -> WorkerOperationEvent:
        current = _utc(now or datetime.now(timezone.utc))
        validated = self._validate(event, current)
        events = self._load(current)
        events.append(validated)
        events = events[-_MAX_RECORDS:]
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.path.parent, 0o700)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as handle:
                temporary = Path(handle.name)
                os.chmod(temporary, 0o600)
                for item in events:
                    handle.write(json.dumps(self._payload(item), sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        except OSError as exc:
            try:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise WorkerOperationsError("worker timeline cannot be written") from exc
        return validated
