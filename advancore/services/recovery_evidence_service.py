"""Strict local evidence that a disposable recovery rehearsal passed."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable


RECOVERY_EVIDENCE_SCHEMA_VERSION = 1
_BACKUP_ID = re.compile(r"advancore-\d{8}T\d{6}Z-[0-9a-f]{8}")
_MIGRATION_HEAD = re.compile(r"[A-Za-z0-9_]{1,64}")
_MAX_EVIDENCE_BYTES = 16_384
RECOVERY_EVIDENCE_MAX_AGE = timedelta(days=30)
_EVIDENCE_KEYS = {
    "schema_version",
    "backup_id",
    "completed_at",
    "migration_head",
    "required_table_count",
    "cleanup_confirmed",
}


class RecoveryEvidenceError(RuntimeError):
    """Raised when recovery evidence cannot be safely stored or trusted."""


@dataclass(frozen=True)
class RecoveryEvidence:
    schema_version: int
    backup_id: str
    completed_at: datetime
    migration_head: str
    required_table_count: int
    cleanup_confirmed: bool


def recovery_evidence_is_fresh(
    evidence: RecoveryEvidence,
    now: datetime,
    *,
    max_age: timedelta = RECOVERY_EVIDENCE_MAX_AGE,
) -> bool:
    """Return true only for bounded, past-or-present recovery evidence."""
    if (
        not isinstance(evidence, RecoveryEvidence)
        or not isinstance(now, datetime)
        or not isinstance(evidence.completed_at, datetime)
        or evidence.completed_at.tzinfo is None
        or now.tzinfo is None
        or not isinstance(max_age, timedelta)
        or max_age <= timedelta(0)
    ):
        return False
    age = now.astimezone(timezone.utc) - evidence.completed_at.astimezone(timezone.utc)
    return timedelta(0) <= age <= max_age


class RecoveryEvidenceService:
    """Persist one bounded receipt outside Git without database credentials."""

    def __init__(
        self,
        repository_root: Path,
        state_directory: Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository_root = Path(repository_root).resolve()
        self._state_directory = Path(
            state_directory or self._repository_root / ".agent_runner" / "recovery"
        ).expanduser()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _validate(self, evidence: RecoveryEvidence) -> RecoveryEvidence:
        if not isinstance(evidence, RecoveryEvidence):
            raise RecoveryEvidenceError("Recovery evidence is invalid.")
        if evidence.schema_version != RECOVERY_EVIDENCE_SCHEMA_VERSION:
            raise RecoveryEvidenceError("Recovery evidence version is unsupported.")
        if not isinstance(evidence.backup_id, str) or not _BACKUP_ID.fullmatch(
            evidence.backup_id
        ):
            raise RecoveryEvidenceError("Recovery evidence is invalid.")
        if not isinstance(evidence.completed_at, datetime) or evidence.completed_at.tzinfo is None:
            raise RecoveryEvidenceError("Recovery evidence is invalid.")
        completed = evidence.completed_at.astimezone(timezone.utc)
        clock_value = self._clock()
        if not isinstance(clock_value, datetime) or clock_value.tzinfo is None:
            raise RecoveryEvidenceError("Recovery evidence clock is invalid.")
        if completed > clock_value.astimezone(timezone.utc).replace(microsecond=0):
            raise RecoveryEvidenceError("Recovery evidence is future-dated.")
        if not isinstance(evidence.migration_head, str) or not _MIGRATION_HEAD.fullmatch(
            evidence.migration_head
        ):
            raise RecoveryEvidenceError("Recovery evidence is invalid.")
        if (
            type(evidence.required_table_count) is not int
            or not 1 <= evidence.required_table_count <= 64
            or evidence.cleanup_confirmed is not True
        ):
            raise RecoveryEvidenceError("Recovery evidence is invalid.")
        return RecoveryEvidence(
            schema_version=evidence.schema_version,
            backup_id=evidence.backup_id,
            completed_at=completed.replace(microsecond=0),
            migration_head=evidence.migration_head,
            required_table_count=evidence.required_table_count,
            cleanup_confirmed=True,
        )

    def _prepare_directory(self) -> Path:
        directory = self._state_directory
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise RecoveryEvidenceError("Recovery evidence directory is unsafe.")
        try:
            directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            os.chmod(directory, 0o700)
            return directory.resolve(strict=True)
        except OSError as exc:
            raise RecoveryEvidenceError("Recovery evidence is unavailable.") from exc

    @property
    def evidence_path(self) -> Path:
        return self._state_directory / "latest.json"

    def record(
        self,
        *,
        backup_id: str,
        migration_head: str,
        required_table_count: int,
        cleanup_confirmed: bool,
    ) -> RecoveryEvidence:
        now = self._clock()
        evidence = self._validate(
            RecoveryEvidence(
                schema_version=RECOVERY_EVIDENCE_SCHEMA_VERSION,
                backup_id=backup_id,
                completed_at=now,
                migration_head=migration_head,
                required_table_count=required_table_count,
                cleanup_confirmed=cleanup_confirmed,
            )
        )
        directory = self._prepare_directory()
        path = directory / "latest.json"
        if path.exists() and path.is_symlink():
            raise RecoveryEvidenceError("Recovery evidence path is unsafe.")
        payload = asdict(evidence)
        payload["completed_at"] = evidence.completed_at.isoformat().replace("+00:00", "Z")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=".recovery-",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                os.chmod(temporary, 0o600)
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise RecoveryEvidenceError("Recovery evidence could not be saved.") from exc
        return evidence

    def load(self) -> RecoveryEvidence | None:
        directory = self._state_directory
        if not directory.exists():
            return None
        if directory.is_symlink() or not directory.is_dir():
            raise RecoveryEvidenceError("Recovery evidence directory is unsafe.")
        path = directory.resolve(strict=True) / "latest.json"
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise RecoveryEvidenceError("Recovery evidence path is unsafe.")
        try:
            if path.stat().st_size > _MAX_EVIDENCE_BYTES:
                raise RecoveryEvidenceError("Recovery evidence is invalid.")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise RecoveryEvidenceError("Recovery evidence is invalid.") from exc
        if not isinstance(payload, dict) or set(payload) != _EVIDENCE_KEYS:
            raise RecoveryEvidenceError("Recovery evidence is invalid.")
        try:
            completed = datetime.fromisoformat(payload["completed_at"].replace("Z", "+00:00"))
            evidence = RecoveryEvidence(
                schema_version=payload["schema_version"],
                backup_id=payload["backup_id"],
                completed_at=completed,
                migration_head=payload["migration_head"],
                required_table_count=payload["required_table_count"],
                cleanup_confirmed=payload["cleanup_confirmed"],
            )
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            raise RecoveryEvidenceError("Recovery evidence is invalid.") from exc
        return self._validate(evidence)
