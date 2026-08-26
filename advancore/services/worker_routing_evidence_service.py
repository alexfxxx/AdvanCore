"""Translate truthful worker health into conservative routing evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Callable

from advancore.agent_runner.worker_registry import (
    WorkerApprovalState,
    get_worker_profile,
)
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
)
from advancore.services.worker_health_service import (
    WorkerHealthService,
    WorkerHealthState,
    WorkerHealthSummary,
)


_HEALTH_TO_AVAILABILITY = {
    WorkerHealthState.AVAILABLE: WorkerAvailability.AVAILABLE,
    WorkerHealthState.PAUSED: WorkerAvailability.PAUSED,
    WorkerHealthState.STALE: WorkerAvailability.STALE,
    WorkerHealthState.UNAVAILABLE: WorkerAvailability.UNAVAILABLE,
    WorkerHealthState.SETUP_REQUIRED: WorkerAvailability.SETUP_REQUIRED,
    WorkerHealthState.CHECKED_AT_LAUNCH: WorkerAvailability.UNAVAILABLE,
    WorkerHealthState.SIMULATION_ONLY: WorkerAvailability.UNAVAILABLE,
}

_FIXED_ROUTE = ("kimi-swarm", "gemini", "codex")
_SAFE_FAILURES = {
    "EXECUTABLE_UNAVAILABLE": "executable",
    "QUOTA_OR_CAPACITY": "limit_or_quota",
    "LIMIT_OR_QUOTA": "limit_or_quota",
    "CAPACITY": "capacity",
    "AUTHENTICATION_UNAVAILABLE": "authentication",
}
_MAX_RECEIPT_BYTES = 2_000_000


@dataclass(frozen=True)
class WorkerHandoffNotification:
    """Safe evidence for one genuine automatic worker transition."""

    previous_worker: str
    next_worker: str
    reason: str
    occurred_at: datetime


@dataclass(frozen=True)
class WorkerSwitchingStatus:
    """Latest controller-owned worker fact and bounded recent transitions."""

    selected_worker: str | None
    handoffs: tuple[WorkerHandoffNotification, ...]


def health_to_routing_evidence(
    summary: WorkerHealthSummary,
) -> WorkerAvailabilityEvidence:
    """Map known health only; launch-time checks never become availability."""
    if not isinstance(summary, WorkerHealthSummary):
        raise ValueError("Worker health summary is invalid")
    profile = get_worker_profile(summary.worker)
    state = _HEALTH_TO_AVAILABILITY.get(summary.state, WorkerAvailability.UNAVAILABLE)
    if profile.approval_state != WorkerApprovalState.APPROVED or not profile.launchable:
        state = (
            WorkerAvailability.SETUP_REQUIRED
            if profile.requires_owner_setup
            else WorkerAvailability.UNAVAILABLE
        )
    return WorkerAvailabilityEvidence(profile.name, state)


class WorkerRoutingEvidenceService:
    """Build explicit evidence without probing accounts or launching workers."""

    def __init__(self, health_service: WorkerHealthService):
        self._health_service = health_service

    def get(self, worker: str) -> WorkerAvailabilityEvidence:
        try:
            summary = self._health_service.get_status(worker)
            return health_to_routing_evidence(summary)
        except Exception:
            profile = get_worker_profile(worker)
            state = (
                WorkerAvailability.SETUP_REQUIRED
                if profile.requires_owner_setup
                else WorkerAvailability.UNAVAILABLE
            )
            return WorkerAvailabilityEvidence(profile.name, state)

    def get_many(
        self, workers: tuple[str, ...]
    ) -> tuple[WorkerAvailabilityEvidence, ...]:
        if not isinstance(workers, tuple) or len(set(workers)) != len(workers):
            raise ValueError("Worker evidence request is invalid")
        return tuple(self.get(worker) for worker in workers)


class WorkerSwitchingStatusService:
    """Read safe status from bounded local auto-pipeline audit receipts."""

    def __init__(
        self,
        repo_root: Path,
        now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._path = repo_root / ".agent_runner" / "auto" / "auto_pipeline.jsonl"
        self._now_provider = now_provider

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)

    def get_status(self) -> WorkerSwitchingStatus:
        try:
            if (
                not self._path.is_file()
                or self._path.is_symlink()
                or self._path.stat().st_size > _MAX_RECEIPT_BYTES
            ):
                return WorkerSwitchingStatus(None, ())
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return WorkerSwitchingStatus(None, ())

        now = self._now_provider().astimezone(timezone.utc)
        cutoff = now - timedelta(days=7)
        selected_worker = None
        selected_at = None
        handoffs: list[WorkerHandoffNotification] = []
        for line in lines[-1000:]:
            try:
                payload = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(payload, dict):
                continue
            occurred_at = self._timestamp(payload.get("timestamp"))
            worker = payload.get("terminal_worker")
            if (
                occurred_at is not None
                and occurred_at <= now + timedelta(minutes=5)
                and worker in _FIXED_ROUTE
                and (selected_at is None or occurred_at > selected_at)
            ):
                selected_worker = worker
                selected_at = occurred_at
            if occurred_at is None or not cutoff <= occurred_at <= now + timedelta(
                minutes=5
            ):
                continue
            attempts = payload.get("automatic_handoffs", ())
            if not isinstance(attempts, list):
                continue
            for attempt in attempts:
                if not isinstance(attempt, dict) or set(attempt) != {
                    "previous_worker",
                    "next_worker",
                    "reason",
                }:
                    continue
                previous = attempt.get("previous_worker")
                following = attempt.get("next_worker")
                reason = attempt.get("reason")
                if (
                    previous in _FIXED_ROUTE
                    and following in _FIXED_ROUTE
                    and _FIXED_ROUTE.index(following)
                    == _FIXED_ROUTE.index(previous) + 1
                    and reason in set(_SAFE_FAILURES.values())
                ):
                    handoffs.append(
                        WorkerHandoffNotification(
                            previous, following, reason, occurred_at
                        )
                    )
        handoffs.sort(key=lambda item: item.occurred_at, reverse=True)
        return WorkerSwitchingStatus(selected_worker, tuple(handoffs[:5]))
