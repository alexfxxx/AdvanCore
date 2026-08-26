import pytest

from advancore.agent_runner.worker_registry import WorkerRole
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
    governed_worker_preferences,
)
from advancore.services.worker_route_preview_service import (
    WorkerRoutePreviewService,
    WorkerRoutePreviewState,
)


class Evidence:
    def __init__(self, states):
        self.states = states
        self.calls = []

    def get_many(self, workers):
        self.calls.append(workers)
        return tuple(
            WorkerAvailabilityEvidence(
                worker, self.states.get(worker, WorkerAvailability.UNAVAILABLE)
            )
            for worker in workers
        )


def test_preview_uses_code_owned_kimi_first_preferences():
    evidence = Evidence(
        {
            "kimi-swarm": WorkerAvailability.AVAILABLE,
            "codex": WorkerAvailability.AVAILABLE,
        }
    )
    result = WorkerRoutePreviewService(evidence).preview(WorkerRole.IMPLEMENTATION)
    assert evidence.calls == [("kimi-swarm", "gemini", "codex")]
    assert result.state == WorkerRoutePreviewState.SELECTED
    assert result.selected_worker == "kimi-swarm"
    assert result.workers_launched == 0
    assert not result.authority_consumed


def test_preview_fails_closed_when_no_worker_is_proven_available():
    result = WorkerRoutePreviewService(Evidence({})).preview("implementation")
    assert result.state == WorkerRoutePreviewState.BLOCKED
    assert result.selected_worker is None
    assert "launch-time checks" in result.message


def test_gemini_is_bounded_to_implementation_and_fallback_preferences():
    assert "gemini" in governed_worker_preferences("implementation")
    assert "gemini" in governed_worker_preferences("fallback")
    assert "gemini" not in governed_worker_preferences("planning")
    assert "gemini" not in governed_worker_preferences("review")


def test_unroutable_role_is_rejected():
    with pytest.raises(ValueError, match="invalid"):
        WorkerRoutePreviewService(Evidence({})).preview("simulation")
