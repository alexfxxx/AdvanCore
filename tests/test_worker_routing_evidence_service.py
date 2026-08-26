from advancore.agent_runner.worker_registry import WorkerApprovalState
from advancore.agent_runner.worker_routing import WorkerAvailability
from advancore.services.worker_health_service import (
    WorkerHealthState,
    WorkerHealthSummary,
)
from advancore.services.worker_routing_evidence_service import (
    WorkerRoutingEvidenceService,
    health_to_routing_evidence,
)


def summary(worker, state, approval=WorkerApprovalState.APPROVED):
    return WorkerHealthSummary(worker, worker, approval, state)


def test_known_kimi_health_maps_exactly_without_probe():
    for health, expected in (
        (WorkerHealthState.AVAILABLE, WorkerAvailability.AVAILABLE),
        (WorkerHealthState.PAUSED, WorkerAvailability.PAUSED),
        (WorkerHealthState.STALE, WorkerAvailability.STALE),
        (WorkerHealthState.UNAVAILABLE, WorkerAvailability.UNAVAILABLE),
    ):
        result = health_to_routing_evidence(summary("kimi-swarm", health))
        assert result.worker == "kimi-swarm"
        assert result.state == expected


def test_codex_launch_check_is_not_misreported_as_available():
    result = health_to_routing_evidence(
        summary("codex", WorkerHealthState.CHECKED_AT_LAUNCH)
    )
    assert result.state == WorkerAvailability.UNAVAILABLE


def test_gemini_candidate_cannot_become_available_from_health():
    result = health_to_routing_evidence(
        summary(
            "gemini",
            WorkerHealthState.AVAILABLE,
            WorkerApprovalState.CANDIDATE,
        )
    )
    assert result.state == WorkerAvailability.SETUP_REQUIRED


def test_health_failure_becomes_bounded_unavailable_evidence():
    class Health:
        def get_status(self, worker):
            raise RuntimeError("provider credential traceback")

    service = WorkerRoutingEvidenceService(Health())
    assert service.get("kimi-swarm").state == WorkerAvailability.UNAVAILABLE
    assert service.get("gemini").state == WorkerAvailability.SETUP_REQUIRED


def test_many_is_ordered_and_rejects_duplicates():
    class Health:
        def get_status(self, worker):
            state = (
                WorkerHealthState.AVAILABLE
                if worker == "kimi-swarm"
                else WorkerHealthState.CHECKED_AT_LAUNCH
            )
            return summary(worker, state)

    service = WorkerRoutingEvidenceService(Health())
    evidence = service.get_many(("kimi-swarm", "codex"))
    assert [item.worker for item in evidence] == ["kimi-swarm", "codex"]

    import pytest

    with pytest.raises(ValueError, match="invalid"):
        service.get_many(("codex", "codex"))
