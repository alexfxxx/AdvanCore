"""Fail-closed local PostgreSQL backup creation and archive verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
from typing import Callable

from sqlalchemy.engine import make_url

from advancore.config import APP_NAME, APP_VERSION


_BACKUP_ID_PATTERN = re.compile(r"advancore-\d{8}T\d{6}Z-[0-9a-f]{8}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MANIFEST_KEYS = {
    "schema_version",
    "backup_id",
    "created_at",
    "application_name",
    "application_version",
    "archive_file",
    "archive_format",
    "size_bytes",
    "sha256",
}
_MAX_MANIFEST_BYTES = 16_384
_MAX_ARCHIVE_BYTES = 100 * 1024 * 1024 * 1024
_MAX_INVENTORY_FILES = 2_000
_DUMP_TIMEOUT_SECONDS = 180
_VERIFY_TIMEOUT_SECONDS = 60
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class LocalBackupError(RuntimeError):
    """Raised when a local backup cannot be created or trusted."""


@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    created_at: datetime
    size_bytes: int
    sha256: str
    archive_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class BackupInventory:
    records: tuple[BackupRecord, ...]
    invalid_entries: int
    total_size_bytes: int


class LocalBackupService:
    """Create and verify PostgreSQL custom archives without restoring them."""

    def __init__(
        self,
        repository_root: Path,
        database_url: str,
        backup_directory: Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        tool_finder: Callable[[str], str | None] = shutil.which,
        command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self._repository_root = Path(repository_root).resolve()
        self._backup_directory = Path(
            backup_directory or self._repository_root / "data" / "backups"
        ).expanduser()
        self._database_environment = self._validate_database_url(database_url)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (lambda: secrets.token_hex(4))
        self._tool_finder = tool_finder
        self._command_runner = command_runner

    @staticmethod
    def _validate_database_url(database_url: str) -> dict[str, str]:
        if not isinstance(database_url, str) or not database_url.strip():
            raise LocalBackupError("Local backup is unavailable.")
        try:
            url = make_url(database_url)
        except Exception as exc:
            raise LocalBackupError("Local backup is unavailable.") from exc
        if not url.drivername.startswith("postgresql"):
            raise LocalBackupError("Local backup supports PostgreSQL only.")
        host = (url.host or "").lower()
        if host not in _LOOPBACK_HOSTS:
            raise LocalBackupError("Local backup requires a loopback database.")
        if not url.database or not url.username:
            raise LocalBackupError("Local backup is unavailable.")
        environment = {
            "PGHOST": host,
            "PGPORT": str(url.port or 5432),
            "PGDATABASE": url.database,
            "PGUSER": url.username,
            "PGCONNECT_TIMEOUT": "10",
            "LC_ALL": "C",
        }
        if url.password is not None:
            environment["PGPASSWORD"] = url.password
        return environment

    def _prepare_directory(self) -> Path:
        directory = self._backup_directory
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise LocalBackupError("Local backup directory is unsafe.")
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                raise LocalBackupError("Local backup directory is unsafe.")
            os.chmod(directory, 0o700)
        except LocalBackupError:
            raise
        except OSError as exc:
            raise LocalBackupError("Local backup directory is unavailable.") from exc
        return directory.resolve()

    @staticmethod
    def _tool_path(tool_finder: Callable[[str], str | None], name: str) -> str:
        path = tool_finder(name)
        if not path or not Path(path).is_absolute():
            raise LocalBackupError("Required PostgreSQL backup tools are unavailable.")
        return path

    @staticmethod
    def _safe_timestamp(value: datetime) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise LocalBackupError("Backup clock is invalid.")
        return value.astimezone(timezone.utc).replace(microsecond=0)

    def _new_backup_identity(self) -> tuple[str, datetime]:
        created_at = self._safe_timestamp(self._clock())
        token = self._token_factory()
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{8}", token):
            raise LocalBackupError("Backup identifier is invalid.")
        timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
        return f"advancore-{timestamp}-{token}", created_at

    @staticmethod
    def _hash_archive(path: Path, expected_size: int | None = None) -> tuple[int, str]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise LocalBackupError("Backup archive is unavailable.") from exc
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise LocalBackupError("Backup archive is unsafe.")
            if details.st_size < 5 or details.st_size > _MAX_ARCHIVE_BYTES:
                raise LocalBackupError("Backup archive size is invalid.")
            if expected_size is not None and details.st_size != expected_size:
                raise LocalBackupError("Backup archive size does not match.")
            digest = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                signature = stream.read(5)
                if signature != b"PGDMP":
                    raise LocalBackupError("Backup archive format is invalid.")
                digest.update(signature)
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            return details.st_size, digest.hexdigest()
        finally:
            os.close(descriptor)

    @staticmethod
    def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
        temporary_path = path.with_suffix(".json.partial")
        if path.exists() or temporary_path.exists():
            raise LocalBackupError("Backup identifier already exists.")
        payload = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        if len(payload) > _MAX_MANIFEST_BYTES:
            raise LocalBackupError("Backup manifest is too large.")
        try:
            descriptor = os.open(
                temporary_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise LocalBackupError("Backup manifest could not be saved.") from exc

    @staticmethod
    def _sync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(path, flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise LocalBackupError("Backup directory could not be synchronized.") from exc

    def create_backup(self) -> BackupRecord:
        directory = self._prepare_directory()
        backup_id, created_at = self._new_backup_identity()
        archive_path = directory / f"{backup_id}.dump"
        manifest_path = directory / f"{backup_id}.json"
        temporary_path = directory / f"{backup_id}.dump.partial"
        if archive_path.exists() or manifest_path.exists() or temporary_path.exists():
            raise LocalBackupError("Backup identifier already exists.")

        pg_dump = self._tool_path(self._tool_finder, "pg_dump")
        command = [
            pg_dump,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
        ]
        try:
            descriptor = os.open(
                temporary_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                result = self._command_runner(
                    command,
                    cwd=self._repository_root,
                    env=dict(self._database_environment),
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    timeout=_DUMP_TIMEOUT_SECONDS,
                    check=False,
                )
                stream.flush()
                os.fsync(stream.fileno())
            if result.returncode != 0:
                raise LocalBackupError("PostgreSQL backup could not be created.")
            os.chmod(temporary_path, 0o600)
            size_bytes, sha256 = self._hash_archive(temporary_path)
            os.replace(temporary_path, archive_path)
            self._sync_directory(directory)
            manifest = {
                "schema_version": 1,
                "backup_id": backup_id,
                "created_at": created_at.isoformat().replace("+00:00", "Z"),
                "application_name": APP_NAME,
                "application_version": APP_VERSION,
                "archive_file": archive_path.name,
                "archive_format": "postgresql-custom",
                "size_bytes": size_bytes,
                "sha256": sha256,
            }
            self._write_manifest(manifest_path, manifest)
            self._sync_directory(directory)
            return self.verify_backup(manifest_path)
        except LocalBackupError:
            temporary_path.unlink(missing_ok=True)
            archive_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            temporary_path.unlink(missing_ok=True)
            archive_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)
            raise LocalBackupError("PostgreSQL backup could not be created.") from exc

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, object]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise LocalBackupError("Backup manifest is unavailable.") from exc
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise LocalBackupError("Backup manifest is unsafe.")
            if details.st_size <= 0 or details.st_size > _MAX_MANIFEST_BYTES:
                raise LocalBackupError("Backup manifest size is invalid.")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(_MAX_MANIFEST_BYTES + 1)
            try:
                manifest = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LocalBackupError("Backup manifest is invalid.") from exc
            if not isinstance(manifest, dict):
                raise LocalBackupError("Backup manifest is invalid.")
            return manifest
        finally:
            os.close(descriptor)

    @staticmethod
    def _validated_manifest(
        manifest: dict[str, object], manifest_path: Path
    ) -> tuple[str, datetime, int, str, str]:
        if set(manifest) != _MANIFEST_KEYS:
            raise LocalBackupError("Backup manifest fields are invalid.")
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
            raise LocalBackupError("Backup manifest version is unsupported.")
        backup_id = manifest["backup_id"]
        if not isinstance(backup_id, str) or not _BACKUP_ID_PATTERN.fullmatch(backup_id):
            raise LocalBackupError("Backup identifier is invalid.")
        if manifest_path.name != f"{backup_id}.json":
            raise LocalBackupError("Backup manifest name is invalid.")
        archive_file = manifest["archive_file"]
        if archive_file != f"{backup_id}.dump":
            raise LocalBackupError("Backup archive name is invalid.")
        if manifest["application_name"] != APP_NAME:
            raise LocalBackupError("Backup application is invalid.")
        if not isinstance(manifest["application_version"], str):
            raise LocalBackupError("Backup application version is invalid.")
        if manifest["archive_format"] != "postgresql-custom":
            raise LocalBackupError("Backup archive format is unsupported.")
        size_bytes = manifest["size_bytes"]
        if (
            type(size_bytes) is not int
            or size_bytes < 5
            or size_bytes > _MAX_ARCHIVE_BYTES
        ):
            raise LocalBackupError("Backup archive size is invalid.")
        sha256 = manifest["sha256"]
        if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
            raise LocalBackupError("Backup checksum is invalid.")
        created_raw = manifest["created_at"]
        if not isinstance(created_raw, str) or not created_raw.endswith("Z"):
            raise LocalBackupError("Backup time is invalid.")
        try:
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LocalBackupError("Backup time is invalid.") from exc
        if created_at.utcoffset() != timezone.utc.utcoffset(created_at):
            raise LocalBackupError("Backup time is invalid.")
        return backup_id, created_at, size_bytes, sha256, archive_file

    def _record_from_manifest(
        self, manifest_path: Path, *, verify_contents: bool
    ) -> BackupRecord:
        directory = self._prepare_directory()
        path = Path(manifest_path)
        try:
            if path.parent.resolve() != directory or path.is_symlink():
                raise LocalBackupError("Backup manifest path is unsafe.")
        except OSError as exc:
            raise LocalBackupError("Backup manifest path is unsafe.") from exc
        manifest = self._read_manifest(path)
        backup_id, created_at, size_bytes, sha256, archive_file = (
            self._validated_manifest(manifest, path)
        )
        archive_path = directory / archive_file
        try:
            if archive_path.parent.resolve() != directory or archive_path.is_symlink():
                raise LocalBackupError("Backup archive path is unsafe.")
        except OSError as exc:
            raise LocalBackupError("Backup archive path is unsafe.") from exc
        actual_size, actual_sha256 = self._hash_archive(archive_path, size_bytes)
        if actual_sha256 != sha256:
            raise LocalBackupError("Backup checksum does not match.")
        record = BackupRecord(
            backup_id=backup_id,
            created_at=created_at,
            size_bytes=actual_size,
            sha256=actual_sha256,
            archive_path=archive_path,
            manifest_path=path,
        )
        if verify_contents:
            pg_restore = self._tool_path(self._tool_finder, "pg_restore")
            try:
                result = self._command_runner(
                    [pg_restore, "--list", str(archive_path)],
                    cwd=self._repository_root,
                    env={"LC_ALL": "C"},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=_VERIFY_TIMEOUT_SECONDS,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise LocalBackupError("Backup archive could not be verified.") from exc
            if result.returncode != 0:
                raise LocalBackupError("Backup archive could not be verified.")
        return record

    def verify_backup(self, manifest_path: Path) -> BackupRecord:
        """Verify one archive and its PostgreSQL table of contents read-only."""
        return self._record_from_manifest(Path(manifest_path), verify_contents=True)

    def get_inventory(self) -> BackupInventory:
        """Return valid manifest-backed archives newest first."""
        directory = self._prepare_directory()
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            raise LocalBackupError("Local backup inventory is unavailable.") from exc
        if len(entries) > _MAX_INVENTORY_FILES:
            raise LocalBackupError("Local backup inventory is too large.")

        records = []
        invalid = 0
        manifest_archives = set()
        for path in entries:
            if path.suffix != ".json":
                continue
            try:
                record = self._record_from_manifest(path, verify_contents=False)
            except LocalBackupError:
                invalid += 1
                continue
            records.append(record)
            manifest_archives.add(record.archive_path.name)
        for path in entries:
            if path.suffix == ".dump" and path.name not in manifest_archives:
                invalid += 1
            elif path.name.endswith(".partial"):
                invalid += 1
        records.sort(key=lambda item: (item.created_at, item.backup_id), reverse=True)
        return BackupInventory(
            records=tuple(records),
            invalid_entries=invalid,
            total_size_bytes=sum(item.size_bytes for item in records),
        )

    def verify_latest(self) -> BackupRecord:
        inventory = self.get_inventory()
        if not inventory.records:
            raise LocalBackupError("No valid local backup is available.")
        return self.verify_backup(inventory.records[0].manifest_path)
