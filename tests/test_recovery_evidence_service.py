from datetime import datetime, timedelta, timezone
import json

import pytest

from advancore.services.recovery_evidence_service import (
    RecoveryEvidenceError,
    RecoveryEvidence,
    RecoveryEvidenceService,
    recovery_evidence_is_fresh,
)


NOW = datetime(2026, 8, 26, 2, 3, 4, tzinfo=timezone.utc)
RECOVERY_REFERENCE = "advancore-20260826T010203Z-00000000"
MIGRATION_REFERENCE = "migration_head_fixture"


def service(tmp_path):
    return RecoveryEvidenceService(tmp_path, tmp_path / "state", clock=lambda: NOW)


def test_record_and_load_strict_secret_free_receipt(tmp_path):
    store = service(tmp_path)
    recorded = store.record(
        backup_id=RECOVERY_REFERENCE,
        migration_head=MIGRATION_REFERENCE,
        required_table_count=4,
        cleanup_confirmed=True,
    )
    assert store.load() == recorded
    raw = store.evidence_path.read_text(encoding="utf-8")
    assert "2026-08-26T02:03:04Z" in raw
    assert store.evidence_path.stat().st_mode & 0o077 == 0
    assert set(json.loads(raw)) == {
        "backup_id",
        "cleanup_confirmed",
        "completed_at",
        "migration_head",
        "required_table_count",
        "schema_version",
    }


def test_record_accepts_current_time_with_microseconds(tmp_path):
    current = datetime(2026, 8, 26, 2, 3, 4, 987654, tzinfo=timezone.utc)
    store = RecoveryEvidenceService(
        tmp_path,
        tmp_path / "state",
        clock=lambda: current,
    )

    recorded = store.record(
        backup_id=RECOVERY_REFERENCE,
        migration_head=MIGRATION_REFERENCE,
        required_table_count=4,
        cleanup_confirmed=True,
    )

    assert recorded.completed_at == current.replace(microsecond=0)
    assert store.load() == recorded


def test_missing_receipt_is_truthfully_absent(tmp_path):
    assert service(tmp_path).load() is None


def test_freshness_is_bounded_to_thirty_days_and_rejects_future_dates():
    current = RecoveryEvidence(
        1,
        RECOVERY_REFERENCE,
        NOW - timedelta(days=30),
        MIGRATION_REFERENCE,
        4,
        True,
    )
    assert recovery_evidence_is_fresh(current, NOW)
    assert not recovery_evidence_is_fresh(
        RecoveryEvidence(
            1,
            RECOVERY_REFERENCE,
            NOW - timedelta(days=30, seconds=1),
            MIGRATION_REFERENCE,
            4,
            True,
        ),
        NOW,
    )
    assert not recovery_evidence_is_fresh(
        RecoveryEvidence(
            1,
            RECOVERY_REFERENCE,
            None,
            MIGRATION_REFERENCE,
            4,
            True,
        ),
        NOW,
    )
    assert not recovery_evidence_is_fresh(
        RecoveryEvidence(
            1,
            RECOVERY_REFERENCE,
            NOW + timedelta(seconds=1),
            MIGRATION_REFERENCE,
            4,
            True,
        ),
        NOW,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"unexpected": True},
        {"cleanup_confirmed": False},
        {"backup_id": "caller-controlled"},
        {"required_table_count": 0},
        {"completed_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    ],
)
def test_tampered_or_unsafe_receipt_fails_closed(tmp_path, changes):
    store = service(tmp_path)
    store.record(
        backup_id=RECOVERY_REFERENCE,
        migration_head=MIGRATION_REFERENCE,
        required_table_count=4,
        cleanup_confirmed=True,
    )
    payload = json.loads(store.evidence_path.read_text(encoding="utf-8"))
    payload.update(changes)
    store.evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RecoveryEvidenceError):
        store.load()


def test_symlinked_state_fails_closed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "state"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(RecoveryEvidenceError, match="unsafe"):
        RecoveryEvidenceService(tmp_path, link, clock=lambda: NOW).record(
            backup_id=RECOVERY_REFERENCE,
            migration_head=MIGRATION_REFERENCE,
            required_table_count=4,
            cleanup_confirmed=True,
        )
