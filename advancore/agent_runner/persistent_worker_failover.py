"""Fail-closed bridge from bounded persistent Kimi launch result to failover."""

from __future__ import annotations

from dataclasses import dataclass

from advancore.agent_runner.auto_pipeline import ProviderFailure
from advancore.agent_runner.failover import (
    FailoverCheckpoint,
    FailoverError,
    _validate_checkpoint,
    advance_failover_checkpoint,
)
from advancore.agent_runner.persistent_kimi_launch import (
    PersistentKimiLaunchReason,
    PersistentKimiLaunchResult,
    PersistentKimiLaunchStatus,
)
from advancore.agent_runner.persistent_kimi_reporting import (
    format_persistent_kimi_launch_result,
)
from advancore.agent_runner.worker import EXECUTABLE_NOT_FOUND, SPAWN_ERROR, WorkerError
from advancore.agent_runner.worker_registry import WorkerRole, get_worker_profile
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
)


class PersistentWorkerFailoverError(RuntimeError):
    """Raised when the bridge receives grossly malformed controller inputs."""


@dataclass(frozen=True)
class PersistentWorkerFailoverDecision:
    """Bounded result of an attempted persistent Kimi failover transition."""

    transitioned: bool
    next_worker: str | None
    failure_class: ProviderFailure | None
    checkpoint: FailoverCheckpoint


def _blocked_decision(
    checkpoint: FailoverCheckpoint,
) -> PersistentWorkerFailoverDecision:
    """Return the canonical no-transition decision without leaking details."""
    return PersistentWorkerFailoverDecision(
        transitioned=False,
        next_worker=None,
        failure_class=None,
        checkpoint=checkpoint,
    )


def _map_kimi_failure(
    launch_result: PersistentKimiLaunchResult,
) -> ProviderFailure | None:
    """Map one coherent approved provider-availability failure class."""
    classification = launch_result.worker_failure_classification
    terminal_reason = launch_result.worker_terminal_reason

    if (
        classification in (EXECUTABLE_NOT_FOUND, SPAWN_ERROR)
        and terminal_reason == "launch_failed"
    ):
        return ProviderFailure.EXECUTABLE_UNAVAILABLE
    if classification is None and terminal_reason == "quota_or_capacity":
        return ProviderFailure.QUOTA_OR_CAPACITY
    if classification is None and terminal_reason == "credential_access_required":
        return ProviderFailure.AUTHENTICATION_UNAVAILABLE
    return None


def _is_eligible_launch_result(launch_result: PersistentKimiLaunchResult) -> bool:
    if launch_result.ok is not False:
        return False
    if launch_result.status != PersistentKimiLaunchStatus.WORKER_FAILED:
        return False
    if launch_result.reason != PersistentKimiLaunchReason.WORKER_FAILED:
        return False
    return True


def _evidence_is_valid(
    evidence: tuple[WorkerAvailabilityEvidence, ...],
) -> bool:
    """Reject malformed or duplicate controller availability evidence."""
    seen: set[str] = set()
    for item in evidence:
        if (
            type(item) is not WorkerAvailabilityEvidence
            or type(item.worker) is not str
            or type(item.state) is not WorkerAvailability
            or item.worker not in {"gemini", "codex"}
        ):
            return False
        try:
            get_worker_profile(item.worker)
        except WorkerError:
            return False
        if item.worker in seen:
            return False
        seen.add(item.worker)
    # Codex may only be considered after the controller explicitly reports
    # Gemini's state. Missing evidence must never silently mean unavailable.
    return "gemini" in seen


def transition_persistent_kimi_failover(
    checkpoint: FailoverCheckpoint,
    launch_result: PersistentKimiLaunchResult,
    repository_fingerprint: str,
    evidence: tuple[WorkerAvailabilityEvidence, ...],
) -> PersistentWorkerFailoverDecision:
    """Advance a failover checkpoint after an eligible persistent Kimi failure.

    The bridge is pure and fail-closed: it inspects the bounded launch result,
    validates repository state, maps an eligible provider-availability failure
    to a ``ProviderFailure``, and delegates next-worker selection to the
    existing immutable failover checkpoint. It never launches a worker, writes
    state, consumes standing authority, or performs Git operations.
    """
    if type(checkpoint) is not FailoverCheckpoint:
        raise PersistentWorkerFailoverError("Checkpoint is not a FailoverCheckpoint")
    if type(launch_result) is not PersistentKimiLaunchResult:
        raise PersistentWorkerFailoverError(
            "Launch result is not a PersistentKimiLaunchResult"
        )
    if type(repository_fingerprint) is not str:
        raise PersistentWorkerFailoverError(
            "Repository fingerprint is not a string"
        )
    if type(evidence) is not tuple:
        raise PersistentWorkerFailoverError("Evidence is not a tuple")

    checkpoint_invalid = False
    try:
        _validate_checkpoint(checkpoint)
    except FailoverError:
        checkpoint_invalid = True
    if checkpoint_invalid:
        # Raise outside the handler so neither __cause__ nor __context__ can
        # retain malformed checkpoint values in a formatted traceback.
        raise PersistentWorkerFailoverError("Checkpoint is invalid")
    try:
        format_persistent_kimi_launch_result(launch_result)
    except TypeError:
        return _blocked_decision(checkpoint)

    if (
        checkpoint.role is not WorkerRole.IMPLEMENTATION
        or checkpoint.selected_worker != "kimi-swarm"
    ):
        return _blocked_decision(checkpoint)
    if not _is_eligible_launch_result(launch_result):
        return _blocked_decision(checkpoint)

    failure = _map_kimi_failure(launch_result)
    if failure is None:
        return _blocked_decision(checkpoint)

    if repository_fingerprint != checkpoint.repository_fingerprint:
        return _blocked_decision(checkpoint)

    if not _evidence_is_valid(evidence):
        return _blocked_decision(checkpoint)

    try:
        next_checkpoint = advance_failover_checkpoint(
            checkpoint,
            failed_worker="kimi-swarm",
            failure=failure,
            repository_fingerprint=repository_fingerprint,
            evidence=evidence,
        )
    except FailoverError:
        return _blocked_decision(checkpoint)

    return PersistentWorkerFailoverDecision(
        transitioned=True,
        next_worker=next_checkpoint.selected_worker,
        failure_class=failure,
        checkpoint=next_checkpoint,
    )
