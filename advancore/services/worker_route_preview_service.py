"""Read-only governed worker route preview with no authority or launch."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from advancore.agent_runner.worker_registry import WorkerRole
from advancore.agent_runner.worker_routing import (
    WorkerAvailabilityEvidence,
    WorkerSelectionError,
    governed_worker_preferences,
    select_governed_worker,
)
from advancore.services.worker_routing_evidence_service import (
    WorkerRoutingEvidenceService,
)


class WorkerRoutePreviewState(str, Enum):
    SELECTED = "SELECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class WorkerRoutePreview:
    role: WorkerRole
    state: WorkerRoutePreviewState
    selected_worker: str | None
    evidence: tuple[WorkerAvailabilityEvidence, ...]
    message: str
    workers_launched: int = 0
    authority_consumed: bool = False


class WorkerRoutePreviewService:
    """Preview selection from current local evidence without probing workers."""

    def __init__(self, evidence_service: WorkerRoutingEvidenceService):
        self._evidence_service = evidence_service

    def preview(self, role: WorkerRole | str) -> WorkerRoutePreview:
        try:
            resolved_role = role if isinstance(role, WorkerRole) else WorkerRole(role)
            preferences = governed_worker_preferences(resolved_role)
        except (TypeError, ValueError, WorkerSelectionError):
            raise ValueError("Worker preview role is invalid")
        evidence = self._evidence_service.get_many(preferences)
        try:
            selection = select_governed_worker(resolved_role, evidence)
        except WorkerSelectionError:
            return WorkerRoutePreview(
                role=resolved_role,
                state=WorkerRoutePreviewState.BLOCKED,
                selected_worker=None,
                evidence=evidence,
                message=(
                    "No approved worker is currently proven available; "
                    "launch-time checks or controller attention are required."
                ),
            )
        return WorkerRoutePreview(
            role=selection.role,
            state=WorkerRoutePreviewState.SELECTED,
            selected_worker=selection.selected_worker,
            evidence=evidence,
            message=f"{selection.selected_worker} is first in the currently proven route.",
        )
