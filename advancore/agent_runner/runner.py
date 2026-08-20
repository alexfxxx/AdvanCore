"""Orchestration control plane for the local agent runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from advancore.agent_runner.git_info import get_git_info
from advancore.agent_runner.task import find_task
from advancore.agent_runner.validation import ValidationResult, validate
from advancore.agent_runner.worker import (
    DryRunWorkerAdapter,
    WorkerAdapter,
    WorkerResult,
    build_worker_instruction,
)


class RunnerStatus(str, Enum):
    """High-level status of a runner invocation."""

    DISCOVERED = "discovered"
    VALIDATED = "validated"
    PLANNING = "planning"
    WORKER_LAUNCHED = "worker_launched"
    WORKER_COMPLETED = "worker_completed"
    WORKER_FAILED = "worker_failed"
    AWAITING_APPROVAL = "awaiting_approval"
    FAILED = "failed"


@dataclass
class RunnerResult:
    """Complete result of a runner plan or execute invocation."""

    status: RunnerStatus
    task: "Task | None" = None
    git_info: "GitInfo | None" = None
    validation: ValidationResult | None = None
    worker_instruction: str | None = None
    worker_command: list[str] | None = None
    worker_result: WorkerResult | None = None
    messages: list[str] = field(default_factory=list)


def plan(
    tasks_dir: Path,
    task_id: str,
    worker: WorkerAdapter | None = None,
) -> RunnerResult:
    """Build a dry-run execution plan for *task_id*.

    This function never launches a worker. It discovers the task, inspects the
    repository, validates safety preconditions, and produces the instruction
    that would be sent to the worker.
    """
    worker = worker or DryRunWorkerAdapter()

    try:
        git_info = get_git_info(cwd=tasks_dir)
    except Exception as exc:
        return RunnerResult(
            status=RunnerStatus.FAILED,
            messages=[f"Failed to inspect Git repository: {exc}"],
        )

    try:
        task = find_task(tasks_dir, task_id)
    except Exception as exc:
        return RunnerResult(
            status=RunnerStatus.FAILED,
            git_info=git_info,
            messages=[f"Failed to discover task: {exc}"],
        )

    validation = validate(task, git_info.current_branch, git_info.is_clean)
    worker_instruction = build_worker_instruction(f"tasks/{task.filename}")
    worker_command = worker.build_command(worker_instruction, git_info.repo_root)

    if not validation:
        return RunnerResult(
            status=RunnerStatus.FAILED,
            task=task,
            git_info=git_info,
            validation=validation,
            worker_instruction=worker_instruction,
            worker_command=worker_command,
            messages=validation.messages
            + ["Execution blocked: safety validation failed."],
        )

    return RunnerResult(
        status=RunnerStatus.PLANNING,
        task=task,
        git_info=git_info,
        validation=validation,
        worker_instruction=worker_instruction,
        worker_command=worker_command,
        messages=validation.messages
        + ["Plan ready. Worker not launched (dry-run by default)."],
    )


def execute(
    tasks_dir: Path,
    task_id: str,
    worker: WorkerAdapter | None = None,
) -> RunnerResult:
    """Plan and, if safe, launch *worker* for *task_id*.

    Execution still respects the same approval gates: the worker is only asked
    to implement the task and report back. Commit, push, merge, and other
    high-impact actions remain gated.
    """
    worker = worker or DryRunWorkerAdapter()
    result = plan(tasks_dir, task_id, worker=worker)

    if result.status == RunnerStatus.FAILED:
        return result

    worker_result = worker.run(result.worker_instruction, result.git_info.repo_root)
    result.worker_result = worker_result

    if worker_result.success:
        result.status = RunnerStatus.AWAITING_APPROVAL
        result.messages.append(
            "Worker completed. Results await independent owner/reviewer approval."
        )
    else:
        result.status = RunnerStatus.WORKER_FAILED
        result.messages.append(f"Worker failed: {worker_result.message}")

    return result
