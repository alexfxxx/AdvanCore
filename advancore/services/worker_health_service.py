"""Provider-neutral, non-probing worker health summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from advancore.agent_runner.worker_registry import (
    WorkerApprovalState,
    get_worker_profile,
)
from advancore.services.worker_usage_service import (
    UsageState,
    WorkerUsageService,
)


class WorkerHealthState(str, Enum):
    AVAILABLE = "AVAILABLE"
    PAUSED = "PAUSED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    CHECKED_AT_LAUNCH = "CHECKED_AT_LAUNCH"
    SETUP_REQUIRED = "SETUP_REQUIRED"
    SIMULATION_ONLY = "SIMULATION_ONLY"


@dataclass(frozen=True)
class WorkerHealthSummary:
    worker: str
    label: str
    approval_state: WorkerApprovalState
    state: WorkerHealthState
    weekly_used_percent: float | None = None
    weekly_percent_limit: float | None = None
    runtime_seconds: int | None = None
    runtime_limit_seconds: int | None = None
    checked_at: datetime | None = None
    reset_at: datetime | None = None


class WorkerHealthService:
    """Read known local evidence without probing provider accounts or CLIs."""

    def __init__(self, usage_service: WorkerUsageService):
        self._usage_service = usage_service

    def get_status(self, worker: str) -> WorkerHealthSummary:
        profile = get_worker_profile(worker)
        if profile.provider == "kimi":
            try:
                usage = self._usage_service.get_summary("kimi")
            except Exception:
                usage = None
            if usage is None:
                state = WorkerHealthState.UNAVAILABLE
            elif usage.state == UsageState.AVAILABLE:
                state = WorkerHealthState.AVAILABLE
            elif usage.state == UsageState.PAUSED:
                state = WorkerHealthState.PAUSED
            elif usage.checked_at is not None:
                state = WorkerHealthState.STALE
            else:
                state = WorkerHealthState.UNAVAILABLE
            return WorkerHealthSummary(
                worker=profile.name,
                label=profile.label,
                approval_state=profile.approval_state,
                state=state,
                weekly_used_percent=(usage.weekly_used_percent if usage else None),
                weekly_percent_limit=(usage.weekly_percent_limit if usage else 20.0),
                runtime_seconds=(usage.runtime_seconds if usage else None),
                runtime_limit_seconds=(usage.runtime_limit_seconds if usage else 3600),
                checked_at=(usage.checked_at if usage else None),
                reset_at=(usage.reset_at if usage else None),
            )
        if profile.name in {"codex", "gemini"}:
            return WorkerHealthSummary(
                worker=profile.name,
                label=profile.label,
                approval_state=profile.approval_state,
                state=WorkerHealthState.CHECKED_AT_LAUNCH,
            )
        return WorkerHealthSummary(
            worker=profile.name,
            label=profile.label,
            approval_state=profile.approval_state,
            state=WorkerHealthState.SIMULATION_ONLY,
        )
