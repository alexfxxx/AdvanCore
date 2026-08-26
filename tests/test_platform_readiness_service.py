from datetime import datetime, timezone
from pathlib import Path

from advancore.services.local_backup_service import BackupInventory, BackupRecord
from advancore.services.platform_readiness_service import (
    PlatformReadinessService,
    ReadinessLevel,
)
from advancore.services.readiness_service import ReadinessSummary
from advancore.services.recovery_evidence_service import RecoveryEvidence


RECOVERY_REFERENCE = "advancore-20260826T010203Z-00000000"
NOW = datetime(2026, 8, 26, 2, 3, 4, tzinfo=timezone.utc)


def record(backup_id=RECOVERY_REFERENCE):
    return BackupRecord(backup_id, NOW, 10, "a" * 64, Path("a"), Path("m"))


def evidence(backup_id=RECOVERY_REFERENCE):
    return RecoveryEvidence(1, backup_id, NOW, "migration_head_fixture", 4, True)


def build(database, inventory, recovery):
    return PlatformReadinessService(
        lambda: database,
        lambda: inventory,
        lambda: recovery,
    ).get_summary()


def test_all_confirmed_local_facts_are_ready():
    summary = build(
        ReadinessSummary(True, True),
        BackupInventory((record(),), 0, 10),
        evidence(),
    )
    assert summary.overall == ReadinessLevel.READY
    assert [item.key for item in summary.items] == ["database", "backup", "recovery"]
    assert all(item.level == ReadinessLevel.READY for item in summary.items)


def test_missing_or_older_recovery_needs_attention_without_inventing_failure():
    missing = build(
        ReadinessSummary(True, True), BackupInventory((record(),), 0, 10), None
    )
    assert missing.overall == ReadinessLevel.ATTENTION
    assert missing.items[2].level == ReadinessLevel.ATTENTION

    older = build(
        ReadinessSummary(True, True),
        BackupInventory((record(),), 0, 10),
        evidence("advancore-20260825T010203Z-00000000"),
    )
    assert older.items[2].level == ReadinessLevel.ATTENTION
    assert "does not match" in older.items[2].message


def test_database_and_provider_errors_are_bounded_unavailable_states():
    def fail():
        raise RuntimeError("postgresql://user:password@host/database")

    summary = PlatformReadinessService(fail, fail, fail).get_summary()
    assert summary.overall == ReadinessLevel.UNAVAILABLE
    rendered = repr(summary).lower()
    for forbidden in ("postgresql://", "password", "@host"):
        assert forbidden not in rendered


def test_invalid_backup_entries_are_visible_attention():
    summary = build(
        ReadinessSummary(True, True),
        BackupInventory((record(),), 2, 10),
        evidence(),
    )
    assert summary.overall == ReadinessLevel.ATTENTION
    assert summary.items[1].level == ReadinessLevel.ATTENTION
    assert summary.items[2].level == ReadinessLevel.READY
