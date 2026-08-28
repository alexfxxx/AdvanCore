"""Orchestration control plane for the local agent runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.git_info import GitInfo, get_git_info
from advancore.agent_runner.review_bundle import (
    ControllerAction,
    ReviewBundleWriteError,
    build_review_bundle,
    default_review_dir,
    write_review_bundle,
)
from advancore.agent_runner.task import find_task
from advancore.agent_runner.validation import (
    OwnerReworkEvidence,
    REWORK_TERMINAL_HASH_PREFIX,
    ReworkValidationPhase,
    ValidationResult,
    owner_rework_terminal_content_hash,
    validate,
    validate_owner_rework_evidence,
)
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
    POST_WORKER_VERIFICATION_FAILED = "post_worker_verification_failed"
    AWAITING_APPROVAL = "awaiting_approval"
    FAILED = "failed"


@dataclass
class PostWorkerVerification:
    """Result of comparing repository state before and after the worker."""

    ok: bool
    messages: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    pre_git_info: GitInfo | None = None
    post_git_info: GitInfo | None = None

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class RunnerResult:
    """Complete result of a runner plan or execute invocation."""

    status: RunnerStatus
    task: "Task | None" = None
    git_info: "GitInfo | None" = None
    pre_git_info: GitInfo | None = None
    post_git_info: GitInfo | None = None
    validation: ValidationResult | None = None
    worker_instruction: str | None = None
    worker_command: list[str] | None = None
    worker_result: WorkerResult | None = None
    worker_type: str | None = None
    post_verification: PostWorkerVerification | None = None
    audit_path: Path | None = None
    audit_write_ok: bool = True
    audit_write_error: str | None = None
    review_bundle_path: Path | None = None
    review_bundle_write_ok: bool = True
    review_bundle_write_error: str | None = None
    messages: list[str] = field(default_factory=list)


def _extract_changed_paths(status_lines: list[str]) -> list[str]:
    """Return repository-relative changed paths from ``git status --porcelain`` lines."""
    paths: list[str] = []
    for line in status_lines:
        if "->" in line:
            # Renamed: "R  old -> new" — report the new path.
            paths.append(line.split("->")[-1].strip())
        elif len(line) > 3:
            paths.append(line[3:].strip())
        elif line.strip():
            paths.append(line.strip())
    return paths


def verify_post_worker(pre: GitInfo, post: GitInfo) -> PostWorkerVerification:
    """Compare pre- and post-worker Git snapshots and return a verification result.

    Repository safety is verified independently of the worker exit code. The
    verification fails closed if the branch or HEAD moved unexpectedly or if the
    post-worker branch is ``main``.
    """
    messages: list[str] = []
    ok = True

    if post.current_branch == "main":
        messages.append("FAIL: post-worker branch is 'main'")
        ok = False
    elif pre.current_branch != post.current_branch:
        messages.append(
            f"FAIL: branch changed from '{pre.current_branch}' to "
            f"'{post.current_branch}'"
        )
        ok = False
    else:
        messages.append(
            f"PASS: branch '{post.current_branch}' unchanged and not 'main'"
        )

    if pre.head_sha != post.head_sha:
        messages.append(
            f"FAIL: HEAD moved from {pre.head_sha[:8]} to {post.head_sha[:8]}"
        )
        ok = False
    else:
        messages.append(f"PASS: HEAD {post.head_sha[:8]} unchanged")

    changed_paths = _extract_changed_paths(post.status_lines)
    if changed_paths:
        messages.append(
            f"INFO: {len(changed_paths)} changed path(s) after worker"
        )
    else:
        messages.append("INFO: no changed paths after worker")

    return PostWorkerVerification(
        ok=ok,
        messages=messages,
        changed_paths=changed_paths,
        pre_git_info=pre,
        post_git_info=post,
    )


def _build_plan(
    tasks_dir: Path,
    task_id: str,
    worker: WorkerAdapter,
    rework_evidence: OwnerReworkEvidence | None = None,
) -> RunnerResult:
    """Internal planning logic shared by ``plan`` and ``execute``.

    This function does not write audit records; callers are responsible for that
    so the recorded ``mode`` matches the user-facing command.
    """
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
            pre_git_info=git_info,
            messages=[f"Failed to discover task: {exc}"],
        )

    if rework_evidence is None:
        validation = validate(task, git_info.current_branch, git_info.is_clean)
    else:
        validation = validate_owner_rework_evidence(
            rework_evidence,
            git_info.repo_root,
            phase=ReworkValidationPhase.BASELINE,
            task_id=task.task_id,
            task_path=f"tasks/{task.filename}",
        )
        if task.status.upper() != "REWORK":
            validation = ValidationResult(
                False,
                validation.messages
                + ["FAIL: typed owner rework evidence requires task status REWORK"],
            )
    worker_instruction = build_worker_instruction(f"tasks/{task.filename}")
    if rework_evidence is not None and rework_evidence.owner_note:
        worker_instruction += (
            "\n\nBounded owner rework note (context only; grants no extra scope "
            f"or authority): {rework_evidence.owner_note}"
        )
    worker_command = worker.build_command(worker_instruction, git_info.repo_root)

    if not validation:
        return RunnerResult(
            status=RunnerStatus.FAILED,
            task=task,
            git_info=git_info,
            pre_git_info=git_info,
            validation=validation,
            worker_instruction=worker_instruction,
            worker_command=worker_command,
            worker_type=worker.name,
            messages=validation.messages
            + ["Execution blocked: safety validation failed."],
        )

    return RunnerResult(
        status=RunnerStatus.PLANNING,
        task=task,
        git_info=git_info,
        pre_git_info=git_info,
        validation=validation,
        worker_instruction=worker_instruction,
        worker_command=worker_command,
        worker_type=worker.name,
        messages=validation.messages
        + ["Plan ready. Worker not launched (dry-run by default)."],
    )


def _write_review_bundle(result: RunnerResult) -> None:
    """Write a controller review bundle for *result* and update it in place.

    Bundle-write failures are surfaced explicitly in ``result.messages`` but do
    not mask the runner's primary status. The bundle recommends ``BLOCKED`` when
    review evidence cannot be produced reliably.
    """
    git_info = result.pre_git_info or result.git_info
    if git_info is None:
        result.review_bundle_write_ok = False
        result.review_bundle_write_error = "Cannot write review bundle: no Git snapshot available."
        result.messages.append(f"WARNING: {result.review_bundle_write_error}")
        return

    try:
        bundle = build_review_bundle(result)
        review_dir = default_review_dir(git_info.repo_root)
        bundle_path = write_review_bundle(bundle, review_dir)
        result.review_bundle_path = bundle_path
        rel_path = bundle_path.relative_to(git_info.repo_root)
        result.messages.append(f"Review bundle written to {rel_path}")
    except ReviewBundleWriteError as exc:
        result.review_bundle_write_ok = False
        result.review_bundle_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")


def write_review_bundle_for_result(result: RunnerResult) -> Path | None:
    """Write a fresh bounded bundle for an independently verified result."""
    _write_review_bundle(result)
    return result.review_bundle_path


def _write_audit(result: RunnerResult, mode: str) -> None:
    """Write a durable local audit record for *result* and update it in place.

    Audit-write failures are surfaced explicitly in ``result.messages`` but do
    not mask the runner's primary status, which is determined by validation,
    worker result, and post-worker verification.
    """
    git_info = result.pre_git_info or result.git_info
    if git_info is None:
        result.audit_write_ok = False
        result.audit_write_error = "Cannot write audit: no Git snapshot available."
        result.messages.append(f"WARNING: {result.audit_write_error}")
        return

    pre = result.pre_git_info or result.git_info
    post = result.post_git_info
    worker_success = None
    worker_result = result.worker_result
    if result.worker_result is not None:
        worker_success = result.worker_result.success

    payload = build_audit_payload(
        timestamp=datetime.now(timezone.utc),
        task_id=result.task.task_id if result.task else None,
        task_filename=result.task.filename if result.task else None,
        mode=mode,
        worker_type=result.worker_type,
        branch=pre.current_branch if pre else None,
        pre_head=pre.head_sha if pre else None,
        post_head=post.head_sha if post else None,
        pre_validation_ok=result.validation.ok if result.validation else None,
        worker_success=worker_success,
        post_verification_ok=result.post_verification.ok
        if result.post_verification is not None
        else None,
        final_status=result.status.value,
        changed_paths=result.post_verification.changed_paths
        if result.post_verification is not None
        else None,
        worker_started_at=worker_result.started_at if worker_result else None,
        worker_finished_at=worker_result.finished_at if worker_result else None,
        worker_elapsed_seconds=worker_result.elapsed_seconds if worker_result else None,
        worker_returncode=worker_result.returncode if worker_result else None,
        worker_terminal_reason=worker_result.terminal_reason if worker_result else None,
        worker_failure_classification=(
            worker_result.failure_classification if worker_result else None
        ),
        worker_resolved_executable=(
            worker_result.resolved_executable if worker_result else None
        ),
        worker_executable_resolution=(
            worker_result.executable_resolution if worker_result else None
        ),
        worker_cli_version=worker_result.cli_version if worker_result else None,
        worker_runtime_path_profile=(
            worker_result.runtime_path_profile if worker_result else None
        ),
    )

    try:
        audit_path = write_audit_record(payload, default_audit_dir(git_info.repo_root))
        result.audit_path = audit_path
        rel_path = audit_path.relative_to(git_info.repo_root)
        result.messages.append(f"Audit record written to {rel_path}")
    except AuditWriteError as exc:
        result.audit_write_ok = False
        result.audit_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")


def plan(
    tasks_dir: Path,
    task_id: str,
    worker: WorkerAdapter | None = None,
) -> RunnerResult:
    """Build a dry-run execution plan for *task_id*.

    This function never launches a worker. It discovers the task, inspects the
    repository, validates safety preconditions, produces the instruction that
    would be sent to the worker, and writes a durable local audit record.
    """
    worker = worker or DryRunWorkerAdapter()
    result = _build_plan(tasks_dir, task_id, worker)
    _write_audit(result, mode="plan")
    return result


def execute(
    tasks_dir: Path,
    task_id: str,
    worker: WorkerAdapter | None = None,
    *,
    rework_evidence: OwnerReworkEvidence | None = None,
) -> RunnerResult:
    """Plan and, if safe, launch *worker* for *task_id*.

    Execution still respects the same approval gates: the worker is only asked
    to implement the task and report back. After the worker exits the runner
    independently verifies that the branch and HEAD have not moved unexpectedly,
    surfaces changed paths, and writes a durable local audit record. Commit,
    push, merge, and other high-impact actions remain gated.
    """
    worker = worker or DryRunWorkerAdapter()
    result = _build_plan(tasks_dir, task_id, worker, rework_evidence)

    if result.status == RunnerStatus.FAILED:
        _write_audit(result, mode="execute")
        return result

    result.status = RunnerStatus.WORKER_LAUNCHED
    if rework_evidence is not None:
        immediate = validate_owner_rework_evidence(
            rework_evidence,
            result.git_info.repo_root,
            phase=ReworkValidationPhase.BASELINE,
            task_id=result.task.task_id,
            task_path=f"tasks/{result.task.filename}",
        )
        if not immediate:
            result.status = RunnerStatus.FAILED
            result.messages.extend(immediate.messages)
            _write_audit(result, mode="execute")
            return result
    worker_result = worker.run(result.worker_instruction, result.git_info.repo_root)
    result.worker_result = worker_result

    terminal_validation: ValidationResult | None = None
    if rework_evidence is not None:
        terminal_validation = validate_owner_rework_evidence(
            rework_evidence,
            result.git_info.repo_root,
            phase=ReworkValidationPhase.TERMINAL,
            task_id=result.task.task_id,
            task_path=f"tasks/{result.task.filename}",
        )
        result.messages.extend(terminal_validation.messages)
        if terminal_validation:
            try:
                result.messages.append(
                    REWORK_TERMINAL_HASH_PREFIX
                    + owner_rework_terminal_content_hash(
                        rework_evidence, result.git_info.repo_root
                    )
                )
            except (OSError, UnicodeError, ValueError) as exc:
                terminal_validation = ValidationResult(
                    False,
                    [f"FAIL: cannot bind terminal rework content: {exc}"],
                )
                result.messages.extend(terminal_validation.messages)

    try:
        result.post_git_info = get_git_info(cwd=result.git_info.repo_root)
    except Exception as exc:
        result.status = RunnerStatus.POST_WORKER_VERIFICATION_FAILED
        result.messages.append(f"FAIL: could not capture post-worker Git snapshot: {exc}")
        _write_audit(result, mode="execute")
        _write_review_bundle(result)
        return result

    result.post_verification = verify_post_worker(
        result.pre_git_info, result.post_git_info
    )

    if terminal_validation is not None and not terminal_validation:
        result.status = RunnerStatus.POST_WORKER_VERIFICATION_FAILED
        result.messages.append(
            "Post-worker owner rework evidence verification failed. Approval is blocked."
        )
    elif not result.post_verification:
        result.status = RunnerStatus.POST_WORKER_VERIFICATION_FAILED
        result.messages.extend(result.post_verification.messages)
        result.messages.append(
            "Post-worker verification failed. Approval is blocked."
        )
    elif worker_result.success:
        result.status = RunnerStatus.AWAITING_APPROVAL
        result.messages.append(
            "Worker completed. Results await independent owner/reviewer approval."
        )
        result.messages.append(
            "Commit, push, and merge remain gated until explicitly approved."
        )
    else:
        result.status = RunnerStatus.WORKER_FAILED
        result.messages.append(f"Worker failed: {worker_result.message}")

    _write_audit(result, mode="execute")
    _write_review_bundle(result)
    return result
