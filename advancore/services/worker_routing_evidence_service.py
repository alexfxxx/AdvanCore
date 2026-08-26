"""Translate truthful worker health into conservative routing evidence."""

from __future__ import annotations

from advancore.agent_runner.worker_registry import WorkerApprovalState, get_worker_profile
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


def health_to_routing_evidence(
    summary: WorkerHealthSummary,
) -> WorkerAvailabilityEvidence:
    """Map known health only; launch-time checks never become availability."""
    if not isinstance(summary, WorkerHealthSummary):
        raise ValueError("Worker health summary is invalid")
    profile = get_worker_profile(summary.worker)
    state = _HEALTH_TO_AVAILABILITY.get(summary.state, WorkerAvailability.UNAVAILABLE)
    if (
        profile.approval_state != WorkerApprovalState.APPROVED
        or not profile.launchable
    ):
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
