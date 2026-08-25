"""Bounded CLI behavior for the local backup foundation."""

from datetime import datetime, timezone
import importlib.util
from pathlib import Path

from advancore.services.local_backup_service import (
    BackupInventory,
    BackupRecord,
    LocalBackupError,
)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup-advancore.py"
SPEC = importlib.util.spec_from_file_location("backup_advancore_cli", SCRIPT)
CLI = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CLI)


def _record(tmp_path):
    return BackupRecord(
        backup_id="advancore-20260826T010203Z-1a2b3c4d",
        created_at=datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc),
        size_bytes=16,
        sha256="a" * 64,
        archive_path=tmp_path / "backup.dump",
        manifest_path=tmp_path / "backup.json",
    )


class FakeService:
    def __init__(self, record, *, error=False, inventory=None):
        self.record = record
        self.error = error
        self.inventory = inventory or BackupInventory((record,), 0, record.size_bytes)
        self.calls = []

    def create_backup(self):
        self.calls.append("create")
        if self.error:
            raise LocalBackupError("postgres://secret raw failure")
        return self.record

    def verify_latest(self):
        self.calls.append("verify-latest")
        if self.error:
            raise LocalBackupError("postgres://secret raw failure")
        return self.record

    def get_inventory(self):
        self.calls.append("status")
        if self.error:
            raise LocalBackupError("postgres://secret raw failure")
        return self.inventory


def test_cli_create_verify_and_status_are_bounded(tmp_path, capsys):
    record = _record(tmp_path)
    service = FakeService(record)
    factory = lambda: service

    assert CLI.main(["create"], service_factory=factory) == 0
    assert CLI.main(["verify-latest"], service_factory=factory) == 0
    assert CLI.main(["status"], service_factory=factory) == 0

    output = capsys.readouterr().out
    assert record.backup_id in output
    assert "1 valid, 0 invalid" in output
    assert service.calls == ["create", "verify-latest", "status"]


def test_cli_empty_status_is_clear(tmp_path, capsys):
    service = FakeService(
        _record(tmp_path),
        inventory=BackupInventory((), 2, 0),
    )
    assert CLI.main(["status"], service_factory=lambda: service) == 0
    output = capsys.readouterr().out
    assert "No valid local backup" in output
    assert "2" in output


def test_cli_failure_never_prints_raw_error_or_secret(tmp_path, capsys):
    service = FakeService(_record(tmp_path), error=True)
    assert CLI.main(["create"], service_factory=lambda: service) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "could not be completed safely" in captured.err
    for sensitive in ("postgres://", "secret", "raw failure"):
        assert sensitive not in captured.err


def test_backup_artifacts_are_ignored_and_runbook_blocks_in_place_restore():
    repository_root = Path(__file__).resolve().parents[1]
    gitignore = (repository_root / ".gitignore").read_text(encoding="utf-8")
    runbook = (
        repository_root / "docs" / "runbooks" / "LOCAL_BACKUP_RECOVERY.md"
    ).read_text(encoding="utf-8")
    normalized_runbook = " ".join(runbook.split())

    assert "data/backups/" in gitignore
    assert "no restore button or restore command" in runbook.lower()
    assert "do not restore into the configured `advancore` database" in (
        normalized_runbook
    )
    assert "--no-owner --no-privileges" in runbook
    assert (repository_root / "scripts" / "backup-advancore.py").stat().st_mode & 0o111
