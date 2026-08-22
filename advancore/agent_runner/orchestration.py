"""End-to-end controller orchestration for the local agent runner.

This module provides a deterministic, resumable coordinator that chains the
existing TASK-019 through TASK-020 capabilities from a bounded owner goal to
safe publication of a non-``main`` feature branch.  It advances verified state;
it does not create authority.

The orchestrator delegates all governance-sensitive work to existing modules:

* ``goal_task.generate_goal_task`` — owner-goal to DRAFT task.
* ``lifecycle.transition_task`` / ``decision_lifecycle_bridge.apply_controller_decision`` —
  lifecycle authority.
* ``auto_pipeline.run_auto_pipeline`` — bounded worker execution and repair.
* ``review_bundle``, ``controller_handoff``, ``controller_adapter`` —
  implementation review and controller decision return path.
* ``finalize.run_finalization`` — controller-gated stage/commit/push.

Orchestration checkpoints are bounded, versioned, atomic JSON files stored under
``.agent_runner/orchestration/``.  They are local coordination aids, not source
of truth, and never contain prompts, transcripts, source contents, secrets, or
environment dumps.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from advancore.agent_runner.auto_pipeline import (
    AutoPipelineResult,
    AutoPipelineStatus,
    parse_task_allowed_scope,
    run_auto_pipeline,
)
from advancore.agent_runner.controller_adapter import (
    AdapterResultState,
    ControllerAdapterResult,
    dispatch_controller_adapter,
)
from advancore.agent_runner.controller_decision import (
    DecisionValue,
    default_decisions_dir,
    find_latest_decision,
    load_controller_decision,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoff,
    ControllerHandoffError,
    HandoffState,
    build_controller_handoff,
    default_handoff_dir,
    load_controller_handoff,
    reconcile_controller_handoff,
    write_controller_handoff,
)
from advancore.agent_runner.decision_lifecycle_bridge import (
    apply_controller_decision,
)
from advancore.agent_runner.finalize import (
    FinalizationStatus,
    default_finalize_dir,
    run_finalization,
)
from advancore.agent_runner.git_info import GitInfo, get_git_info
from advancore.agent_runner.goal_task import (
    GoalTaskGenerationStatus,
    default_goal_task_dir,
    generate_goal_task,
    validate_owner_goal,
)
from advancore.agent_runner.lifecycle import (
    ActorRole,
    LifecycleResult,
    TaskStatus,
    transition_task,
)
from advancore.agent_runner.review_bundle import (
    ReviewBundle,
    default_review_dir,
    find_latest_bundle,
    load_review_bundle,
)
from advancore.agent_runner.task import Task, TaskError, find_task
from advancore.agent_runner.worker import (
    DryRunWorkerAdapter,
    KimiSwarmWorkerAdapter,
    KimiWorkerAdapter,
    WorkerAdapter,
    build_worker_adapter,
    validate_worker_policy,
)


# ---------------------------------------------------------------------------
# Bounded constants
# ---------------------------------------------------------------------------

ORCHESTRATION_SCHEMA_VERSION = "advancore-orchestration-v1"
ORCHESTRATION_SUBDIR = "orchestration"
CHECKPOINT_FILENAME = "{run_id}.json"

MAX_GOAL_LENGTH = 2000
MAX_REPAIR_ATTEMPTS = 2
MAX_REWORK_CYCLES = 1


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OrchestrationError(Exception):
    """Raised when the orchestrator cannot proceed safely."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class OrchestrationPhase(str, Enum):
    """Deterministic phases of an orchestration run."""

    GOAL_VALIDATION = "GOAL_VALIDATION"
    TASK_DRAFT_GENERATION = "TASK_DRAFT_GENERATION"
    AWAITING_TASK_APPROVAL = "AWAITING_TASK_APPROVAL"
    TASK_EXECUTION = "TASK_EXECUTION"
    AWAITING_IMPLEMENTATION_DECISION = "AWAITING_IMPLEMENTATION_DECISION"
    FINALIZATION = "FINALIZATION"
    PUBLISHED = "PUBLISHED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class OrchestrationStatus(str, Enum):
    """Terminal or pause statuses reported by the orchestrator."""

    PUBLISHED = "PUBLISHED"
    AWAITING_TASK_APPROVAL = "AWAITING_TASK_APPROVAL"
    AWAITING_IMPLEMENTATION_DECISION = "AWAITING_IMPLEMENTATION_DECISION"
    OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"
    TASK_EXECUTION = "TASK_EXECUTION"
    FINALIZATION = "FINALIZATION"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    REWORK_EXHAUSTED = "REWORK_EXHAUSTED"
    NON_REPAIRABLE = "NON_REPAIRABLE"
    REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass
class OrchestrationConfig:
    """Bounded configuration for one orchestration run."""

    goal: str | None = None
    resume_run_id: str | None = None
    planner: str = "dry-run"
    worker: str = "dry-run"
    fallback_worker: str | None = None
    controller: str = "manual"
    repair_attempts: int = 0
    max_rework: int = 0
    apply: bool = False

    def __post_init__(self):
        """Clamp budgets to approved bounds."""
        if self.repair_attempts < 0:
            object.__setattr__(self, "repair_attempts", 0)
        elif self.repair_attempts > MAX_REPAIR_ATTEMPTS:
            object.__setattr__(self, "repair_attempts", MAX_REPAIR_ATTEMPTS)

        if self.max_rework < 0:
            object.__setattr__(self, "max_rework", 0)
        elif self.max_rework > MAX_REWORK_CYCLES:
            object.__setattr__(self, "max_rework", MAX_REWORK_CYCLES)
        try:
            validate_worker_policy(self.worker, self.fallback_worker)
        except Exception as exc:
            raise OrchestrationError(str(exc)) from exc


@dataclass
class OrchestrationCheckpoint:
    """Durable, bounded orchestration state."""

    schema_version: str
    run_id: str
    goal_hash: str
    goal_summary: str
    planner: str
    worker: str
    controller: str
    repair_attempts: int
    max_rework: int
    apply: bool
    phase: str
    fallback_worker: str | None = None
    completed_phases: list[str] = field(default_factory=list)
    status: str = OrchestrationStatus.AWAITING_TASK_APPROVAL.value
    branch: str | None = None
    expected_head: str | None = None
    path_fingerprint: list[str] = field(default_factory=list)
    task_id: str | None = None
    task_path: str | None = None
    task_written: bool = False
    owner_decision_count: int = 0
    goal_task_artifact_path: str | None = None
    review_bundle_path: str | None = None
    handoff_path: str | None = None
    handoff_request_id: str | None = None
    decision_path: str | None = None
    decision: str | None = None
    auto_artifact_path: str | None = None
    auto_status: str | None = None
    finalization_artifact_path: str | None = None
    commit_sha: str | None = None
    push_verified: bool = False
    rework_cycles_used: int = 0
    repair_attempts_used: int = 0
    consumed_decision_paths: list[str] = field(default_factory=list)
    mutations: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class OrchestrationResult:
    """Consolidated, machine-readable-enough orchestration result."""

    ok: bool
    run_id: str
    task_id: str | None
    task_path: str | None
    phase: str
    status: str
    completed_phases: list[str]
    branch: str | None
    head: str | None
    evidence_paths: dict[str, str | None]
    controller_gate: str | None
    mutations_performed: list[str]
    blocking_reason: str | None
    owner_decision_required: bool
    next_action: str
    resume_command: str
    messages: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_goal(text: str) -> str:
    """Return a deterministic short hash of *text* for correlation."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _short_summary(text: str, max_length: int = 120) -> str:
    """Return a bounded short summary of *text*."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


def _extract_changed_paths(status_lines: list[str]) -> list[str]:
    """Return repository-relative changed paths from porcelain status lines."""
    paths: list[str] = []
    for line in status_lines:
        if "->" in line:
            paths.append(line.split("->")[-1].strip())
        elif len(line) > 3:
            paths.append(line[3:].strip())
        elif line.strip():
            paths.append(line.strip())
    return paths


def _repo_fingerprint(repo_root: Path) -> dict[str, Any]:
    """Return a deterministic snapshot of repository state."""
    git_info = get_git_info(cwd=repo_root)
    return {
        "branch": git_info.current_branch,
        "head": git_info.head_sha,
        "status_lines": git_info.status_lines,
        "changed_paths": sorted(_extract_changed_paths(git_info.status_lines)),
    }


def _build_planner(name: str) -> WorkerAdapter:
    """Return a planner worker adapter by name."""
    if name == "kimi":
        return KimiWorkerAdapter()
    if name == "kimi-swarm":
        return KimiSwarmWorkerAdapter()
    return DryRunWorkerAdapter()


def _build_worker(name: str, allowed_scope: list[str] | None = None) -> WorkerAdapter:
    """Return an implementation worker adapter by name."""
    return build_worker_adapter(name, allowed_scope=allowed_scope)


def _count_owner_decisions(task_path: Path) -> int:
    """Count unresolved owner decisions declared in a task file."""
    text = task_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("## owner decisions"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("##"):
                break
            if stripped.startswith("-"):
                item = stripped[1:].strip()
                if item and item.lower() != "none.":
                    count += 1
    return count


def _map_auto_status(status: AutoPipelineStatus) -> OrchestrationStatus:
    """Map an auto-pipeline terminal status to an orchestration status."""
    mapping = {
        AutoPipelineStatus.REPAIR_EXHAUSTED: OrchestrationStatus.REPAIR_EXHAUSTED,
        AutoPipelineStatus.NON_REPAIRABLE: OrchestrationStatus.NON_REPAIRABLE,
    }
    return mapping.get(status, OrchestrationStatus.FAILED)


def _map_finalize_status(status: FinalizationStatus) -> OrchestrationStatus:
    """Map a finalization terminal status to an orchestration status."""
    mapping = {
        FinalizationStatus.STALE_EVIDENCE: OrchestrationStatus.STALE_EVIDENCE,
        FinalizationStatus.DECISION_REJECTED: OrchestrationStatus.BLOCKED,
        FinalizationStatus.PUBLICATION_FAILED: OrchestrationStatus.BLOCKED,
    }
    return mapping.get(status, OrchestrationStatus.BLOCKED)


def _resume_command(run_id: str, apply: bool = True) -> str:
    """Return the exact resume command for *run_id*."""
    flag = " --apply" if apply else ""
    return (
        f".venv/bin/python -m advancore.agent_runner orchestrate "
        f"--resume {run_id}{flag}"
    )


# ---------------------------------------------------------------------------
# Checkpoint persistence
# ---------------------------------------------------------------------------


def default_orchestration_dir(repo_root: Path) -> Path:
    """Return the default orchestration checkpoint directory."""
    return repo_root / ".agent_runner" / ORCHESTRATION_SUBDIR


def _checkpoint_path(run_id: str, repo_root: Path) -> Path:
    """Return the checkpoint file path for *run_id*."""
    return default_orchestration_dir(repo_root) / CHECKPOINT_FILENAME.format(run_id=run_id)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write *payload* to *path* using write-then-replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.tmp-",
        suffix=".json",
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, default=str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def save_checkpoint(checkpoint: OrchestrationCheckpoint, repo_root: Path) -> Path:
    """Persist *checkpoint* atomically and return its path."""
    checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
    path = _checkpoint_path(checkpoint.run_id, repo_root)
    payload = asdict(checkpoint)
    _atomic_write_json(path, payload)
    return path


def load_checkpoint(run_id: str, repo_root: Path) -> OrchestrationCheckpoint:
    """Load and validate the checkpoint for *run_id*."""
    path = _checkpoint_path(run_id, repo_root)
    if not path.exists():
        raise OrchestrationError(f"Checkpoint not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OrchestrationError(f"Cannot read checkpoint {path}: {exc}") from exc

    if data.get("schema_version") != ORCHESTRATION_SCHEMA_VERSION:
        raise OrchestrationError(
            f"Unsupported checkpoint schema: {data.get('schema_version')!r} "
            f"(expected {ORCHESTRATION_SCHEMA_VERSION!r})"
        )

    try:
        return OrchestrationCheckpoint(**data)
    except Exception as exc:
        raise OrchestrationError(f"Invalid checkpoint format: {exc}") from exc


def _new_checkpoint(config: OrchestrationConfig, repo_root: Path) -> OrchestrationCheckpoint:
    """Create a fresh checkpoint from *config*."""
    git_info = get_git_info(cwd=repo_root)
    fp = _repo_fingerprint(repo_root)
    goal = config.goal or ""
    return OrchestrationCheckpoint(
        schema_version=ORCHESTRATION_SCHEMA_VERSION,
        run_id=f"ORCH-{uuid.uuid4().hex}",
        goal_hash=_hash_goal(goal),
        goal_summary=_short_summary(goal),
        planner=config.planner,
        worker=config.worker,
        fallback_worker=config.fallback_worker,
        controller=config.controller,
        repair_attempts=config.repair_attempts,
        max_rework=config.max_rework,
        apply=config.apply,
        phase=OrchestrationPhase.GOAL_VALIDATION.value,
        completed_phases=[],
        status=OrchestrationStatus.AWAITING_TASK_APPROVAL.value,
        branch=git_info.current_branch,
        expected_head=git_info.head_sha,
        path_fingerprint=fp["changed_paths"],
        mutations=[],
        messages=["Checkpoint created"],
    )


# ---------------------------------------------------------------------------
# Result building
# ---------------------------------------------------------------------------


def _build_result(
    checkpoint: OrchestrationCheckpoint,
    *,
    ok: bool,
    status: OrchestrationStatus,
    blocking_reason: str | None = None,
    owner_decision_required: bool = False,
    next_action: str | None = None,
    messages: list[str] | None = None,
) -> OrchestrationResult:
    """Build a consolidated result from *checkpoint*."""
    git_info = get_git_info(cwd=_repo_root_from_checkpoint(checkpoint))
    evidence_paths = {
        "goal_task_artifact": checkpoint.goal_task_artifact_path,
        "review_bundle": checkpoint.review_bundle_path,
        "handoff": checkpoint.handoff_path,
        "decision": checkpoint.decision_path,
        "auto_artifact": checkpoint.auto_artifact_path,
        "finalization_artifact": checkpoint.finalization_artifact_path,
        "checkpoint": str(_checkpoint_path(checkpoint.run_id, git_info.repo_root)),
    }
    if next_action is None:
        next_action = _default_next_action(checkpoint, status)
    return OrchestrationResult(
        ok=ok,
        run_id=checkpoint.run_id,
        task_id=checkpoint.task_id,
        task_path=checkpoint.task_path,
        phase=checkpoint.phase,
        status=status.value,
        completed_phases=list(checkpoint.completed_phases),
        branch=git_info.current_branch,
        head=git_info.head_sha,
        evidence_paths=evidence_paths,
        controller_gate=checkpoint.decision,
        mutations_performed=list(checkpoint.mutations),
        blocking_reason=blocking_reason,
        owner_decision_required=owner_decision_required,
        next_action=next_action,
        resume_command=_resume_command(checkpoint.run_id),
        messages=messages or list(checkpoint.messages),
    )


def _repo_root_from_checkpoint(checkpoint: OrchestrationCheckpoint) -> Path:
    """Return the repository root implied by the checkpoint task path."""
    if checkpoint.task_path:
        task_path = Path(checkpoint.task_path)
        if task_path.is_absolute():
            return task_path.parent.parent
    # Fall back to current working directory.
    return Path.cwd()


def _default_next_action(
    checkpoint: OrchestrationCheckpoint, status: OrchestrationStatus
) -> str:
    """Return a precise next action for *status*."""
    if status == OrchestrationStatus.PUBLISHED:
        return "No further action required."
    if status == OrchestrationStatus.AWAITING_TASK_APPROVAL:
        return (
            f"Review the generated task ({checkpoint.task_id}) and apply a valid "
            "controller/owner DRAFT -> READY transition, then resume."
        )
    if status == OrchestrationStatus.OWNER_DECISION_REQUIRED:
        return (
            f"Resolve owner decisions in {checkpoint.task_id} and apply a valid "
            "controller/owner DRAFT -> READY transition, then resume."
        )
    if status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION:
        return (
            f"Record a controller decision for {checkpoint.task_id} against the "
            "review bundle/handoff, then resume."
        )
    if status == OrchestrationStatus.REWORK_REQUIRED:
        return "A REWORK decision was applied; re-running task execution."
    if status == OrchestrationStatus.REWORK_EXHAUSTED:
        return "Rework budget exhausted; controller/owner intervention required."
    if status == OrchestrationStatus.REPAIR_EXHAUSTED:
        return "Autonomous repair budget exhausted; controller/owner review required."
    if status == OrchestrationStatus.NON_REPAIRABLE:
        return "Non-repairable failure; controller/owner review required."
    if status == OrchestrationStatus.STALE_EVIDENCE:
        return "Repository evidence is stale; inspect and start a new run if needed."
    return "Orchestration blocked; inspect messages and resume or start a new run."


# ---------------------------------------------------------------------------
# Freshness / stale-evidence guards
# ---------------------------------------------------------------------------


def _check_branch_head(checkpoint: OrchestrationCheckpoint, repo_root: Path) -> None:
    """Fail closed if branch/HEAD do not match checkpoint expectations."""
    git_info = get_git_info(cwd=repo_root)
    if checkpoint.branch and git_info.current_branch != checkpoint.branch:
        raise OrchestrationError(
            f"Branch mismatch: current={git_info.current_branch!r}, "
            f"checkpoint={checkpoint.branch!r}"
        )
    if checkpoint.expected_head and git_info.head_sha != checkpoint.expected_head:
        raise OrchestrationError(
            f"HEAD mismatch: current={git_info.head_sha!r}, "
            f"checkpoint={checkpoint.expected_head!r}"
        )


def _check_freshness(checkpoint: OrchestrationCheckpoint, repo_root: Path) -> None:
    """Fail closed if repository state does not match checkpoint expectations.

    Called before finalization where the exact approved changed-path set is
    security-critical.  A checkpoint reference alone is never proof of authority.
    """
    _check_branch_head(checkpoint, repo_root)
    fp = _repo_fingerprint(repo_root)
    if checkpoint.path_fingerprint and fp["changed_paths"] != checkpoint.path_fingerprint:
        raise OrchestrationError(
            f"Changed-path fingerprint mismatch: current={fp['changed_paths']}, "
            f"checkpoint={checkpoint.path_fingerprint}"
        )


def _update_branch_head(checkpoint: OrchestrationCheckpoint, repo_root: Path) -> None:
    """Capture current branch/HEAD into *checkpoint*."""
    git_info = get_git_info(cwd=repo_root)
    checkpoint.branch = git_info.current_branch
    checkpoint.expected_head = git_info.head_sha


def _update_fingerprint(checkpoint: OrchestrationCheckpoint, repo_root: Path) -> None:
    """Capture current repository fingerprint into *checkpoint*."""
    fp = _repo_fingerprint(repo_root)
    checkpoint.branch = fp["branch"]
    checkpoint.expected_head = fp["head"]
    checkpoint.path_fingerprint = fp["changed_paths"]


# ---------------------------------------------------------------------------
# Phase handlers
# ---------------------------------------------------------------------------


def _phase_goal_validation(
    config: OrchestrationConfig,
    checkpoint: OrchestrationCheckpoint,
    repo_root: Path,
) -> OrchestrationResult | None:
    """Validate the owner goal and advance to task draft generation."""
    if OrchestrationPhase.GOAL_VALIDATION.value in checkpoint.completed_phases:
        checkpoint.phase = OrchestrationPhase.TASK_DRAFT_GENERATION.value
        return None

    goal = config.goal or ""
    owner_goal = validate_owner_goal(goal)
    if not owner_goal.accepted:
        reason = next(
            (m for m in owner_goal.messages if m.startswith("FAIL")),
            "Goal validation failed",
        )
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason=reason,
            messages=owner_goal.messages,
        )

    checkpoint.goal_hash = _hash_goal(owner_goal.normalized)
    checkpoint.goal_summary = _short_summary(owner_goal.normalized)
    checkpoint.completed_phases.append(OrchestrationPhase.GOAL_VALIDATION.value)
    checkpoint.phase = OrchestrationPhase.TASK_DRAFT_GENERATION.value
    checkpoint.messages.append("PASS: owner goal accepted")
    if config.apply:
        save_checkpoint(checkpoint, repo_root)
    return None


def _phase_task_draft_generation(
    config: OrchestrationConfig,
    checkpoint: OrchestrationCheckpoint,
    repo_root: Path,
    tasks_dir: Path,
) -> OrchestrationResult | None:
    """Generate or preview the DRAFT task and bind it to the checkpoint."""
    if checkpoint.task_id is not None and checkpoint.task_written:
        # Idempotent: already generated.
        checkpoint.phase = OrchestrationPhase.AWAITING_TASK_APPROVAL.value
        return None

    goal = config.goal or ""
    planner = _build_planner(config.planner)
    gen_result = generate_goal_task(
        repo_root=repo_root,
        tasks_dir=tasks_dir,
        goal=goal,
        planner=planner,
        execute=config.apply,
    )

    checkpoint.goal_task_artifact_path = (
        str(gen_result.artifact_path) if gen_result.artifact_path else None
    )
    checkpoint.task_id = gen_result.task_id
    checkpoint.task_path = str(gen_result.task_path) if gen_result.task_path else None
    checkpoint.task_written = gen_result.task_written
    checkpoint.owner_decision_count = gen_result.owner_decision_count

    if not config.apply:
        # Preview stops here without writing a checkpoint.
        status = (
            OrchestrationStatus.AWAITING_TASK_APPROVAL
            if gen_result.owner_decision_count == 0
            else OrchestrationStatus.OWNER_DECISION_REQUIRED
        )
        preview_messages = [
            "Preview: goal-task generation would create a DRAFT task.",
            f"Preview: candidate task ID {gen_result.task_id or 'n/a'}",
            "Preview: no checkpoint, task file, or artifact will be written without --apply.",
        ]
        return _build_result(
            checkpoint,
            ok=True,
            status=status,
            owner_decision_required=gen_result.owner_decision_count > 0,
            messages=preview_messages,
        )

    if gen_result.status != GoalTaskGenerationStatus.DRAFT_CREATED:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason=f"Goal-task generation failed: {gen_result.status.value}",
            messages=gen_result.messages,
        )

    _update_fingerprint(checkpoint, repo_root)
    checkpoint.completed_phases.append(OrchestrationPhase.TASK_DRAFT_GENERATION.value)
    checkpoint.phase = OrchestrationPhase.AWAITING_TASK_APPROVAL.value
    checkpoint.status = (
        OrchestrationStatus.OWNER_DECISION_REQUIRED.value
        if gen_result.owner_decision_count > 0
        else OrchestrationStatus.AWAITING_TASK_APPROVAL.value
    )
    checkpoint.messages.append(
        f"PASS: generated DRAFT task {gen_result.task_id} at {gen_result.task_path.name}"
    )
    save_checkpoint(checkpoint, repo_root)
    return None


def _phase_awaiting_task_approval(
    config: OrchestrationConfig,
    checkpoint: OrchestrationCheckpoint,
    repo_root: Path,
    tasks_dir: Path,
) -> OrchestrationResult | None:
    """Pause until a valid controller/owner DRAFT -> READY transition exists."""
    if checkpoint.task_id is None:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason="No task assigned to checkpoint",
        )

    try:
        task = find_task(tasks_dir, checkpoint.task_id)
    except TaskError as exc:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason=f"Cannot load task: {exc}",
        )

    # Worker output or generation success is never authority.
    if task.status.upper() == TaskStatus.READY.value:
        _update_branch_head(checkpoint, repo_root)
        checkpoint.completed_phases.append(
            OrchestrationPhase.AWAITING_TASK_APPROVAL.value
        )
        checkpoint.phase = OrchestrationPhase.TASK_EXECUTION.value
        checkpoint.status = OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
        checkpoint.messages.append(
            f"PASS: task {task.task_id} is READY; controller/owner authority verified"
        )
        if config.apply:
            save_checkpoint(checkpoint, repo_root)
        return None

    if task.status.upper() != TaskStatus.DRAFT.value:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.BLOCKED,
            blocking_reason=f"Unexpected task status: {task.status}",
        )

    # Re-evaluate owner decisions from the authoritative task file.
    owner_decision_count = _count_owner_decisions(task.path)
    checkpoint.owner_decision_count = owner_decision_count

    if owner_decision_count > 0:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.OWNER_DECISION_REQUIRED,
            owner_decision_required=True,
            messages=[
                f"Task {task.task_id} has {owner_decision_count} unresolved owner decision(s).",
                "Resolve owner decisions and apply a valid controller/owner DRAFT -> READY transition, then resume.",
            ],
        )

    return _build_result(
        checkpoint,
        ok=False,
        status=OrchestrationStatus.AWAITING_TASK_APPROVAL,
        messages=[
            f"Task {task.task_id} is DRAFT and awaits controller/owner approval.",
            "Apply a valid DRAFT -> READY transition through existing lifecycle authority, then resume.",
        ],
    )


def _phase_task_execution(
    config: OrchestrationConfig,
    checkpoint: OrchestrationCheckpoint,
    repo_root: Path,
    tasks_dir: Path,
) -> OrchestrationResult | None:
    """Run the auto-pipeline for a READY task."""
    if checkpoint.task_id is None:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason="No task assigned to checkpoint",
        )

    # Idempotency: if we already recorded a successful READY_FOR_APPROVAL run,
    # do not re-invoke the worker.
    if checkpoint.auto_status == AutoPipelineStatus.READY_FOR_APPROVAL.value:
        checkpoint.phase = OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value
        return None

    try:
        task = find_task(tasks_dir, checkpoint.task_id)
    except TaskError as exc:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason=f"Cannot load task: {exc}",
        )

    if task.status.upper() not in {TaskStatus.READY.value, TaskStatus.REWORK.value}:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.BLOCKED,
            blocking_reason=f"Task status {task.status!r} is not executable",
        )

    allowed_scope = parse_task_allowed_scope(task.path) or []
    worker = _build_worker(config.worker, allowed_scope=allowed_scope)
    fallback_worker = (
        _build_worker(config.fallback_worker, allowed_scope=allowed_scope)
        if config.fallback_worker else None
    )

    if not config.apply:
        return _build_result(
            checkpoint,
            ok=True,
            status=OrchestrationStatus.TASK_EXECUTION,
            messages=[
                f"Preview: would run auto-pipeline for {task.task_id} with worker {config.worker}",
                f"Preview: repair-attempts={config.repair_attempts}, max-rework={config.max_rework}",
            ],
        )

    try:
        _check_branch_head(checkpoint, repo_root)
    except OrchestrationError as exc:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.STALE_EVIDENCE,
            blocking_reason=str(exc),
        )

    auto_result = run_auto_pipeline(
        tasks_dir,
        checkpoint.task_id,
        worker=worker,
        fallback_worker=fallback_worker,
        max_repair_attempts=config.repair_attempts,
    )

    checkpoint.auto_artifact_path = (
        str(auto_result.auto_artifact_path) if auto_result.auto_artifact_path else None
    )
    checkpoint.auto_status = auto_result.status.value
    checkpoint.review_bundle_path = (
        str(auto_result.review_bundle_path) if auto_result.review_bundle_path else None
    )
    checkpoint.repair_attempts_used = len(auto_result.repair_attempts)
    checkpoint.messages.extend(auto_result.messages)

    if auto_result.status == AutoPipelineStatus.READY_FOR_APPROVAL:
        _update_fingerprint(checkpoint, repo_root)
        checkpoint.completed_phases.append(OrchestrationPhase.TASK_EXECUTION.value)
        checkpoint.phase = OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value
        checkpoint.status = OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
        checkpoint.messages.append(
            "PASS: auto-pipeline completed; awaiting controller implementation decision"
        )
        save_checkpoint(checkpoint, repo_root)
        return None

    status = _map_auto_status(auto_result.status)
    return _build_result(
        checkpoint,
        ok=False,
        status=status,
        blocking_reason=f"Auto-pipeline terminal status: {auto_result.status.value}",
    )


def _find_latest_bundle_for_task(repo_root: Path, task_id: str) -> Path | None:
    """Return the latest review bundle that links to *task_id*."""
    review_dir = default_review_dir(repo_root)
    if not review_dir.exists():
        return None
    candidates = sorted(review_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            bundle = load_review_bundle(candidate)
        except Exception:
            continue
        if bundle.task_id == task_id:
            return candidate
    return None


def _find_matching_decision(
    repo_root: Path, task_id: str, consumed_paths: set[str] | None = None
) -> Path | None:
    """Return the latest unconsumed decision record for *task_id*, or None."""
    decisions_dir = default_decisions_dir(repo_root)
    consumed = consumed_paths or set()
    if not decisions_dir.exists():
        return None
    candidates = sorted(
        decisions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for candidate in candidates:
        if str(candidate.resolve()) in consumed:
            continue
        try:
            decision = load_controller_decision(candidate)
        except Exception:
            continue
        if decision.task_id == task_id:
            return candidate
    return None


def _phase_awaiting_implementation_decision(
    config: OrchestrationConfig,
    checkpoint: OrchestrationCheckpoint,
    repo_root: Path,
    tasks_dir: Path,
) -> OrchestrationResult | None:
    """Create/reuse review handoff and dispatch controller adapter."""
    if checkpoint.task_id is None:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason="No task assigned to checkpoint",
        )

    if not config.apply:
        return _build_result(
            checkpoint,
            ok=True,
            status=OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION,
            messages=[
                "Preview: would create or reuse the review handoff and dispatch "
                f"controller adapter {checkpoint.controller!r}.",
                "Preview: no handoff, transport, decision, or checkpoint will be written.",
            ],
        )

    # Ensure a handoff exists for the review bundle.
    handoff_path: Path | None = None
    if checkpoint.handoff_path:
        handoff_path = Path(checkpoint.handoff_path)
    else:
        bundle_path = (
            Path(checkpoint.review_bundle_path)
            if checkpoint.review_bundle_path
            else _find_latest_bundle_for_task(repo_root, checkpoint.task_id)
        )
        if bundle_path is None:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
                blocking_reason="No review bundle found for implementation decision",
            )

        try:
            bundle = load_review_bundle(bundle_path)
        except Exception as exc:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
                blocking_reason=f"Cannot load review bundle: {exc}",
            )

        git_info = get_git_info(cwd=repo_root)
        try:
            handoff = build_controller_handoff(
                bundle_path, bundle, git_info=git_info, repo_root=repo_root
            )
        except ControllerHandoffError as exc:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
                blocking_reason=f"Cannot build handoff: {exc}",
            )

        handoff_path = write_controller_handoff(handoff, default_handoff_dir(repo_root))
        checkpoint.handoff_path = str(handoff_path)
        checkpoint.handoff_request_id = handoff.request_id
        checkpoint.messages.append(f"Handoff written to {handoff_path.name}")
        if config.apply:
            save_checkpoint(checkpoint, repo_root)

    try:
        _check_branch_head(checkpoint, repo_root)
    except OrchestrationError as exc:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.STALE_EVIDENCE,
            blocking_reason=str(exc),
        )

    # In apply mode, look for a matching decision and reconcile if found.
    decision_path = _find_matching_decision(
        repo_root, checkpoint.task_id, set(checkpoint.consumed_decision_paths)
    )
    if decision_path is not None and handoff_path is not None:
        try:
            reconcile_controller_handoff(
                request_path=handoff_path,
                decision_path=decision_path,
                repo_root=repo_root,
                git_info=get_git_info(cwd=repo_root),
            )
            checkpoint.messages.append(
                f"Reconciled handoff with decision {decision_path.name}"
            )
        except Exception as exc:
            checkpoint.messages.append(
                f"WARNING: could not reconcile decision: {exc}"
            )

    # Dispatch the selected controller adapter.
    adapter_result = dispatch_controller_adapter(
        handoff_target=handoff_path,
        adapter=config.controller,
        repo_root=repo_root,
        git_info=get_git_info(cwd=repo_root),
    )

    if adapter_result.state == AdapterResultState.PENDING.value:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION,
            messages=[
                "No separately valid controller decision is available.",
                f"Record a decision for task {checkpoint.task_id} and resume.",
            ],
        )

    if adapter_result.state == AdapterResultState.BLOCKED.value:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.BLOCKED,
            blocking_reason="Controller adapter returned BLOCKED",
            messages=adapter_result.messages,
        )

    if adapter_result.state != AdapterResultState.DECISION_RECEIVED.value:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.BLOCKED,
            blocking_reason=f"Unknown adapter state: {adapter_result.state!r}",
        )

    decision = adapter_result.decision
    checkpoint.decision = decision
    checkpoint.decision_path = adapter_result.decision_path
    save_checkpoint(checkpoint, repo_root)

    if decision == DecisionValue.APPROVE.value:
        _update_fingerprint(checkpoint, repo_root)
        checkpoint.completed_phases.append(
            OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value
        )
        checkpoint.phase = OrchestrationPhase.FINALIZATION.value
        checkpoint.status = OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
        checkpoint.messages.append(
            f"PASS: controller APPROVE received; proceeding to finalization"
        )
        save_checkpoint(checkpoint, repo_root)
        return None

    if decision == DecisionValue.REWORK.value:
        if checkpoint.rework_cycles_used >= config.max_rework:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.REWORK_EXHAUSTED,
                blocking_reason=f"Rework budget exhausted ({config.max_rework} cycle(s))",
            )

        # Auto-pipeline verification is evidence, not lifecycle authority.  Move
        # the worker-owned states in order before applying the separately
        # recorded controller decision through the existing bridge:
        # READY/REWORK -> IN_PROGRESS -> REVIEW -> REWORK.
        try:
            current_task = find_task(tasks_dir, checkpoint.task_id)
        except TaskError as exc:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
                blocking_reason=f"Cannot load task for REWORK lifecycle: {exc}",
            )

        if current_task.status.upper() in {
            TaskStatus.READY.value,
            TaskStatus.REWORK.value,
        }:
            lifecycle_result = transition_task(
                tasks_dir,
                checkpoint.task_id,
                TaskStatus.IN_PROGRESS,
                ActorRole.WORKER,
                apply=True,
                git_info=get_git_info(cwd=repo_root),
            )
            if not lifecycle_result.applied:
                return _build_result(
                    checkpoint,
                    ok=False,
                    status=OrchestrationStatus.BLOCKED,
                    blocking_reason=(
                        "Worker lifecycle transition to IN_PROGRESS could not be applied"
                    ),
                    messages=lifecycle_result.messages,
                )
            current_task = find_task(tasks_dir, checkpoint.task_id)

        if current_task.status.upper() == TaskStatus.IN_PROGRESS.value:
            lifecycle_result = transition_task(
                tasks_dir,
                checkpoint.task_id,
                TaskStatus.REVIEW,
                ActorRole.WORKER,
                apply=True,
                git_info=get_git_info(cwd=repo_root),
            )
            if not lifecycle_result.applied:
                return _build_result(
                    checkpoint,
                    ok=False,
                    status=OrchestrationStatus.BLOCKED,
                    blocking_reason=(
                        "Worker lifecycle transition to REVIEW could not be applied"
                    ),
                    messages=lifecycle_result.messages,
                )
            current_task = find_task(tasks_dir, checkpoint.task_id)

        if current_task.status.upper() != TaskStatus.REVIEW.value:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
                blocking_reason=(
                    f"Task must be REVIEW before controller REWORK; found "
                    f"{current_task.status!r}"
                ),
            )

        if not checkpoint.decision_path:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
                blocking_reason="Controller REWORK decision path is missing",
            )

        resolved_decision_path = Path(checkpoint.decision_path)
        if not resolved_decision_path.is_absolute():
            resolved_decision_path = repo_root / resolved_decision_path
        bridge_result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=resolved_decision_path,
            apply=True,
            git_info=get_git_info(cwd=repo_root),
        )
        if not bridge_result.ok or not bridge_result.applied:
            return _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
                blocking_reason="Controller REWORK decision could not be applied",
                messages=bridge_result.messages,
            )

        if checkpoint.decision_path:
            consumed_path = Path(checkpoint.decision_path)
            if not consumed_path.is_absolute():
                consumed_path = repo_root / consumed_path
            checkpoint.consumed_decision_paths.append(str(consumed_path.resolve()))
        checkpoint.rework_cycles_used += 1
        # Clear execution evidence so the next loop re-runs the pipeline.
        checkpoint.auto_status = None
        checkpoint.auto_artifact_path = None
        checkpoint.review_bundle_path = None
        checkpoint.handoff_path = None
        checkpoint.handoff_request_id = None
        checkpoint.decision = None
        checkpoint.decision_path = None
        if OrchestrationPhase.TASK_EXECUTION.value in checkpoint.completed_phases:
            checkpoint.completed_phases.remove(
                OrchestrationPhase.TASK_EXECUTION.value
            )
        checkpoint.phase = OrchestrationPhase.TASK_EXECUTION.value
        checkpoint.status = OrchestrationStatus.REWORK_REQUIRED.value
        checkpoint.messages.append(
            f"REWORK applied (cycle {checkpoint.rework_cycles_used} of {config.max_rework}); re-running execution"
        )
        save_checkpoint(checkpoint, repo_root)
        return None

    # BLOCKED decision or any other non-APPROVE value.
    return _build_result(
        checkpoint,
        ok=False,
        status=OrchestrationStatus.BLOCKED,
        blocking_reason=f"Controller decision is {decision}; publication blocked",
    )


def _phase_finalization(
    config: OrchestrationConfig,
    checkpoint: OrchestrationCheckpoint,
    repo_root: Path,
    tasks_dir: Path,
) -> OrchestrationResult | None:
    """Delegate publication to TASK-020 finalization."""
    if checkpoint.push_verified:
        checkpoint.phase = OrchestrationPhase.PUBLISHED.value
        checkpoint.status = OrchestrationStatus.PUBLISHED.value
        checkpoint.completed_phases.append(OrchestrationPhase.FINALIZATION.value)
        save_checkpoint(checkpoint, repo_root)
        return None

    if checkpoint.task_id is None:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.FAILED,
            blocking_reason="No task assigned to checkpoint",
        )

    decision_target = checkpoint.decision_path or "latest"

    if not config.apply:
        return _build_result(
            checkpoint,
            ok=True,
            status=OrchestrationStatus.FINALIZATION,
            messages=[
                f"Preview: would run finalization for {checkpoint.task_id} with decision {decision_target}",
                "Preview: use --apply to execute lifecycle, stage, commit, and push.",
            ],
        )

    try:
        _check_freshness(checkpoint, repo_root)
    except OrchestrationError as exc:
        return _build_result(
            checkpoint,
            ok=False,
            status=OrchestrationStatus.STALE_EVIDENCE,
            blocking_reason=str(exc),
        )

    finalize_result = run_finalization(
        repo_root=repo_root,
        tasks_dir=tasks_dir,
        task_id=checkpoint.task_id,
        decision_path=decision_target,
        apply=True,
    )

    checkpoint.finalization_artifact_path = str(default_finalize_dir(repo_root))
    checkpoint.commit_sha = finalize_result.commit_sha
    checkpoint.messages.extend(finalize_result.messages)

    if finalize_result.status == FinalizationStatus.PUSHED:
        _update_fingerprint(checkpoint, repo_root)
        checkpoint.push_verified = True
        checkpoint.completed_phases.append(OrchestrationPhase.FINALIZATION.value)
        checkpoint.phase = OrchestrationPhase.PUBLISHED.value
        checkpoint.status = OrchestrationStatus.PUBLISHED.value
        checkpoint.mutations.append("finalization: staged, committed, pushed")
        save_checkpoint(checkpoint, repo_root)
        return None

    status = _map_finalize_status(finalize_result.status)
    return _build_result(
        checkpoint,
        ok=False,
        status=status,
        blocking_reason=f"Finalization failed: {finalize_result.status.value}",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _setup_checkpoint(
    config: OrchestrationConfig, repo_root: Path
) -> OrchestrationCheckpoint:
    """Load or create a checkpoint and validate resume invariants."""
    if config.resume_run_id:
        checkpoint = load_checkpoint(config.resume_run_id, repo_root)
        if config.goal is not None:
            raise OrchestrationError(
                "Cannot specify --goal with --resume"
            )
        # Ensure the loaded run was created with apply semantics if resuming
        # in apply mode; preview resumes are allowed for inspection.
        return checkpoint

    if not config.goal:
        raise OrchestrationError("--goal is required for a new run")

    return _new_checkpoint(config, repo_root)


def run_orchestration(
    config: OrchestrationConfig,
    repo_root: Path,
) -> OrchestrationResult:
    """Run one governed orchestration from goal to publication.

    The orchestrator advances verified state; it does not create authority.
    All lifecycle, controller, and publication authority remains in the
    existing dedicated modules.
    """
    tasks_dir = repo_root / "tasks"

    try:
        checkpoint = _setup_checkpoint(config, repo_root)
    except OrchestrationError as exc:
        raise

    if config.resume_run_id:
        # Resume uses the provider selections and bounded budgets recorded by
        # the authoritative checkpoint.  CLI defaults must not silently change
        # planner, worker, controller, repair, or rework behavior mid-run.
        config = OrchestrationConfig(
            goal=None,
            resume_run_id=config.resume_run_id,
            planner=checkpoint.planner,
            worker=checkpoint.worker,
            fallback_worker=checkpoint.fallback_worker,
            controller=checkpoint.controller,
            repair_attempts=checkpoint.repair_attempts,
            max_rework=checkpoint.max_rework,
            apply=config.apply,
        )

    # New runs in preview mode do not persist a checkpoint.
    if not config.resume_run_id and not config.apply:
        pass

    max_iterations = 10
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        phase = checkpoint.phase

        if phase == OrchestrationPhase.GOAL_VALIDATION.value:
            result = _phase_goal_validation(config, checkpoint, repo_root)
        elif phase == OrchestrationPhase.TASK_DRAFT_GENERATION.value:
            result = _phase_task_draft_generation(
                config, checkpoint, repo_root, tasks_dir
            )
        elif phase == OrchestrationPhase.AWAITING_TASK_APPROVAL.value:
            result = _phase_awaiting_task_approval(
                config, checkpoint, repo_root, tasks_dir
            )
        elif phase == OrchestrationPhase.TASK_EXECUTION.value:
            result = _phase_task_execution(
                config, checkpoint, repo_root, tasks_dir
            )
        elif phase == OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value:
            result = _phase_awaiting_implementation_decision(
                config, checkpoint, repo_root, tasks_dir
            )
        elif phase == OrchestrationPhase.FINALIZATION.value:
            result = _phase_finalization(config, checkpoint, repo_root, tasks_dir)
        elif phase == OrchestrationPhase.PUBLISHED.value:
            result = _build_result(
                checkpoint,
                ok=True,
                status=OrchestrationStatus.PUBLISHED,
            )
        elif phase == OrchestrationPhase.BLOCKED.value:
            result = _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.BLOCKED,
            )
        elif phase == OrchestrationPhase.FAILED.value:
            result = _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.FAILED,
            )
        else:
            result = _build_result(
                checkpoint,
                ok=False,
                status=OrchestrationStatus.FAILED,
                blocking_reason=f"Unknown phase: {phase}",
            )

        if result is not None:
            return result

    return _build_result(
        checkpoint,
        ok=False,
        status=OrchestrationStatus.FAILED,
        blocking_reason="Orchestration exceeded maximum iteration limit",
    )
