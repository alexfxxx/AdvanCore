"""Deterministic safety checks for TASK-077 local backups."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import subprocess

import pytest

from advancore.services.local_backup_service import (
    LocalBackupError,
    LocalBackupService,
)


DATABASE_URL = (
    "postgresql+psycopg://advancore:sup3rsecret@localhost:5432/advancore"
)


class FakeCommandRunner:
    def __init__(self, archive=b"PGDMPsafe-fixture", *, dump_code=0, restore_code=0):
        self.archive = archive
        self.dump_code = dump_code
        self.restore_code = restore_code
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        if str(args[0]).endswith("docker") and args[1] == "ps":
            return subprocess.CompletedProcess(args, 0, stdout="0123456789ab\n", stderr="")
        if str(args[0]).endswith("docker") and args[1] == "exec":
            if self.dump_code == 0:
                kwargs["stdout"].write(self.archive)
            return subprocess.CompletedProcess(
                args,
                self.dump_code,
                stderr=b"postgres://sup3rsecret raw dump failure",
            )
        return subprocess.CompletedProcess(
            args,
            self.restore_code,
            stderr=b"postgres://sup3rsecret raw restore failure",
        )


def _tool_finder(name):
    return f"/tools/{name}"


def _service(
    tmp_path,
    runner=None,
    *,
    database_url=DATABASE_URL,
    clock=None,
    token="1a2b3c4d",
    backup_directory=None,
    tool_finder=_tool_finder,
):
    return LocalBackupService(
        tmp_path,
        database_url,
        backup_directory,
        clock=clock or (lambda: datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc)),
        token_factory=lambda: token,
        tool_finder=tool_finder,
        command_runner=runner or FakeCommandRunner(),
    )


def test_create_writes_atomic_owner_only_archive_and_strict_manifest(tmp_path):
    runner = FakeCommandRunner()
    service = _service(tmp_path, runner)

    record = service.create_backup()

    assert record.backup_id == "advancore-20260826T010203Z-1a2b3c4d"
    assert record.archive_path.read_bytes() == b"PGDMPsafe-fixture"
    assert stat.S_IMODE(record.archive_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(record.manifest_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(record.archive_path.parent.stat().st_mode) == 0o700
    assert not list(record.archive_path.parent.glob("*.partial"))

    manifest = json.loads(record.manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "application_name": "AdvanCore",
        "application_version": "0.1",
        "archive_file": f"{record.backup_id}.dump",
        "archive_format": "postgresql-custom",
        "backup_id": record.backup_id,
        "created_at": "2026-08-26T01:02:03Z",
        "schema_version": 1,
        "sha256": record.sha256,
        "size_bytes": len(b"PGDMPsafe-fixture"),
    }
    manifest_text = record.manifest_path.read_text(encoding="utf-8")
    assert "sup3rsecret" not in manifest_text
    assert "advancore:sup3rsecret" not in manifest_text

    discovery_args, discovery_kwargs = runner.calls[0]
    dump_args, dump_kwargs = runner.calls[1]
    restore_args, restore_kwargs = runner.calls[2]
    assert discovery_args[:2] == ["/tools/docker", "ps"]
    assert "PGPASSWORD" not in discovery_kwargs["env"]
    assert dump_args == [
        "/tools/docker",
        "exec",
        "-u",
        "postgres",
        "0123456789ab",
        "pg_dump",
        "--username",
        "advancore",
        "--dbname",
        "advancore",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
    ]
    assert "sup3rsecret" not in " ".join(dump_args)
    assert dump_kwargs["env"]["PGPASSWORD"] == "sup3rsecret"
    assert restore_args == [
        "/tools/pg_restore",
        "--list",
        str(record.archive_path),
    ]
    assert "PGPASSWORD" not in restore_kwargs["env"]


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///local.db",
        "postgresql://user:secret@example.com/advancore",
        "postgresql://user:secret@192.168.1.8/advancore",
        "postgresql://localhost/advancore",
        "",
    ],
)
def test_non_postgres_remote_or_incomplete_configuration_fails_closed(
    tmp_path, database_url
):
    with pytest.raises(LocalBackupError):
        _service(tmp_path, database_url=database_url)


def test_missing_tool_and_raw_subprocess_error_are_generic_and_cleanup(tmp_path):
    missing = _service(tmp_path, tool_finder=lambda _name: None)
    with pytest.raises(LocalBackupError, match="tools are unavailable") as missing_error:
        missing.create_backup()
    assert "sup3rsecret" not in str(missing_error.value)

    runner = FakeCommandRunner(dump_code=2)
    failing = _service(tmp_path, runner, token="deadbeef")
    with pytest.raises(LocalBackupError, match="could not be created") as failure:
        failing.create_backup()
    assert "sup3rsecret" not in str(failure.value)
    backup_directory = tmp_path / "data" / "backups"
    assert list(backup_directory.iterdir()) == []


def test_restore_list_failure_rejects_and_removes_new_unverified_backup(tmp_path):
    runner = FakeCommandRunner(restore_code=3)
    service = _service(tmp_path, runner)

    with pytest.raises(LocalBackupError, match="could not be verified") as failure:
        service.create_backup()

    assert "sup3rsecret" not in str(failure.value)
    assert list((tmp_path / "data" / "backups").iterdir()) == []


def test_verify_detects_signature_size_checksum_and_extra_manifest_fields(tmp_path):
    service = _service(tmp_path)
    record = service.create_backup()

    record.archive_path.write_bytes(b"WRONGsafe-fixture")
    with pytest.raises(LocalBackupError, match="format is invalid"):
        service.verify_backup(record.manifest_path)

    record.archive_path.write_bytes(b"PGDMPsafe-fixture-extra")
    with pytest.raises(LocalBackupError, match="size does not match"):
        service.verify_backup(record.manifest_path)

    record.archive_path.write_bytes(b"PGDMPunsafe-data")
    manifest = json.loads(record.manifest_path.read_text(encoding="utf-8"))
    manifest["size_bytes"] = len(b"PGDMPunsafe-data")
    record.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LocalBackupError, match="checksum does not match"):
        service.verify_backup(record.manifest_path)

    manifest["unexpected"] = True
    record.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LocalBackupError, match="fields are invalid"):
        service.verify_backup(record.manifest_path)


def test_manifest_name_path_traversal_and_symlinks_fail_closed(tmp_path):
    service = _service(tmp_path)
    record = service.create_backup()
    manifest = json.loads(record.manifest_path.read_text(encoding="utf-8"))

    manifest["archive_file"] = "../outside.dump"
    record.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LocalBackupError, match="archive name is invalid"):
        service.verify_backup(record.manifest_path)

    outside_manifest = tmp_path / "outside.json"
    outside_manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(LocalBackupError, match="path is unsafe"):
        service.verify_backup(outside_manifest)

    manifest["archive_file"] = f"{record.backup_id}.dump"
    record.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    archive_target = tmp_path / "archive-target.dump"
    archive_target.write_bytes(record.archive_path.read_bytes())
    record.archive_path.unlink()
    record.archive_path.symlink_to(archive_target)
    with pytest.raises(LocalBackupError, match="archive path is unsafe"):
        service.verify_backup(record.manifest_path)


def test_symlink_backup_directory_is_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "backups-link"
    link.symlink_to(target, target_is_directory=True)
    service = _service(tmp_path, backup_directory=link)
    with pytest.raises(LocalBackupError, match="directory is unsafe"):
        service.get_inventory()


def test_inventory_is_newest_first_counts_invalid_and_verify_latest(tmp_path):
    backup_directory = tmp_path / "backups"
    first_time = datetime(2026, 8, 25, 1, tzinfo=timezone.utc)
    first = _service(
        tmp_path,
        clock=lambda: first_time,
        token="11111111",
        backup_directory=backup_directory,
    ).create_backup()
    second_service = _service(
        tmp_path,
        clock=lambda: first_time + timedelta(hours=1),
        token="22222222",
        backup_directory=backup_directory,
    )
    second = second_service.create_backup()
    (backup_directory / "incomplete.dump.partial").write_bytes(b"partial")
    (backup_directory / "orphan.dump").write_bytes(b"PGDMPorphan")
    (backup_directory / "invalid.json").write_text("{}", encoding="utf-8")

    inventory = second_service.get_inventory()

    assert [item.backup_id for item in inventory.records] == [
        second.backup_id,
        first.backup_id,
    ]
    assert inventory.invalid_entries == 3
    assert inventory.total_size_bytes == first.size_bytes + second.size_bytes
    assert second_service.verify_latest().backup_id == second.backup_id


def test_empty_inventory_and_invalid_clock_or_token_are_safe(tmp_path):
    service = _service(tmp_path)
    assert service.get_inventory().records == ()
    with pytest.raises(LocalBackupError, match="No valid local backup"):
        service.verify_latest()

    naive_clock = _service(
        tmp_path,
        clock=lambda: datetime(2026, 8, 26),
        token="33333333",
    )
    with pytest.raises(LocalBackupError, match="clock is invalid"):
        naive_clock.create_backup()

    bad_token = _service(tmp_path, token="../unsafe")
    with pytest.raises(LocalBackupError, match="identifier is invalid"):
        bad_token.create_backup()


def test_manifest_size_limit_and_boolean_integer_fields_are_rejected(tmp_path):
    service = _service(tmp_path)
    record = service.create_backup()
    record.manifest_path.write_bytes(b"{" + b"x" * 20_000)
    with pytest.raises(LocalBackupError, match="manifest size is invalid"):
        service.verify_backup(record.manifest_path)

    record = _service(tmp_path, token="99999999").create_backup()
    manifest = json.loads(record.manifest_path.read_text(encoding="utf-8"))
    manifest["size_bytes"] = True
    record.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LocalBackupError, match="archive size is invalid"):
        service.verify_backup(record.manifest_path)


def test_directory_and_files_never_become_group_or_world_readable(tmp_path):
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(mode=0o777)
    os.chmod(backup_directory, 0o777)
    record = _service(tmp_path, backup_directory=backup_directory).create_backup()
    assert stat.S_IMODE(backup_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(record.archive_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(record.manifest_path.stat().st_mode) == 0o600
