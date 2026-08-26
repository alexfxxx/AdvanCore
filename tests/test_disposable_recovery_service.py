from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from advancore.services.disposable_recovery_service import (
    DisposableRecoveryError,
    DisposableRecoveryService,
)


VERIFICATION_OUTPUT = """alembic_version|a94f8b17d6e2
projects|4
knowledge_items|7
activity_logs|6
system_settings|1
"""


class BackupService:
    def __init__(self, archive: Path):
        self.archive = archive
        self.calls = 0

    def verify_latest(self):
        self.calls += 1
        return SimpleNamespace(backup_id="advancore-test", archive_path=self.archive)


class Runner:
    def __init__(self, fail_tool: str | None = None, cleanup_fails: bool = False):
        self.calls = []
        self.fail_tool = fail_tool
        self.cleanup_fails = cleanup_fails

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        tool = Path(command[0]).name
        operation = (
            "docker-ps"
            if tool == "docker" and command[1] == "ps"
            else "pg_restore"
            if tool == "docker" and command[1] == "exec"
            else tool
        )
        returncode = 1 if operation == self.fail_tool else 0
        if tool == "dropdb" and self.cleanup_fails:
            returncode = 1
        stdout = (
            "0123456789ab\n"
            if operation == "docker-ps"
            else VERIFICATION_OUTPUT
            if tool == "psql"
            else ""
        )
        return subprocess.CompletedProcess(command, returncode, stdout, "secret-error")


def tools(name: str) -> str:
    return f"/usr/local/bin/{name}"


def service(tmp_path: Path, runner: Runner, url: str = "postgresql://user:secret@localhost/live"):
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"PGDMP-test")
    return DisposableRecoveryService(
        tmp_path,
        url,
        BackupService(archive),
        clock=lambda: datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc),
        token_factory=lambda: "deadbeef",
        tool_finder=tools,
        command_runner=runner,
    )


class EvidenceRecorder:
    def __init__(self, runner, fails=False):
        self.runner = runner
        self.fails = fails
        self.calls = []

    def record(self, **kwargs):
        from advancore.services.recovery_evidence_service import RecoveryEvidenceError

        self.calls.append((kwargs, Path(self.runner.calls[-1][0][0]).name))
        if self.fails:
            raise RecoveryEvidenceError("secret local detail")


def test_rehearsal_restores_verifies_and_drops_only_generated_database(tmp_path):
    runner = Runner()
    result = service(tmp_path, runner).rehearse_latest()

    target = "advancore_recovery_20260826t010203_deadbeef"
    commands = [call[0] for call in runner.calls]
    assert [Path(command[0]).name for command in commands] == [
        "docker", "createdb", "docker", "psql", "dropdb"
    ]
    assert commands[1][-1] == target
    assert commands[2][commands[2].index("--dbname") + 1] == target
    assert commands[2][:7] == [
        "/usr/local/bin/docker", "exec", "-i", "-u", "postgres",
        "0123456789ab", "pg_restore",
    ]
    assert "--no-owner" in commands[2]
    assert "--no-privileges" in commands[2]
    assert "--exit-on-error" in commands[2]
    assert hasattr(runner.calls[2][1]["stdin"], "read")
    assert commands[-1] == [
        "/usr/local/bin/dropdb", "--maintenance-db=postgres", "--if-exists", target
    ]
    assert all(all("live" not in part for part in command) for command in commands)
    assert all(all("secret" not in part for part in command) for command in commands)
    assert all(call[1]["env"]["PGPASSWORD"] == "secret" for call in runner.calls)
    assert result.migration_head == "a94f8b17d6e2"
    assert dict(result.table_counts) == {
        "projects": 4,
        "knowledge_items": 7,
        "activity_logs": 6,
        "system_settings": 1,
    }
    assert result.cleanup_confirmed


@pytest.mark.parametrize("tool", ["createdb", "pg_restore", "psql"])
def test_every_creation_or_restore_failure_attempts_exact_cleanup(tmp_path, tool):
    runner = Runner(fail_tool=tool)
    with pytest.raises(DisposableRecoveryError):
        service(tmp_path, runner).rehearse_latest()
    commands = [call[0] for call in runner.calls]
    assert Path(commands[-1][0]).name == "dropdb"
    assert commands[-1][-1] == "advancore_recovery_20260826t010203_deadbeef"


def test_cleanup_failure_is_the_terminal_owner_attention_error(tmp_path):
    runner = Runner(fail_tool="pg_restore", cleanup_fails=True)
    with pytest.raises(DisposableRecoveryError, match="owner attention"):
        service(tmp_path, runner).rehearse_latest()


def test_malformed_verification_fails_closed_and_cleans_up(tmp_path):
    runner = Runner()

    def malformed(command, **kwargs):
        result = runner(command, **kwargs)
        if Path(command[0]).name == "psql":
            result.stdout = "projects|not-a-count\n"
        return result

    instance = service(tmp_path, runner)
    instance._command_runner = malformed
    with pytest.raises(DisposableRecoveryError, match="verification"):
        instance.rehearse_latest()
    assert Path(runner.calls[-1][0][0]).name == "dropdb"


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///local.db",
        "postgresql://user:secret@example.com/live",
        "postgresql://user@localhost/",
        "",
    ],
)
def test_non_loopback_or_incomplete_configuration_is_rejected(tmp_path, url):
    with pytest.raises(DisposableRecoveryError):
        service(tmp_path, Runner(), url=url)


def test_target_collision_with_live_database_fails_before_commands(tmp_path):
    target = "advancore_recovery_20260826t010203_deadbeef"
    runner = Runner()
    instance = service(
        tmp_path, runner, url=f"postgresql://user:secret@localhost/{target}"
    )
    with pytest.raises(DisposableRecoveryError, match="unsafe"):
        instance.rehearse_latest()
    assert [Path(call[0][0]).name for call in runner.calls] == ["docker"]


def test_raw_subprocess_error_is_never_exposed(tmp_path):
    runner = Runner(fail_tool="pg_restore")
    with pytest.raises(DisposableRecoveryError) as caught:
        service(tmp_path, runner).rehearse_latest()
    assert "secret-error" not in str(caught.value)


def test_evidence_is_recorded_only_after_cleanup(tmp_path):
    runner = Runner()
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"PGDMP-test")
    backup = BackupService(archive)
    backup.verify_latest = lambda: SimpleNamespace(
        backup_id="advancore-20260826T010203Z-00000000",
        archive_path=archive,
    )
    evidence = EvidenceRecorder(runner)
    instance = DisposableRecoveryService(
        tmp_path,
        "postgresql://user:secret@localhost/live",
        backup,
        evidence,
        clock=lambda: datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc),
        token_factory=lambda: "deadbeef",
        tool_finder=tools,
        command_runner=runner,
    )

    instance.rehearse_latest()

    assert evidence.calls == [
        (
            {
                "backup_id": "advancore-20260826T010203Z-00000000",
                "migration_head": "a94f8b17d6e2",
                "required_table_count": 4,
                "cleanup_confirmed": True,
            },
            "dropdb",
        )
    ]


def test_failed_rehearsal_never_records_evidence(tmp_path):
    runner = Runner(fail_tool="pg_restore")
    evidence = EvidenceRecorder(runner)
    instance = service(tmp_path, runner)
    instance._evidence_service = evidence
    with pytest.raises(DisposableRecoveryError):
        instance.rehearse_latest()
    assert evidence.calls == []


def test_evidence_failure_is_bounded_after_confirmed_cleanup(tmp_path):
    runner = Runner()
    evidence = EvidenceRecorder(runner, fails=True)
    instance = service(tmp_path, runner)
    instance._backup_service.verify_latest = lambda: SimpleNamespace(
        backup_id="advancore-20260826T010203Z-00000000",
        archive_path=instance._backup_service.archive,
    )
    instance._evidence_service = evidence
    with pytest.raises(DisposableRecoveryError, match="evidence could not be recorded") as caught:
        instance.rehearse_latest()
    assert "secret" not in str(caught.value)
    assert evidence.calls[0][1] == "dropdb"
