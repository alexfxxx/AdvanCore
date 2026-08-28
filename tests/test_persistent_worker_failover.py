from dataclasses import replace
import traceback

import pytest

from advancore.agent_runner.auto_pipeline import ProviderFailure
from advancore.agent_runner.failover import (
    FailoverCheckpoint,
    start_failover_checkpoint,
)
from advancore.agent_runner.persistent_kimi_launch import (
    PersistentKimiLaunchReason,
    PersistentKimiLaunchResult,
    PersistentKimiLaunchStatus,
)
from advancore.agent_runner.persistent_worker_failover import (
    PersistentWorkerFailoverError,
    transition_persistent_kimi_failover,
)
from advancore.agent_runner.worker import (
    EXECUTABLE_NOT_FOUND,
    RUNTIME_ERROR,
    SPAWN_ERROR,
)
from advancore.agent_runner.worker_registry import WorkerRole
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
)


FINGERPRINT = "a" * 64


def available(worker):
    return WorkerAvailabilityEvidence(worker, WorkerAvailability.AVAILABLE)


def unavailable(worker):
    return WorkerAvailabilityEvidence(worker, WorkerAvailability.UNAVAILABLE)


def kimi_checkpoint():
    return start_failover_checkpoint(
        run_id="FAILOVER-task152",
        task_id="TASK-152",
        branch="task-152-fallback-bridge",
        role=WorkerRole.IMPLEMENTATION,
        repository_fingerprint=FINGERPRINT,
        evidence=(available("kimi-swarm"), available("gemini"), available("codex")),
    )


def eligible_result(
    *,
    classification=None,
    terminal_reason=None,
):
    return PersistentKimiLaunchResult(
        ok=False,
        status=PersistentKimiLaunchStatus.WORKER_FAILED,
        reason=PersistentKimiLaunchReason.WORKER_FAILED,
        worker_failure_classification=classification,
        worker_terminal_reason=terminal_reason,
    )


def assert_blocked(decision, checkpoint):
    assert decision.transitioned is False
    assert decision.next_worker is None
    assert decision.failure_class is None
    assert decision.checkpoint == checkpoint


def test_executable_not_found_selects_gemini():
    checkpoint = kimi_checkpoint()
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(
            classification=EXECUTABLE_NOT_FOUND, terminal_reason="launch_failed"
        ),
        FINGERPRINT,
        (available("gemini"), available("codex")),
    )
    assert decision.transitioned is True
    assert decision.next_worker == "gemini"
    assert decision.failure_class == ProviderFailure.EXECUTABLE_UNAVAILABLE
    assert decision.checkpoint.selected_worker == "gemini"
    assert decision.checkpoint.attempted_workers == ("kimi-swarm",)


def test_spawn_error_selects_gemini():
    checkpoint = kimi_checkpoint()
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(classification=SPAWN_ERROR, terminal_reason="launch_failed"),
        FINGERPRINT,
        (available("gemini"), available("codex")),
    )
    assert decision.transitioned is True
    assert decision.next_worker == "gemini"
    assert decision.failure_class == ProviderFailure.EXECUTABLE_UNAVAILABLE


def test_quota_or_capacity_selects_gemini():
    checkpoint = kimi_checkpoint()
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(terminal_reason="quota_or_capacity"),
        FINGERPRINT,
        (available("gemini"), available("codex")),
    )
    assert decision.transitioned is True
    assert decision.next_worker == "gemini"
    assert decision.failure_class == ProviderFailure.QUOTA_OR_CAPACITY


def test_credential_access_required_selects_gemini():
    checkpoint = kimi_checkpoint()
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(terminal_reason="credential_access_required"),
        FINGERPRINT,
        (available("gemini"), available("codex")),
    )
    assert decision.transitioned is True
    assert decision.next_worker == "gemini"
    assert decision.failure_class == ProviderFailure.AUTHENTICATION_UNAVAILABLE


@pytest.mark.parametrize(
    "classification,terminal_reason,expected_failure",
    [
        (EXECUTABLE_NOT_FOUND, "launch_failed", ProviderFailure.EXECUTABLE_UNAVAILABLE),
        (SPAWN_ERROR, "launch_failed", ProviderFailure.EXECUTABLE_UNAVAILABLE),
        (None, "quota_or_capacity", ProviderFailure.QUOTA_OR_CAPACITY),
        (None, "credential_access_required", ProviderFailure.AUTHENTICATION_UNAVAILABLE),
    ],
)
def test_gemini_unavailable_falls_back_to_codex(
    classification, terminal_reason, expected_failure
):
    checkpoint = kimi_checkpoint()
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(
            classification=classification, terminal_reason=terminal_reason
        ),
        FINGERPRINT,
        (unavailable("gemini"), available("codex")),
    )
    assert decision.transitioned is True
    assert decision.next_worker == "codex"
    assert decision.failure_class == expected_failure
    assert decision.checkpoint.selected_worker == "codex"
    assert decision.checkpoint.attempted_workers == ("kimi-swarm",)


def test_preflight_failed_status_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = PersistentKimiLaunchResult(
        ok=False,
        status=PersistentKimiLaunchStatus.PREFLIGHT_FAILED,
        reason=PersistentKimiLaunchReason.WORKSPACE_NOT_READY,
    )
    decision = transition_persistent_kimi_failover(
        checkpoint, launch, FINGERPRINT, (available("gemini"), available("codex"))
    )
    assert_blocked(decision, checkpoint)


def test_postcheck_failed_status_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = PersistentKimiLaunchResult(
        ok=False,
        status=PersistentKimiLaunchStatus.POSTCHECK_FAILED,
        reason=PersistentKimiLaunchReason.OUT_OF_SCOPE_CHANGES,
    )
    decision = transition_persistent_kimi_failover(
        checkpoint, launch, FINGERPRINT, (available("gemini"), available("codex"))
    )
    assert_blocked(decision, checkpoint)


def test_successful_launch_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = PersistentKimiLaunchResult(
        ok=True,
        status=PersistentKimiLaunchStatus.COMPLETED,
        reason=PersistentKimiLaunchReason.COMPLETED,
    )
    decision = transition_persistent_kimi_failover(
        checkpoint, launch, FINGERPRINT, (available("gemini"), available("codex"))
    )
    assert_blocked(decision, checkpoint)


def test_worker_exception_reason_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = PersistentKimiLaunchResult(
        ok=False,
        status=PersistentKimiLaunchStatus.WORKER_FAILED,
        reason=PersistentKimiLaunchReason.WORKER_EXCEPTION,
    )
    decision = transition_persistent_kimi_failover(
        checkpoint, launch, FINGERPRINT, (available("gemini"), available("codex"))
    )
    assert_blocked(decision, checkpoint)


@pytest.mark.parametrize(
    "terminal_reason",
    [
        "runtime_error",
        "timeout",
        "cancelled",
        "authority_blocked",
        "unknown",
        "",
        None,
    ],
)
def test_non_eligible_terminal_reasons_are_blocked(terminal_reason):
    checkpoint = kimi_checkpoint()
    launch = eligible_result(terminal_reason=terminal_reason)
    decision = transition_persistent_kimi_failover(
        checkpoint, launch, FINGERPRINT, (available("gemini"), available("codex"))
    )
    assert_blocked(decision, checkpoint)


@pytest.mark.parametrize(
    "classification",
    [RUNTIME_ERROR, "UNKNOWN_CLASSIFICATION", "", None],
)
def test_non_eligible_failure_classifications_are_blocked(classification):
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=classification)
    decision = transition_persistent_kimi_failover(
        checkpoint, launch, FINGERPRINT, (available("gemini"), available("codex"))
    )
    assert_blocked(decision, checkpoint)


def test_malformed_launch_result_type_raises():
    checkpoint = kimi_checkpoint()
    with pytest.raises(PersistentWorkerFailoverError):
        transition_persistent_kimi_failover(
            checkpoint,
            {"ok": False},
            FINGERPRINT,
            (available("gemini"), available("codex")),
        )


def test_malformed_checkpoint_type_raises():
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    with pytest.raises(PersistentWorkerFailoverError):
        transition_persistent_kimi_failover(
            "not-a-checkpoint",
            launch,
            FINGERPRINT,
            (available("gemini"), available("codex")),
        )


def test_malformed_exact_checkpoint_does_not_escape_in_decision_or_error():
    secret = "DATABASE_URL=postgres://owner:secret@example.invalid/db\npublish-main"
    checkpoint = replace(kimi_checkpoint(), branch=secret)
    with pytest.raises(PersistentWorkerFailoverError) as captured:
        transition_persistent_kimi_failover(
            checkpoint,
            eligible_result(
                classification=EXECUTABLE_NOT_FOUND,
                terminal_reason="launch_failed",
            ),
            FINGERPRINT,
            (available("gemini"), available("codex")),
        )
    assert str(captured.value) == "Checkpoint is invalid"
    assert secret not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    rendered = "".join(
        traceback.format_exception(
            type(captured.value), captured.value, captured.value.__traceback__
        )
    )
    assert secret not in rendered


def test_malformed_repository_fingerprint_raises():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    with pytest.raises(PersistentWorkerFailoverError):
        transition_persistent_kimi_failover(
            checkpoint,
            launch,
            None,
            (available("gemini"), available("codex")),
        )


def test_malformed_evidence_raises():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    with pytest.raises(PersistentWorkerFailoverError):
        transition_persistent_kimi_failover(
            checkpoint, launch, FINGERPRINT, [available("gemini")]
        )


def test_duplicate_evidence_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    decision = transition_persistent_kimi_failover(
        checkpoint,
        launch,
        FINGERPRINT,
        (available("gemini"), available("gemini")),
    )
    assert_blocked(decision, checkpoint)


def test_non_evidence_item_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    decision = transition_persistent_kimi_failover(
        checkpoint,
        launch,
        FINGERPRINT,
        ("gemini", available("codex")),
    )
    assert_blocked(decision, checkpoint)


class _UnknownWorkerEvidence(WorkerAvailabilityEvidence):
    """Evidence with an invalid worker name that bypasses construction validation."""

    def __post_init__(self) -> None:
        pass


def test_unknown_worker_in_evidence_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    decision = transition_persistent_kimi_failover(
        checkpoint,
        launch,
        FINGERPRINT,
        (available("gemini"), _UnknownWorkerEvidence("unknown", WorkerAvailability.AVAILABLE)),
    )
    assert_blocked(decision, checkpoint)


def test_repository_drift_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    decision = transition_persistent_kimi_failover(
        checkpoint,
        launch,
        "b" * 64,
        (available("gemini"), available("codex")),
    )
    assert_blocked(decision, checkpoint)


def test_route_mismatch_non_kimi_selected_is_blocked():
    gemini_checkpoint = start_failover_checkpoint(
        run_id="FAILOVER-gemini",
        task_id="TASK-152",
        branch="task-152-fallback-bridge",
        role=WorkerRole.IMPLEMENTATION,
        repository_fingerprint=FINGERPRINT,
        evidence=(available("gemini"), available("codex")),
    )
    assert gemini_checkpoint.selected_worker == "gemini"
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    decision = transition_persistent_kimi_failover(
        gemini_checkpoint,
        launch,
        FINGERPRINT,
        (available("codex"),),
    )
    assert_blocked(decision, gemini_checkpoint)


def test_missing_gemini_evidence_cannot_skip_directly_to_codex():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(
        classification=EXECUTABLE_NOT_FOUND, terminal_reason="launch_failed"
    )
    decision = transition_persistent_kimi_failover(
        checkpoint,
        launch,
        FINGERPRINT,
        (available("codex"),),
    )
    assert_blocked(decision, checkpoint)


def test_planning_checkpoint_cannot_escape_implementation_route():
    checkpoint = replace(kimi_checkpoint(), role=WorkerRole.PLANNING)
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(
            classification=EXECUTABLE_NOT_FOUND, terminal_reason="launch_failed"
        ),
        FINGERPRINT,
        (unavailable("gemini"), available("codex")),
    )
    assert_blocked(decision, checkpoint)


@pytest.mark.parametrize(
    "classification,terminal_reason",
    [
        (SPAWN_ERROR, "runtime_error"),
        (RUNTIME_ERROR, "quota_or_capacity"),
        (EXECUTABLE_NOT_FOUND, None),
        (None, "launch_failed"),
    ],
)
def test_contradictory_or_incomplete_failure_metadata_is_blocked(
    classification, terminal_reason
):
    checkpoint = kimi_checkpoint()
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(
            classification=classification, terminal_reason=terminal_reason
        ),
        FINGERPRINT,
        (available("gemini"), available("codex")),
    )
    assert_blocked(decision, checkpoint)


class _ForgedEvidence(WorkerAvailabilityEvidence):
    def __post_init__(self) -> None:
        pass


@pytest.mark.parametrize("state", ["AVAILABLE", "BOGUS"])
def test_forged_evidence_subclass_is_blocked(state):
    checkpoint = kimi_checkpoint()
    decision = transition_persistent_kimi_failover(
        checkpoint,
        eligible_result(
            classification=EXECUTABLE_NOT_FOUND, terminal_reason="launch_failed"
        ),
        FINGERPRINT,
        (_ForgedEvidence("gemini", state), available("codex")),
    )
    assert_blocked(decision, checkpoint)


def test_no_available_fallback_is_blocked():
    checkpoint = kimi_checkpoint()
    launch = eligible_result(classification=EXECUTABLE_NOT_FOUND)
    decision = transition_persistent_kimi_failover(
        checkpoint,
        launch,
        FINGERPRINT,
        (unavailable("gemini"), unavailable("codex")),
    )
    assert_blocked(decision, checkpoint)
