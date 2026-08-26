"""Offline, deterministic rehearsal of approved multi-worker governance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from advancore.agent_runner.auto_pipeline import ProviderFailure
from advancore.agent_runner.failover import (
    FailoverError,
    advance_failover_checkpoint,
    start_failover_checkpoint,
)
from advancore.agent_runner.worker import build_worker_adapter
from advancore.agent_runner.worker_registry import WorkerRole, get_worker_profile
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
    WorkerSelectionError,
    select_governed_worker,
)


REHEARSAL_FINGERPRINT = "a" * 64


@dataclass(frozen=True)
class RehearsalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class MultiWorkerRehearsalReport:
    passed: bool
    checks: tuple[RehearsalCheck, ...]
    workers_launched: int = 0
    authority_consumed: bool = False


def _evidence(
    worker: str, state: WorkerAvailability
) -> WorkerAvailabilityEvidence:
    return WorkerAvailabilityEvidence(worker, state)


def _check(name: str, passed: bool, detail: str) -> RehearsalCheck:
    return RehearsalCheck(name=name, passed=bool(passed), detail=detail)


def run_multi_worker_governance_rehearsal(
    *, working_directory: Path | None = None
) -> MultiWorkerRehearsalReport:
    """Exercise routing and failover policy without launching a provider worker."""
    checks: list[RehearsalCheck] = []
    root = Path(working_directory or Path.cwd())

    healthy = (
        _evidence("kimi-swarm", WorkerAvailability.AVAILABLE),
        _evidence("codex", WorkerAvailability.AVAILABLE),
    )
    primary = select_governed_worker(WorkerRole.IMPLEMENTATION, healthy)
    checks.append(
        _check(
            "kimi_primary",
            primary.selected_worker == "kimi-swarm",
            "healthy Kimi-Swarm is selected before Codex",
        )
    )

    paused = select_governed_worker(
        WorkerRole.IMPLEMENTATION,
        (
            _evidence("kimi-swarm", WorkerAvailability.PAUSED),
            _evidence("codex", WorkerAvailability.AVAILABLE),
        ),
    )
    checks.append(
        _check(
            "codex_fallback",
            paused.selected_worker == "codex",
            "explicitly paused Kimi-Swarm selects approved Codex fallback",
        )
    )

    try:
        select_governed_worker(
            WorkerRole.IMPLEMENTATION,
            (_evidence("gemini", WorkerAvailability.AVAILABLE),),
        )
    except WorkerSelectionError:
        route_pending = True
    else:
        route_pending = False
    checks.append(
        _check(
            "gemini_activation_route_separation",
            route_pending and get_worker_profile("gemini").launchable,
            "Gemini is activated but remains outside runtime routing until TASK-099",
        )
    )

    try:
        select_governed_worker(WorkerRole.IMPLEMENTATION, ())
    except WorkerSelectionError:
        missing_blocked = True
    else:
        missing_blocked = False
    checks.append(
        _check(
            "missing_evidence_blocks",
            missing_blocked,
            "missing availability evidence fails closed",
        )
    )

    checkpoint = start_failover_checkpoint(
        run_id="FAILOVER-task085",
        task_id="TASK-085",
        branch="task-085-multi-worker-rehearsal",
        role=WorkerRole.IMPLEMENTATION,
        repository_fingerprint=REHEARSAL_FINGERPRINT,
        evidence=healthy,
    )
    fallback = advance_failover_checkpoint(
        checkpoint,
        failed_worker="kimi-swarm",
        failure=ProviderFailure.QUOTA_OR_CAPACITY,
        repository_fingerprint=REHEARSAL_FINGERPRINT,
        evidence=healthy,
    )
    checks.append(
        _check(
            "eligible_single_failover",
            fallback.selected_worker == "codex"
            and fallback.attempted_workers == ("kimi-swarm",),
            "eligible primary failure advances once to an unattempted Codex",
        )
    )

    try:
        advance_failover_checkpoint(
            checkpoint,
            failed_worker="kimi-swarm",
            failure=ProviderFailure.QUOTA_OR_CAPACITY,
            repository_fingerprint="b" * 64,
            evidence=healthy,
        )
    except FailoverError:
        changed_blocked = True
    else:
        changed_blocked = False
    checks.append(
        _check(
            "changed_repository_blocks",
            changed_blocked,
            "a changed repository fingerprint blocks failover",
        )
    )

    try:
        advance_failover_checkpoint(
            checkpoint,
            failed_worker="kimi-swarm",
            failure=ProviderFailure.UNKNOWN,
            repository_fingerprint=REHEARSAL_FINGERPRINT,
            evidence=healthy,
        )
    except FailoverError:
        unknown_blocked = True
    else:
        unknown_blocked = False
    checks.append(
        _check(
            "unknown_failure_blocks",
            unknown_blocked,
            "an unclassified provider failure requires controller attention",
        )
    )

    try:
        advance_failover_checkpoint(
            fallback,
            failed_worker="codex",
            failure=ProviderFailure.AUTHENTICATION_UNAVAILABLE,
            repository_fingerprint=REHEARSAL_FINGERPRINT,
            evidence=healthy,
        )
    except FailoverError:
        exhausted = True
    else:
        exhausted = False
    checks.append(
        _check(
            "fallback_is_bounded",
            exhausted,
            "a second provider failure stops instead of cycling workers",
        )
    )

    gemini = build_worker_adapter("gemini")
    command = gemini.build_command("offline rehearsal", root)
    checks.append(
        _check(
            "gemini_command_is_bounded",
            command[0] == "agy"
            and "--sandbox" in command
            and "--disable-slash-commands" in command
            and "--dangerously-skip-permissions" not in command,
            "Gemini has a fixed sandboxed command and the rehearsal launches nothing",
        )
    )

    return MultiWorkerRehearsalReport(
        passed=all(item.passed for item in checks),
        checks=tuple(checks),
    )


def format_multi_worker_rehearsal(report: MultiWorkerRehearsalReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        f"Multi-worker governance rehearsal: {status}",
        f"Workers launched: {report.workers_launched}",
        f"Authority consumed: {'yes' if report.authority_consumed else 'no'}",
    ]
    lines.extend(
        f"- {'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}"
        for check in report.checks
    )
    return "\n".join(lines)
