import pytest

from advancore.agent_runner import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
    WorkerRole,
    WorkerSelectionError,
    select_governed_worker,
)
from advancore.agent_runner.worker import WorkerError


def evidence(worker, state):
    return WorkerAvailabilityEvidence(worker, state)


def test_implementation_prefers_available_kimi_swarm():
    result = select_governed_worker(
        WorkerRole.IMPLEMENTATION,
        (
            evidence("kimi-swarm", WorkerAvailability.AVAILABLE),
            evidence("gemini", WorkerAvailability.AVAILABLE),
            evidence("codex", WorkerAvailability.AVAILABLE),
        ),
    )
    assert result.selected_worker == "kimi-swarm"
    assert result.considered == (("kimi-swarm", "SELECTED"),)


@pytest.mark.parametrize(
    "state",
    [
        WorkerAvailability.PAUSED,
        WorkerAvailability.STALE,
        WorkerAvailability.UNAVAILABLE,
        WorkerAvailability.SETUP_REQUIRED,
    ],
)
def test_gemini_is_selected_when_kimi_swarm_is_not_available(state):
    result = select_governed_worker(
        "implementation",
        (
            evidence("kimi-swarm", state),
            evidence("gemini", WorkerAvailability.AVAILABLE),
            evidence("codex", WorkerAvailability.AVAILABLE),
        ),
    )
    assert result.selected_worker == "gemini"
    assert result.considered[-1] == ("gemini", "SELECTED")


def test_missing_evidence_is_unavailable_not_assumed_healthy():
    result = select_governed_worker(
        WorkerRole.IMPLEMENTATION,
        (evidence("codex", WorkerAvailability.AVAILABLE),),
    )
    assert result.selected_worker == "codex"
    assert result.considered[0] == ("kimi-swarm", "UNAVAILABLE")


def test_approved_gemini_evidence_makes_it_routable():
    result = select_governed_worker(
        WorkerRole.IMPLEMENTATION,
        (evidence("gemini", WorkerAvailability.AVAILABLE),),
    )
    assert result.selected_worker == "gemini"


def test_no_available_worker_fails_closed():
    with pytest.raises(WorkerSelectionError, match="No approved worker"):
        select_governed_worker(
            "implementation",
            (
                evidence("kimi-swarm", WorkerAvailability.STALE),
                evidence("codex", WorkerAvailability.UNAVAILABLE),
            ),
        )


def test_unknown_roles_workers_duplicates_and_container_types_fail_closed():
    with pytest.raises(WorkerSelectionError, match="not routable"):
        select_governed_worker("owner", ())
    with pytest.raises(WorkerError, match="Unknown worker profile"):
        evidence("unknown", WorkerAvailability.AVAILABLE)
    duplicate = evidence("codex", WorkerAvailability.AVAILABLE)
    with pytest.raises(WorkerSelectionError, match="Duplicate"):
        select_governed_worker("implementation", (duplicate, duplicate))
    with pytest.raises(WorkerSelectionError, match="invalid"):
        select_governed_worker("implementation", [duplicate])


def test_selection_does_not_build_or_launch_adapters(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("selection must not build or launch a worker")

    monkeypatch.setattr("advancore.agent_runner.worker.build_worker_adapter", forbidden)
    result = select_governed_worker(
        "fallback", (evidence("codex", WorkerAvailability.AVAILABLE),)
    )
    assert result.selected_worker == "codex"
