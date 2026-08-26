"""Fail-closed PostgreSQL recovery rehearsal in one disposable database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
from typing import Callable

from sqlalchemy.engine import make_url

from advancore.services.local_backup_service import (
    BackupRecord,
    LocalBackupError,
    LocalBackupService,
)
from advancore.services.recovery_evidence_service import (
    RecoveryEvidenceError,
    RecoveryEvidenceService,
)
from advancore.services.local_postgres_container_service import (
    LocalPostgresContainerError,
    resolve_local_postgres_container,
)


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DATABASE_NAME_PATTERN = re.compile(
    r"advancore_recovery_\d{8}t\d{6}_[0-9a-f]{8}"
)
_MIGRATION_PATTERN = re.compile(r"[A-Za-z0-9_]{1,64}")
_REQUIRED_TABLES = ("projects", "knowledge_items", "activity_logs", "system_settings")
_MAX_ROW_COUNT = 1_000_000_000_000
_CREATE_TIMEOUT_SECONDS = 30
_RESTORE_TIMEOUT_SECONDS = 180
_VERIFY_TIMEOUT_SECONDS = 30
_DROP_TIMEOUT_SECONDS = 30


class DisposableRecoveryError(RuntimeError):
    """Raised when a recovery rehearsal or its cleanup cannot be trusted."""


@dataclass(frozen=True)
class DisposableRecoveryResult:
    backup_id: str
    migration_head: str
    table_counts: tuple[tuple[str, int], ...]
    cleanup_confirmed: bool


class DisposableRecoveryService:
    """Restore one verified archive into a service-owned temporary database."""

    def __init__(
        self,
        repository_root: Path,
        database_url: str,
        backup_service: LocalBackupService,
        evidence_service: RecoveryEvidenceService | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        tool_finder: Callable[[str], str | None] = shutil.which,
        command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self._repository_root = Path(repository_root).resolve()
        (
            self._live_database,
            self._database_user,
            self._environment,
        ) = self._validate_database_url(
            database_url
        )
        self._backup_service = backup_service
        self._evidence_service = evidence_service
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (lambda: secrets.token_hex(4))
        self._tool_finder = tool_finder
        self._command_runner = command_runner

    @staticmethod
    def _validate_database_url(
        database_url: str,
    ) -> tuple[str, str, dict[str, str]]:
        if not isinstance(database_url, str) or not database_url.strip():
            raise DisposableRecoveryError("Recovery rehearsal is unavailable.")
        try:
            url = make_url(database_url)
        except Exception as exc:
            raise DisposableRecoveryError("Recovery rehearsal is unavailable.") from exc
        if not url.drivername.startswith("postgresql"):
            raise DisposableRecoveryError("Recovery rehearsal requires PostgreSQL.")
        host = (url.host or "").lower()
        if host not in _LOOPBACK_HOSTS:
            raise DisposableRecoveryError(
                "Recovery rehearsal requires a loopback database."
            )
        if not url.database or not url.username:
            raise DisposableRecoveryError("Recovery rehearsal is unavailable.")
        environment = {
            "PGHOST": host,
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username,
            "PGCONNECT_TIMEOUT": "10",
            "LC_ALL": "C",
        }
        if url.password is not None:
            environment["PGPASSWORD"] = url.password
        return url.database, url.username, environment

    @staticmethod
    def _tool_path(tool_finder: Callable[[str], str | None], name: str) -> str:
        path = tool_finder(name)
        if not path or not Path(path).is_absolute():
            raise DisposableRecoveryError(
                "Required PostgreSQL recovery tools are unavailable."
            )
        return path

    def _new_database_name(self) -> str:
        now = self._clock()
        token = self._token_factory()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise DisposableRecoveryError("Recovery rehearsal clock is invalid.")
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{8}", token):
            raise DisposableRecoveryError("Recovery rehearsal identifier is invalid.")
        timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S").lower()
        name = f"advancore_recovery_{timestamp}_{token}"
        if not _DATABASE_NAME_PATTERN.fullmatch(name) or name == self._live_database:
            raise DisposableRecoveryError("Recovery rehearsal target is unsafe.")
        return name

    def _run(
        self,
        command: list[str],
        *,
        timeout: int,
        capture_output: bool = False,
        stdin_path: Path | None = None,
    ) -> subprocess.CompletedProcess:
        descriptor = None
        stream = None
        try:
            if stdin_path is not None:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(stdin_path, flags)
                details = os.fstat(descriptor)
                if not stat.S_ISREG(details.st_mode):
                    raise DisposableRecoveryError("Backup archive is unsafe.")
                stream = os.fdopen(descriptor, "rb", closefd=False)
            return self._command_runner(
                command,
                cwd=self._repository_root,
                env=dict(self._environment),
                stdin=stream if stream is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
        finally:
            if stream is not None:
                stream.close()
            if descriptor is not None:
                os.close(descriptor)

    def _running_postgres_container(self, docker: str) -> str:
        try:
            return resolve_local_postgres_container(
                self._repository_root,
                docker,
                int(self._environment["PGPORT"]),
                self._command_runner,
            )
        except (LocalPostgresContainerError, TypeError, ValueError) as exc:
            raise DisposableRecoveryError(
                "The local PostgreSQL recovery container is unavailable."
            ) from exc

    @staticmethod
    def _parse_verification(output: str) -> tuple[str, tuple[tuple[str, int], ...]]:
        if not isinstance(output, str) or len(output.encode("utf-8")) > 16_384:
            raise DisposableRecoveryError("Restored database verification failed.")
        values: dict[str, str] = {}
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("|", 1)
            if len(parts) != 2 or parts[0] in values:
                raise DisposableRecoveryError("Restored database verification failed.")
            values[parts[0]] = parts[1]
        expected = {"alembic_version", *_REQUIRED_TABLES}
        if set(values) != expected:
            raise DisposableRecoveryError("Restored database verification failed.")
        migration = values["alembic_version"]
        if not _MIGRATION_PATTERN.fullmatch(migration):
            raise DisposableRecoveryError("Restored database verification failed.")
        counts = []
        for table in _REQUIRED_TABLES:
            raw_count = values[table]
            if not re.fullmatch(r"0|[1-9][0-9]*", raw_count):
                raise DisposableRecoveryError("Restored database verification failed.")
            count = int(raw_count)
            if count > _MAX_ROW_COUNT:
                raise DisposableRecoveryError("Restored database verification failed.")
            counts.append((table, count))
        return migration, tuple(counts)

    def rehearse_latest(self) -> DisposableRecoveryResult:
        """Restore, inspect, and remove one service-owned disposable database."""
        try:
            backup: BackupRecord = self._backup_service.verify_latest()
        except LocalBackupError as exc:
            raise DisposableRecoveryError(
                "No verified local backup is available for rehearsal."
            ) from exc

        createdb = self._tool_path(self._tool_finder, "createdb")
        docker = self._tool_path(self._tool_finder, "docker")
        psql = self._tool_path(self._tool_finder, "psql")
        dropdb = self._tool_path(self._tool_finder, "dropdb")
        container_id = self._running_postgres_container(docker)
        target = self._new_database_name()
        creation_confirmed = False
        rehearsal_error: Exception | None = None
        migration = ""
        counts: tuple[tuple[str, int], ...] = ()

        verification_sql = ";".join(
            [
                "SELECT 'alembic_version', version_num FROM alembic_version",
                *(f"SELECT '{table}', count(*)::text FROM {table}" for table in _REQUIRED_TABLES),
            ]
        ) + ";"

        try:
            created = self._run(
                [
                    createdb,
                    "--maintenance-db=postgres",
                    "--encoding=UTF8",
                    "--template=template0",
                    target,
                ],
                timeout=_CREATE_TIMEOUT_SECONDS,
            )
            if created.returncode != 0:
                raise DisposableRecoveryError(
                    "Disposable recovery database could not be created."
                )
            creation_confirmed = True
            restored = self._run(
                [
                    docker,
                    "exec",
                    "-i",
                    "-u",
                    "postgres",
                    container_id,
                    "pg_restore",
                    "--username",
                    self._database_user,
                    "--dbname",
                    target,
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                ],
                timeout=_RESTORE_TIMEOUT_SECONDS,
                stdin_path=backup.archive_path,
            )
            if restored.returncode != 0:
                raise DisposableRecoveryError("Backup restore rehearsal failed.")
            verified = self._run(
                [
                    psql,
                    "--dbname",
                    target,
                    "--no-psqlrc",
                    "--tuples-only",
                    "--no-align",
                    "--field-separator=|",
                    "--set=ON_ERROR_STOP=1",
                    "--command",
                    verification_sql,
                ],
                timeout=_VERIFY_TIMEOUT_SECONDS,
                capture_output=True,
            )
            if verified.returncode != 0:
                raise DisposableRecoveryError(
                    "Restored database verification failed."
                )
            migration, counts = self._parse_verification(verified.stdout or "")
        except Exception as exc:
            rehearsal_error = exc
        finally:
            cleanup_ok = not creation_confirmed
            if creation_confirmed:
                try:
                    dropped = self._run(
                        [dropdb, "--maintenance-db=postgres", "--if-exists", target],
                        timeout=_DROP_TIMEOUT_SECONDS,
                    )
                    cleanup_ok = dropped.returncode == 0
                except (OSError, subprocess.SubprocessError):
                    cleanup_ok = False

        if not cleanup_ok:
            raise DisposableRecoveryError(
                "Disposable recovery cleanup could not be confirmed; owner attention is required."
            ) from rehearsal_error
        if rehearsal_error is not None:
            if isinstance(rehearsal_error, DisposableRecoveryError):
                raise rehearsal_error
            raise DisposableRecoveryError(
                "Disposable recovery rehearsal did not pass."
            ) from rehearsal_error
        result = DisposableRecoveryResult(
            backup_id=backup.backup_id,
            migration_head=migration,
            table_counts=counts,
            cleanup_confirmed=True,
        )
        if self._evidence_service is not None:
            try:
                self._evidence_service.record(
                    backup_id=result.backup_id,
                    migration_head=result.migration_head,
                    required_table_count=len(result.table_counts),
                    cleanup_confirmed=result.cleanup_confirmed,
                )
            except RecoveryEvidenceError as exc:
                raise DisposableRecoveryError(
                    "Recovery rehearsal passed, but its local evidence could not be recorded."
                ) from exc
        return result
