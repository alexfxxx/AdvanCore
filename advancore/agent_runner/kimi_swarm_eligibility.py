"""Pure controller gate for an explicitly assigned Kimi Swarm task."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import re

from advancore.agent_runner.kimi_scope_manifest import (
    KimiScopeManifestError,
    build_kimi_scope_manifest,
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


_TASK_ID = re.compile(r"^TASK-[0-9]{3}$")
_TASK_PATH = re.compile(r"^tasks/(TASK-[0-9]{3})-[A-Za-z0-9_.-]+\.md$")
_FEATURE_BRANCH = re.compile(r"^task-[a-z0-9][a-z0-9-]{0,100}$")
_VERIFICATION_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_MULTI_FILE_MINIMUM = 11
_MAX_QUEUE_CLAIM_AGE = timedelta(hours=2)
_MAX_RESERVATION_LEASE = timedelta(hours=4)


class SwarmWorkKind(str, Enum):
    MULTI_FILE = "MULTI_FILE"
    ARCHITECTURE = "ARCHITECTURE"


class SwarmEligibilityReason(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    SCOPE_INVALID = "SCOPE_INVALID"
    QUEUE_MISMATCH = "QUEUE_MISMATCH"
    RESERVATION_MISMATCH = "RESERVATION_MISMATCH"
    WORKSPACE_NOT_READY = "WORKSPACE_NOT_READY"
    MANIFEST_NOT_VERIFIED = "MANIFEST_NOT_VERIFIED"
    WORK_UNSUITABLE = "WORK_UNSUITABLE"
    TIME_INVALID = "TIME_INVALID"


@dataclass(frozen=True)
class SwarmEligibilityResult:
    eligible: bool
    reason: SwarmEligibilityReason
    scope_count: int = 0


@dataclass(frozen=True)
class ManifestVerificationEvidence:
    """Identity-bound evidence produced after reading back one scope manifest."""

    task_id: str
    allowed_paths: tuple[str, ...]
    workspace_branch: str
    verified_at: datetime
    verification_id: str


def _utc(value: datetime) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc)


def evaluate_kimi_swarm_eligibility(
    *,
    task_id: str,
    work_kind: SwarmWorkKind,
    allowed_paths: list[str] | tuple[str, ...],
    queue_record: TaskQueueRecord,
    reservation: ScopeReservation,
    workspace: PersistentWorkspaceReadiness,
    manifest_verification: ManifestVerificationEvidence,
    now: datetime,
) -> SwarmEligibilityResult:
    """Return a decision only; never mutate state, select or launch a worker."""
    if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
        return SwarmEligibilityResult(False, SwarmEligibilityReason.SCOPE_INVALID)
    try:
        manifest = build_kimi_scope_manifest(task_id, allowed_paths)
    except KimiScopeManifestError:
        return SwarmEligibilityResult(False, SwarmEligibilityReason.SCOPE_INVALID)
    scope_count = len(manifest.allowed_paths)

    current = _utc(now)
    if current is None:
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.TIME_INVALID, scope_count
        )
    if (
        not isinstance(queue_record, TaskQueueRecord)
        or queue_record.task_id != task_id
        or not isinstance(queue_record.task_path, str)
        or (task_match := _TASK_PATH.fullmatch(queue_record.task_path)) is None
        or task_match.group(1) != task_id
        or queue_record.worker != "kimi-swarm"
        or queue_record.status != TaskQueueStatus.RUNNING
        or queue_record.claimed_at is None
        or queue_record.finished_at is not None
    ):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.QUEUE_MISMATCH, scope_count
        )
    enqueued = _utc(queue_record.enqueued_at)
    claimed = _utc(queue_record.claimed_at)
    if (
        enqueued is None
        or claimed is None
        or claimed < enqueued
        or claimed > current
        or current - claimed >= _MAX_QUEUE_CLAIM_AGE
    ):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.TIME_INVALID, scope_count
        )

    if not isinstance(reservation, ScopeReservation):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.RESERVATION_MISMATCH, scope_count
        )
    try:
        reservation_paths = tuple(path.casefold() for path in reservation.paths)
    except (AttributeError, TypeError):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.RESERVATION_MISMATCH, scope_count
        )
    manifest_paths = tuple(path.casefold() for path in manifest.allowed_paths)
    if (
        reservation.task_id != task_id
        or reservation.worker != "kimi-swarm"
        or reservation.status != ReservationStatus.ACTIVE
        or reservation.released_at is not None
        or len(set(reservation_paths)) != len(reservation_paths)
        or set(reservation_paths) != set(manifest_paths)
    ):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.RESERVATION_MISMATCH, scope_count
        )
    reserved = _utc(reservation.reserved_at)
    expires = _utc(reservation.expires_at)
    if (
        reserved is None
        or expires is None
        or expires <= reserved
        or reserved > current
        or current >= expires
        or expires - reserved > _MAX_RESERVATION_LEASE
    ):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.TIME_INVALID, scope_count
        )

    expected_branch_prefix = f"task-{task_id.removeprefix('TASK-')}-".lower()
    if (
        not isinstance(workspace, PersistentWorkspaceReadiness)
        or not workspace.eligible
        or workspace.reason != WorkspaceReadinessReason.READY
        or not isinstance(workspace.branch, str)
        or not _FEATURE_BRANCH.fullmatch(workspace.branch)
        or not workspace.branch.startswith(expected_branch_prefix)
    ):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.WORKSPACE_NOT_READY, scope_count
        )
    if not isinstance(manifest_verification, ManifestVerificationEvidence):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.MANIFEST_NOT_VERIFIED, scope_count
        )
    verified = _utc(manifest_verification.verified_at)
    try:
        verified_manifest = build_kimi_scope_manifest(
            manifest_verification.task_id,
            manifest_verification.allowed_paths,
        )
    except KimiScopeManifestError:
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.MANIFEST_NOT_VERIFIED, scope_count
        )
    if (
        manifest_verification.task_id != task_id
        or verified_manifest != manifest
        or manifest_verification.workspace_branch != workspace.branch
        or verified is None
        or verified < claimed
        or verified < reserved
        or verified > current
        or not isinstance(manifest_verification.verification_id, str)
        or not _VERIFICATION_ID.fullmatch(manifest_verification.verification_id)
    ):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.MANIFEST_NOT_VERIFIED, scope_count
        )
    if not isinstance(work_kind, SwarmWorkKind) or (
        work_kind == SwarmWorkKind.MULTI_FILE
        and scope_count < _MULTI_FILE_MINIMUM
    ):
        return SwarmEligibilityResult(
            False, SwarmEligibilityReason.WORK_UNSUITABLE, scope_count
        )
    return SwarmEligibilityResult(
        True, SwarmEligibilityReason.ELIGIBLE, scope_count
    )
