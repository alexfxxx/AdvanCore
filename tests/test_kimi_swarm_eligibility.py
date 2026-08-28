"""Contract tests for the pure Kimi Swarm eligibility gate."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from advancore.agent_runner.kimi_swarm_eligibility import (
    SwarmEligibilityReason,
    SwarmWorkKind,
    evaluate_kimi_swarm_eligibility,
)
from advancore.agent_runner.persistent_worker_workspace import (
    PersistentWorkspaceReadiness,
    WorkspaceReadinessReason,
)
from advancore.agent_runner.scope_reservations import (
    ReservationStatus,
    ScopeReservation,
)
from advancore.agent_runner.task_queue import TaskQueueRecord, TaskQueueStatus


NOW = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
PATHS = tuple(f"advancore/file_{index:02d}.py" for index in range(11))


def _evidence():
    queue = TaskQueueRecord(
        task_id="TASK-148",
        task_path="tasks/TASK-148-kimi-swarm-eligibility-gate.md",
        worker="kimi-swarm",
        status=TaskQueueStatus.RUNNING,
        enqueued_at=NOW - timedelta(minutes=2),
        claimed_at=NOW - timedelta(minutes=1),
    )
    reservation = ScopeReservation(
        task_id="TASK-148",
        worker="kimi-swarm",
        paths=PATHS,
        status=ReservationStatus.ACTIVE,
        reserved_at=NOW - timedelta(minutes=2),
        expires_at=NOW + timedelta(hours=3),
    )
    workspace = PersistentWorkspaceReadiness(
        True, WorkspaceReadinessReason.READY, "task-148-swarm"
    )
    return queue, reservation, workspace


def _evaluate(**overrides):
    queue, reservation, workspace = _evidence()
    values = {
        "task_id": "TASK-148",
        "work_kind": SwarmWorkKind.MULTI_FILE,
        "allowed_paths": PATHS,
        "queue_record": queue,
        "reservation": reservation,
        "workspace": workspace,
        "manifest_verified": True,
        "now": NOW,
    }
    values.update(overrides)
    return evaluate_kimi_swarm_eligibility(**values)


def test_matching_multi_file_evidence_is_eligible():
    result = _evaluate()
    assert result.eligible is True
    assert result.reason == SwarmEligibilityReason.ELIGIBLE
    assert result.scope_count == 11


def test_explicit_architecture_work_can_have_small_scope():
    paths = ("docs/architecture/design.md",)
    queue, reservation, workspace = _evidence()
    reservation = replace(reservation, paths=paths)
    result = _evaluate(
        work_kind=SwarmWorkKind.ARCHITECTURE,
        allowed_paths=paths,
        reservation=reservation,
        queue_record=queue,
        workspace=workspace,
    )
    assert result.eligible is True


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"task_id": "task-148"}, SwarmEligibilityReason.SCOPE_INVALID),
        ({"allowed_paths": ()}, SwarmEligibilityReason.SCOPE_INVALID),
        (
            {"allowed_paths": ("Shared.py", "shared.py")},
            SwarmEligibilityReason.SCOPE_INVALID,
        ),
        ({"manifest_verified": False}, SwarmEligibilityReason.MANIFEST_NOT_VERIFIED),
        (
            {"work_kind": SwarmWorkKind.MULTI_FILE, "allowed_paths": ("a.py",)},
            SwarmEligibilityReason.RESERVATION_MISMATCH,
        ),
        ({"now": NOW.replace(tzinfo=None)}, SwarmEligibilityReason.TIME_INVALID),
    ],
)
def test_invalid_inputs_fail_closed(overrides, reason):
    assert _evaluate(**overrides).reason == reason


def test_queue_mismatch_fails_closed():
    queue, _, _ = _evidence()
    assert _evaluate(queue_record=replace(queue, worker="kimi")).reason == (
        SwarmEligibilityReason.QUEUE_MISMATCH
    )
    assert _evaluate(queue_record=replace(queue, status=TaskQueueStatus.QUEUED)).reason == (
        SwarmEligibilityReason.QUEUE_MISMATCH
    )
    assert _evaluate(
        queue_record=replace(queue, task_path="tasks/TASK-999-wrong.md")
    ).reason == SwarmEligibilityReason.QUEUE_MISMATCH


def test_reservation_mismatch_or_expiry_fails_closed():
    _, reservation, _ = _evidence()
    assert _evaluate(reservation=replace(reservation, worker="kimi")).reason == (
        SwarmEligibilityReason.RESERVATION_MISMATCH
    )
    assert _evaluate(
        reservation=replace(reservation, expires_at=NOW)
    ).reason == SwarmEligibilityReason.TIME_INVALID


def test_matching_reservation_path_order_is_not_significant():
    _, reservation, _ = _evidence()
    result = _evaluate(reservation=replace(reservation, paths=tuple(reversed(PATHS))))
    assert result.eligible is True


def test_workspace_must_be_ready():
    _, _, workspace = _evidence()
    result = _evaluate(
        workspace=replace(
            workspace,
            eligible=False,
            reason=WorkspaceReadinessReason.DIRTY_WORKTREE,
        )
    )
    assert result.reason == SwarmEligibilityReason.WORKSPACE_NOT_READY
    assert _evaluate(workspace=replace(workspace, branch=None)).reason == (
        SwarmEligibilityReason.WORKSPACE_NOT_READY
    )


def test_small_multifile_scope_is_unsuitable_when_other_evidence_matches():
    paths = tuple(f"a{index}.py" for index in range(10))
    _, reservation, _ = _evidence()
    result = _evaluate(
        allowed_paths=paths,
        reservation=replace(reservation, paths=paths),
    )
    assert result.reason == SwarmEligibilityReason.WORK_UNSUITABLE


def test_gate_does_not_mutate_input_evidence():
    queue, reservation, workspace = _evidence()
    before = (queue, reservation, workspace)
    _evaluate(queue_record=queue, reservation=reservation, workspace=workspace)
    assert (queue, reservation, workspace) == before
