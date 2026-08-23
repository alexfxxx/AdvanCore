"""Controller-gated finalization and branch publication for the local agent runner.

This module provides a single bounded path that consumes a separately valid
controller ``APPROVE`` decision for a successfully verified auto-pipeline result,
applies only authorized lifecycle transitions, stages exactly the verified task
scope, creates one local commit, and pushes only the current non-``main`` feature
branch.

The finalizer does **not** infer approval from test success, Kimi output,
review-bundle state, file presence, or transport success. It executes authority;
it does not create it.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_finalization_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    ControllerDecisionError,
    DecisionValue,
    default_decisions_dir,
    find_latest_decision,
    load_controller_decision,
)
from advancore.agent_runner.decision_lifecycle_bridge import (
    DecisionLifecycleBridgeError,
    apply_controller_decision,
)
from advancore.agent_runner.git_info import GitInfo, get_git_info
from advancore.agent_runner.lifecycle import (
    ActorRole,
    LifecycleResult,
    TaskStatus,
    is_transition_allowed,
    transition_task,
)
from advancore.agent_runner.review_bundle import (
    ReviewBundle,
    ReviewBundleError,
    load_review_bundle,
)
from advancore.agent_runner.task import TaskError, find_task


class FinalizationStatus(str, Enum):
    """Terminal status of a controller-gated finalization attempt."""

    READY_TO_FINALIZE = "READY_TO_FINALIZE"
    FINALIZED_LOCAL = "FINALIZED_LOCAL"
    PUSHED = "PUSHED"
    BLOCKED = "BLOCKED"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    DECISION_REJECTED = "DECISION_REJECTED"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"


class FinalizationError(Exception):
    """Raised when a finalization gate cannot be satisfied."""


@dataclass
class FinalizationResult:
    """Complete result of a controller-gated finalization attempt."""

    ok: bool
    status: FinalizationStatus
    task_id: str | None = None
    task_filename: str | None = None
    branch: str | None = None
    pre_head: str | None = None
    post_head: str | None = None
    commit_sha: str | None = None
    decision_path: str | None = None
    bundle_path: str | None = None
    staged_paths: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    lifecycle_states: list[str] = field(default_factory=list)
    push_command: list[str] | None = None
    push_result: dict[str, Any] | None = None
    audit_path: Path | None = None
    audit_write_ok: bool = True
    audit_write_error: str | None = None
    apply: bool = False
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


FINALIZE_SUBDIR = "finalize"
FINALIZE_ARTIFACT_FILENAME = "finalize.jsonl"

# Characters that must never appear in a bounded commit message.
_COMMIT_MESSAGE_FORBIDDEN_RE = re.compile(r"[\r\n]")


def default_finalize_dir(repo_root: Path) -> Path:
    """Return the default finalization artifact directory for *repo_root*."""
    return repo_root / ".agent_runner" / FINALIZE_SUBDIR


def _run_git(
    args: list[str],
    cwd: Path,
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` in *cwd* and return the completed process.

    The command is passed as an argument array; no shell interpolation is used.
    """
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _current_branch(cwd: Path) -> str:
    """Return the current branch name or raise ``FinalizationError``."""
    result = _run_git(["branch", "--show-current"], cwd=cwd)
    if result.returncode != 0:
        raise FinalizationError(f"cannot determine current branch: {result.stderr.strip()}")
    branch = result.stdout.strip()
    if not branch:
        raise FinalizationError("repository is in detached HEAD state")
    return branch


def _current_head(cwd: Path) -> str:
    """Return the current HEAD SHA or raise ``FinalizationError``."""
    result = _run_git(["rev-parse", "HEAD"], cwd=cwd)
    if result.returncode != 0:
        raise FinalizationError(f"cannot determine HEAD: {result.stderr.strip()}")
    return result.stdout.strip()


def _porcelain_status(cwd: Path) -> list[str]:
    """Return non-empty ``git status --porcelain`` lines for individual files.

    ``--untracked-files=all`` ensures new directories are reported as the
    individual untracked files inside them, giving a precise changed-path set.
    """
    result = _run_git(["status", "--porcelain", "--untracked-files=all"], cwd=cwd)
    if result.returncode != 0:
        raise FinalizationError(f"git status failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


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


def _staged_paths(cwd: Path) -> list[str]:
    """Return repository-relative paths currently staged."""
    result = _run_git(["diff", "--cached", "--name-only"], cwd=cwd)
    if result.returncode != 0:
        raise FinalizationError(f"cannot inspect staged changes: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _resolve_decision_path(value: str | Path | None, repo_root: Path) -> Path:
    """Return an absolute decision-record path from a CLI-style target.

    ``None`` or ``"latest"`` resolves to the most recently modified decision
    record under ``.agent_runner/decisions/``.
    """
    if value is None or str(value).strip().lower() == "latest":
        decisions_dir = default_decisions_dir(repo_root)
        latest = find_latest_decision(decisions_dir)
        if latest is None:
            raise FinalizationError(f"no decision records found under {decisions_dir}")
        return latest.resolve()

    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path.resolve()


def _resolve_bundle_path(decision: ControllerDecision, repo_root: Path) -> Path:
    """Return the absolute path to the linked review bundle."""
    bundle_path = Path(decision.bundle_path)
    if not bundle_path.is_absolute():
        bundle_path = (repo_root / bundle_path).resolve()
    return bundle_path.resolve()


def _validate_decision_actor(decision: ControllerDecision) -> None:
    """Fail closed if the decision actor is worker or unknown."""
    try:
        actor = ActorRole(decision.actor_role.lower())
    except ValueError as exc:
        raise FinalizationError(f"unknown decision actor role: {decision.actor_role!r}") from exc

    if actor == ActorRole.WORKER:
        raise FinalizationError("worker cannot act as a controller decision actor")


def _validate_decision_value(decision: ControllerDecision) -> None:
    """Fail closed unless the decision is a known controller value."""
    try:
        decision_enum = DecisionValue(decision.decision.upper())
    except ValueError as exc:
        raise FinalizationError(
            f"unknown controller decision: {decision.decision!r}. "
            f"Allowed values are: {', '.join(d.value for d in DecisionValue)}."
        ) from exc

    if decision_enum != DecisionValue.APPROVE:
        raise FinalizationError(
            f"decision is {decision_enum.value}; only APPROVE may finalize",
            decision_enum.value,
        )


def _require_bundle_field(name: str, value: str | None) -> str:
    """Return *value* if it is a non-empty string, else raise."""
    if not value or not isinstance(value, str):
        raise FinalizationError(f"review bundle is missing required field: {name}")
    return value


def _normalize_path_set(paths: list[str]) -> set[str]:
    """Return a normalized set of repository-relative path strings."""
    normalized: set[str] = set()
    for p in paths:
        p = p.strip()
        if not p:
            continue
        # Strip a leading status code if present (e.g. "M  path").
        if len(p) > 3 and p[2:3] == " ":
            p = p[3:].strip()
        normalized.add(Path(p).as_posix())
    return normalized


def _build_commit_message(task_title: str, custom_message: str | None = None) -> str:
    """Return a bounded, deterministic commit message.

    A controller-supplied message is accepted only if it contains no newlines or
    carriage returns and is non-empty after stripping. Otherwise a task-derived
    message is used.
    """
    if custom_message is not None:
        message = custom_message.strip()
        if message and not _COMMIT_MESSAGE_FORBIDDEN_RE.search(message):
            return message
    safe_title = re.sub(r"[^\w\s\-:.]+", "", task_title).strip()
    if not safe_title:
        safe_title = "agent task"
    return f"agent: {safe_title}"


def _write_finalize_artifact(
    result: FinalizationResult,
    repo_root: Path,
) -> Path | None:
    """Append a bounded finalization artifact and return its path."""
    payload = build_finalization_audit_payload(
        timestamp=datetime.now(timezone.utc),
        task_id=result.task_id,
        task_filename=result.task_filename,
        status=result.status.value,
        branch=result.branch,
        pre_head=result.pre_head,
        post_head=result.post_head,
        commit_sha=result.commit_sha,
        decision_path=result.decision_path,
        bundle_path=result.bundle_path,
        staged_paths=result.staged_paths,
        changed_paths=result.changed_paths,
        lifecycle_states=result.lifecycle_states,
        push_command=result.push_command,
        push_result=result.push_result,
        messages=result.messages,
    )

    finalize_dir = default_finalize_dir(repo_root)
    try:
        finalize_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        result.audit_write_ok = False
        result.audit_write_error = f"Failed to create finalize directory {finalize_dir}: {exc}"
        result.messages.append(f"WARNING: {result.audit_write_error}")
        return None

    path = finalize_dir / FINALIZE_ARTIFACT_FILENAME
    line = json.dumps(payload, separators=(",", ":"), default=str, sort_keys=True) + "\n"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        result.audit_write_ok = False
        result.audit_write_error = f"Failed to write finalization artifact to {path}: {exc}"
        result.messages.append(f"WARNING: {result.audit_write_error}")
        return None

    return path


def _maybe_write_audit(result: FinalizationResult, repo_root: Path) -> None:
    """Append a finalization audit record and update *result* in place."""
    try:
        audit_path = write_audit_record(
            build_finalization_audit_payload(
                timestamp=datetime.now(timezone.utc),
                task_id=result.task_id,
                task_filename=result.task_filename,
                status=result.status.value,
                branch=result.branch,
                pre_head=result.pre_head,
                post_head=result.post_head,
                commit_sha=result.commit_sha,
                decision_path=result.decision_path,
                bundle_path=result.bundle_path,
                staged_paths=result.staged_paths,
                changed_paths=result.changed_paths,
                lifecycle_states=result.lifecycle_states,
                push_command=result.push_command,
                push_result=result.push_result,
                messages=result.messages,
            ),
            default_audit_dir(repo_root),
        )
        result.audit_path = audit_path
    except AuditWriteError as exc:
        result.audit_write_ok = False
        result.audit_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")


def _fail(
    result: FinalizationResult,
    status: FinalizationStatus,
    message: str,
    repo_root: Path,
) -> FinalizationResult:
    """Close out a failed finalization result, write audit, and return it."""
    result.ok = False
    result.status = status
    result.messages.append(message)
    _maybe_write_audit(result, repo_root)
    return result


def _apply_worker_transition(
    tasks_dir: Path,
    task_id: str,
    to_status: TaskStatus,
    apply: bool,
    git_info: GitInfo,
) -> LifecycleResult:
    """Apply a worker-attributed lifecycle transition and return the result."""
    return transition_task(
        tasks_dir,
        task_id,
        to_status,
        ActorRole.WORKER,
        apply=apply,
        git_info=git_info,
    )


def run_finalization(
    repo_root: Path,
    tasks_dir: Path,
    task_id: str,
    *,
    decision_path: str | Path | None = None,
    commit_message: str | None = None,
    apply: bool = False,
) -> FinalizationResult:
    """Run the controller-gated finalization path for *task_id*.

    Preview mode (``apply=False``) performs all safe validation and reports what
    would happen without changing lifecycle state, index, HEAD, or remote state.
    Apply mode (``apply=True``) executes each gate in order and stops at the
    first failure.

    The caller is responsible for ensuring *repo_root* and *tasks_dir* exist and
    that the repository is in a clean, expected state.
    """
    result = FinalizationResult(
        ok=False,
        status=FinalizationStatus.BLOCKED,
        task_id=task_id,
        apply=apply,
        messages=[f"Finalization {'apply' if apply else 'preview'} started for {task_id}"],
    )

    # 1. Capture current Git snapshot.
    try:
        git_info = get_git_info(cwd=repo_root)
    except Exception as exc:
        result.messages.append(f"FAIL: cannot inspect Git repository: {exc}")
        _maybe_write_audit(result, repo_root)
        return result

    result.branch = git_info.current_branch
    result.pre_head = git_info.head_sha

    # 2. Reject main immediately.
    if git_info.current_branch == "main":
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            "FAIL: finalization is not permitted on the 'main' branch",
            repo_root,
        )

    # 3. Resolve and load the controller decision record.
    try:
        decision_file = _resolve_decision_path(decision_path, repo_root)
        decision = load_controller_decision(decision_file)
        result.decision_path = str(decision_file)
    except (ControllerDecisionError, FinalizationError, OSError) as exc:
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            f"FAIL: cannot load controller decision: {exc}",
            repo_root,
        )

    # 4. Validate decision actor and value.
    try:
        _validate_decision_actor(decision)
        _validate_decision_value(decision)
    except FinalizationError as exc:
        extra = getattr(exc, "args", [None])
        decision_value = extra[1] if len(extra) > 1 else None
        status = (
            FinalizationStatus.DECISION_REJECTED
            if decision_value and decision_value != "APPROVE"
            else FinalizationStatus.BLOCKED
        )
        return _fail(result, status, f"FAIL: {exc}", repo_root)

    # 5. Resolve and load the linked review bundle.
    try:
        bundle_file = _resolve_bundle_path(decision, repo_root)
        result.bundle_path = str(bundle_file)
        bundle = load_review_bundle(bundle_file)
    except (ReviewBundleError, FinalizationError, OSError) as exc:
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            f"FAIL: cannot load linked review bundle: {exc}",
            repo_root,
        )

    # 6. Validate required bundle linkage evidence.
    try:
        bundle_task_id = _require_bundle_field("task_id", bundle.task_id)
        bundle_task_filename = _require_bundle_field("task_filename", bundle.task_filename)
        bundle_branch = _require_bundle_field("branch", bundle.branch)
        bundle_pre_head = _require_bundle_field("pre_head", bundle.pre_head)
        bundle_post_head = bundle.post_head
    except FinalizationError as exc:
        return _fail(result, FinalizationStatus.STALE_EVIDENCE, f"FAIL: {exc}", repo_root)

    # 7. Validate task identity linkage.
    try:
        task = find_task(tasks_dir, task_id)
    except TaskError as exc:
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            f"FAIL: cannot find task {task_id!r}: {exc}",
            repo_root,
        )

    result.task_id = task.task_id
    result.task_filename = task.filename

    try:
        task_file_rel = task.path.relative_to(repo_root).as_posix()
    except ValueError:
        task_file_rel = task.path.as_posix()

    if decision.task_id != bundle_task_id or decision.task_id != task.task_id:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: task ID mismatch: decision={decision.task_id!r}, "
            f"bundle={bundle_task_id!r}, task={task.task_id!r}",
            repo_root,
        )

    if decision.task_filename != bundle_task_filename or decision.task_filename != task.filename:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: task filename mismatch: decision={decision.task_filename!r}, "
            f"bundle={bundle_task_filename!r}, task={task.filename!r}",
            repo_root,
        )

    if decision.bundle_task_id != bundle_task_id:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: decision bundle_task_id mismatch: {decision.bundle_task_id!r} "
            f"!= {bundle_task_id!r}",
            repo_root,
        )

    if decision.bundle_task_filename != bundle_task_filename:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: decision bundle_task_filename mismatch: "
            f"{decision.bundle_task_filename!r} != {bundle_task_filename!r}",
            repo_root,
        )

    # 8. Validate branch and HEAD freshness.
    if bundle_branch != git_info.current_branch:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: branch mismatch: current={git_info.current_branch!r}, "
            f"bundle={bundle_branch!r}",
            repo_root,
        )

    if bundle_post_head is not None and bundle_post_head != git_info.head_sha:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: HEAD is stale: current={git_info.head_sha!r}, "
            f"bundle_post={bundle_post_head!r}",
            repo_root,
        )

    # 9. Verify no staged paths at start.
    try:
        initial_staged = _staged_paths(repo_root)
    except FinalizationError as exc:
        return _fail(result, FinalizationStatus.BLOCKED, f"FAIL: {exc}", repo_root)

    if initial_staged:
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            f"FAIL: existing staged paths at start: {initial_staged}",
            repo_root,
        )

    # 10. Verify current working-tree changed paths exactly match bundle evidence.
    try:
        current_status_lines = _porcelain_status(repo_root)
        current_changed = _extract_changed_paths(current_status_lines)
    except FinalizationError as exc:
        return _fail(result, FinalizationStatus.BLOCKED, f"FAIL: {exc}", repo_root)

    approved_paths = _normalize_path_set(bundle.changed_paths)
    actual_paths = _normalize_path_set(current_changed)
    result.changed_paths = sorted(actual_paths)

    if not approved_paths:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            "FAIL: no verified changed paths to finalize",
            repo_root,
        )

    if actual_paths != approved_paths:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: changed-path mismatch: actual={sorted(actual_paths)}, "
            f"approved={sorted(approved_paths)}",
            repo_root,
        )

    result.messages.append(
        f"PASS: verified changed paths match approved scope: {sorted(approved_paths)}"
    )

    # 11. Orchestrate worker lifecycle transitions where warranted.
    # In preview mode the task file is not rewritten, so we validate the chain
    # logically and only call the authority-aware transition helper in apply
    # mode, re-reading the task status after each applied step.
    task_status = task.status.upper()
    lifecycle_states: list[str] = [task_status]

    def _compute_worker_chain(start: str) -> list[str]:
        chain = [start]
        if start == TaskStatus.READY.value:
            chain.append(TaskStatus.IN_PROGRESS.value)
        if chain[-1] == TaskStatus.IN_PROGRESS.value:
            chain.append(TaskStatus.REVIEW.value)
        return chain

    worker_chain = _compute_worker_chain(task_status)

    # Validate every worker transition logically first.
    for i in range(len(worker_chain) - 1):
        current_step = worker_chain[i]
        next_step = worker_chain[i + 1]
        allowed, reason = is_transition_allowed(current_step, next_step, ActorRole.WORKER)
        if not allowed:
            return _fail(
                result,
                FinalizationStatus.BLOCKED,
                f"FAIL: {current_step} -> {next_step} transition denied for worker: {reason}",
                repo_root,
            )
        result.messages.append(f"{current_step} -> {next_step} allowed for worker")

    # Apply worker transitions in apply mode.
    if apply:
        for i in range(len(worker_chain) - 1):
            next_step_enum = TaskStatus(worker_chain[i + 1])
            worker_result = _apply_worker_transition(
                tasks_dir, task.task_id, next_step_enum, apply=True, git_info=git_info
            )
            result.messages.extend(worker_result.messages)
            if not worker_result.allowed or not worker_result.applied:
                return _fail(
                    result,
                    FinalizationStatus.BLOCKED,
                    f"FAIL: {worker_chain[i]} -> {worker_chain[i + 1]} transition could not be applied",
                    repo_root,
                )
            lifecycle_states.append(worker_chain[i + 1])
            # Re-read task status for the next iteration.
            try:
                task_status = find_task(tasks_dir, task.task_id).status.upper()
            except TaskError as exc:
                return _fail(
                    result,
                    FinalizationStatus.BLOCKED,
                    f"FAIL: cannot re-read task status after transition: {exc}",
                    repo_root,
                )
    else:
        # Preview mode: record the logical chain without mutating the task file.
        lifecycle_states.extend(worker_chain[1:])
        task_status = worker_chain[-1]

    # 12. Apply controller approval via the existing decision-lifecycle bridge.
    # In apply mode the task file has been moved to REVIEW (if needed), so the
    # bridge can validate and apply REVIEW -> APPROVED. In preview mode the file
    # is still at its original status, so we perform the same linkage/authority
    # checks manually and report the intended approval transition.
    if apply:
        if task_status == TaskStatus.REVIEW.value:
            bridge_result = apply_controller_decision(
                repo_root=repo_root,
                tasks_dir=tasks_dir,
                decision_path=Path(result.decision_path),
                apply=True,
                git_info=git_info,
            )
            result.messages.extend(bridge_result.messages)
            if not bridge_result.ok:
                return _fail(
                    result,
                    FinalizationStatus.BLOCKED,
                    "FAIL: controller decision could not be applied to lifecycle",
                    repo_root,
                )
            lifecycle_states.append(TaskStatus.APPROVED.value)
            task_status = TaskStatus.APPROVED.value
        elif task_status == TaskStatus.APPROVED.value:
            bridge_result = apply_controller_decision(
                repo_root=repo_root,
                tasks_dir=tasks_dir,
                decision_path=Path(result.decision_path),
                apply=False,
                git_info=git_info,
            )
            if not bridge_result.ok and not bridge_result.transition_allowed:
                if not (
                    bridge_result.task_id == task.task_id
                    and bridge_result.decision == DecisionValue.APPROVE.value
                ):
                    result.messages.extend(bridge_result.messages)
                    return _fail(
                        result,
                        FinalizationStatus.BLOCKED,
                        "FAIL: controller decision validation failed for already-approved task",
                        repo_root,
                    )
            result.messages.append(
                "Task is already APPROVED; using validated decision for audit"
            )
            lifecycle_states.append(TaskStatus.APPROVED.value)
        else:
            return _fail(
                result,
                FinalizationStatus.BLOCKED,
                f"FAIL: unexpected task status for finalization: {task_status}",
                repo_root,
            )
    else:
        # Preview mode: manual controller-approval validation.
        if task_status not in {TaskStatus.REVIEW.value, TaskStatus.APPROVED.value}:
            return _fail(
                result,
                FinalizationStatus.BLOCKED,
                f"FAIL: unexpected logical task status for finalization: {task_status}",
                repo_root,
            )
        # Authority and linkage were already validated; confirm decision maps to
        # APPROVED and report the intended transition.
        try:
            target_status = TaskStatus(
                {DecisionValue.APPROVE.value: TaskStatus.APPROVED.value}.get(
                    decision.decision.upper(), ""
                )
            )
        except ValueError as exc:
            return _fail(
                result,
                FinalizationStatus.BLOCKED,
                f"FAIL: decision {decision.decision!r} does not map to APPROVED: {exc}",
                repo_root,
            )
        result.messages.append(
            f"Preview: {task_status} -> {target_status.value} would be applied via controller decision"
        )
        lifecycle_states.append(target_status.value)
        task_status = target_status.value

    result.lifecycle_states = lifecycle_states
    result.messages.append(
        f"PASS: lifecycle transitions applied: {' -> '.join(lifecycle_states)}"
    )

    # 12b. The lifecycle transitions legitimately modify the task file; include it
    # in the staged/commit set so the final commit is complete and the tree is
    # clean. The task file path is derived from the validated task metadata.
    commit_set = approved_paths | {task_file_rel}
    sorted_paths = sorted(commit_set)

    # 12c. Re-verify the working tree now includes the expected task-file change.
    # In preview mode the task file has not been rewritten yet, so we verify
    # against the original approved working-tree scope; in apply mode we require
    # the task-file change to be present as well.
    expected_working_tree_paths = commit_set if apply else approved_paths
    try:
        post_transition_status_lines = _porcelain_status(repo_root)
        post_transition_changed = _extract_changed_paths(post_transition_status_lines)
    except FinalizationError as exc:
        return _fail(result, FinalizationStatus.BLOCKED, f"FAIL: {exc}", repo_root)

    post_transition_paths = _normalize_path_set(post_transition_changed)
    if post_transition_paths != expected_working_tree_paths:
        return _fail(
            result,
            FinalizationStatus.STALE_EVIDENCE,
            f"FAIL: post-transition path mismatch: actual={sorted(post_transition_paths)}, "
            f"approved={sorted(expected_working_tree_paths)}",
            repo_root,
        )

    result.changed_paths = sorted_paths
    result.messages.append(
        f"PASS: post-transition working tree matches approved scope: {sorted_paths}"
    )

    # 13. Stage only the exact verified paths.
    if apply:
        add_result = _run_git(["add", *sorted_paths], cwd=repo_root)
        if add_result.returncode != 0:
            return _fail(
                result,
                FinalizationStatus.BLOCKED,
                f"FAIL: git add failed: {add_result.stderr.strip()}",
                repo_root,
            )

    # 14. Independently verify staged scope.
    try:
        staged_after = _staged_paths(repo_root) if apply else []
    except FinalizationError as exc:
        return _fail(result, FinalizationStatus.BLOCKED, f"FAIL: {exc}", repo_root)

    if apply:
        staged_set = _normalize_path_set(staged_after)
        if staged_set != commit_set:
            return _fail(
                result,
                FinalizationStatus.BLOCKED,
                f"FAIL: staged path mismatch: staged={sorted(staged_set)}, "
                f"approved={sorted_paths}",
                repo_root,
            )
        result.staged_paths = sorted(staged_set)
    else:
        result.staged_paths = sorted_paths

    result.messages.append(
        f"PASS: staged scope matches approved paths: {result.staged_paths}"
    )

    # 15. Run cached diff check before commit.
    diff_check = _run_git(["diff", "--cached", "--check"], cwd=repo_root)
    if diff_check.returncode != 0:
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            f"FAIL: git diff --cached --check detected whitespace errors: "
            f"{diff_check.stderr.strip()}",
            repo_root,
        )

    result.messages.append("PASS: git diff --cached --check found no whitespace errors")

    # 16. Build bounded commit message.
    message = _build_commit_message(task.title, commit_message)
    result.messages.append(f"Commit message: {message}")

    # 17. Preview stop before mutation.
    if not apply:
        result.ok = True
        result.status = FinalizationStatus.READY_TO_FINALIZE
        result.messages.append(
            "Preview complete. Use --apply to execute lifecycle, stage, commit, and push."
        )
        _maybe_write_audit(result, repo_root)
        return result

    # 18. Create exactly one local commit.
    pre_commit_head = _current_head(repo_root)
    commit_result = _run_git(["commit", "-m", message], cwd=repo_root)
    if commit_result.returncode != 0:
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            f"FAIL: git commit failed: {commit_result.stderr.strip()}",
            repo_root,
        )

    result.commit_sha = _current_head(repo_root)
    result.messages.append(f"Created commit {result.commit_sha}")

    # 19. Post-commit verification.
    post_commit_status = _porcelain_status(repo_root)
    if post_commit_status:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: working tree is dirty after commit: {post_commit_status}",
            repo_root,
        )

    commit_parent = _run_git(["rev-parse", f"{result.commit_sha}^"], cwd=repo_root)
    if commit_parent.returncode != 0 or commit_parent.stdout.strip() != pre_commit_head:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: commit parent {commit_parent.stdout.strip()!r} != expected {pre_commit_head!r}",
            repo_root,
        )

    commit_tree = _run_git(["rev-parse", f"{result.commit_sha}^{{tree}}"], cwd=repo_root)
    if commit_tree.returncode != 0:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: cannot read commit tree: {commit_tree.stderr.strip()}",
            repo_root,
        )

    # Verify the commit contains exactly the approved paths.
    diff_tree = _run_git(
        ["diff-tree", "--no-commit-id", "--name-only", "-r", result.commit_sha],
        cwd=repo_root,
    )
    if diff_tree.returncode != 0:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: cannot inspect commit contents: {diff_tree.stderr.strip()}",
            repo_root,
        )

    committed_paths = _normalize_path_set(
        [line for line in diff_tree.stdout.splitlines() if line.strip()]
    )
    if committed_paths != commit_set:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: commit contents mismatch: committed={sorted(committed_paths)}, "
            f"approved={sorted_paths}",
            repo_root,
        )

    # Verify this is not a merge commit (exactly one parent).
    parents = _run_git(["rev-list", "--parents", "-n", "1", result.commit_sha], cwd=repo_root)
    if parents.returncode == 0:
        parent_count = len(parents.stdout.strip().split()) - 1
        if parent_count != 1:
            return _fail(
                result,
                FinalizationStatus.PUBLICATION_FAILED,
                f"FAIL: commit has {parent_count} parents; merge commits are not allowed",
                repo_root,
            )

    result.messages.append("PASS: post-commit verification complete")
    result.status = FinalizationStatus.FINALIZED_LOCAL

    # 20. Push only the current verified feature branch.
    branch = _current_branch(repo_root)
    if branch == "main":
        return _fail(
            result,
            FinalizationStatus.BLOCKED,
            "FAIL: current branch became 'main' after commit; push rejected",
            repo_root,
        )

    # Verify upstream points to origin/<branch>.
    upstream = _run_git(["rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], cwd=repo_root)
    expected_upstream = f"origin/{branch}"
    if upstream.returncode != 0 or upstream.stdout.strip() != expected_upstream:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: upstream mismatch: {upstream.stdout.strip()!r} != {expected_upstream!r}",
            repo_root,
        )

    push_command = ["git", "push", "origin", branch]
    result.push_command = push_command
    push_result = _run_git(["push", "origin", branch], cwd=repo_root)
    result.push_result = {
        "returncode": push_result.returncode,
        "stdout": push_result.stdout.strip(),
        "stderr": push_result.stderr.strip(),
    }

    if push_result.returncode != 0:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: git push failed: {push_result.stderr.strip()}",
            repo_root,
        )

    # 21. Post-push synchronization verification.
    local_head = _current_head(repo_root)
    remote_head = _run_git(["rev-parse", expected_upstream], cwd=repo_root)
    if remote_head.returncode != 0:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: cannot read remote HEAD {expected_upstream}: {remote_head.stderr.strip()}",
            repo_root,
        )

    if local_head != remote_head.stdout.strip():
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: local branch ({local_head}) is not synchronized with "
            f"{expected_upstream} ({remote_head.stdout.strip()})",
            repo_root,
        )

    post_push_status = _porcelain_status(repo_root)
    if post_push_status:
        return _fail(
            result,
            FinalizationStatus.PUBLICATION_FAILED,
            f"FAIL: working tree is dirty after push: {post_push_status}",
            repo_root,
        )

    result.post_head = local_head
    result.status = FinalizationStatus.PUSHED
    result.ok = True
    result.messages.append(
        f"PASS: pushed {branch} to {expected_upstream} and verified synchronization"
    )

    # 22. Write bounded finalization artifact and audit record.
    artifact_path = _write_finalize_artifact(result, repo_root)
    if artifact_path is not None:
        result.messages.append(f"Finalization artifact written to {artifact_path}")

    _maybe_write_audit(result, repo_root)
    return result


def format_finalization_result(result: FinalizationResult) -> str:
    """Return a concise, human-readable summary of *result*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Controller-Gated Finalization")
    lines.append("=" * 64)
    lines.append(f"Task:            {result.task_id or 'n/a'}")
    lines.append(f"File:            {result.task_filename or 'n/a'}")
    lines.append(f"Branch:          {result.branch or 'n/a'}")
    lines.append(f"Pre HEAD:        {result.pre_head or 'n/a'}")
    lines.append(f"Post HEAD:       {result.post_head or 'n/a'}")
    lines.append(f"Decision:        {result.decision_path or 'n/a'}")
    lines.append(f"Bundle:          {result.bundle_path or 'n/a'}")
    lines.append(f"Status:          {result.status.value}")
    lines.append(f"Mode:            {'apply' if result.apply else 'preview'}")
    if result.lifecycle_states:
        lines.append(f"Lifecycle:       {' -> '.join(result.lifecycle_states)}")
    if result.staged_paths:
        lines.append(f"Staged paths:    {result.staged_paths}")
    if result.commit_sha:
        lines.append(f"Commit SHA:      {result.commit_sha}")
    if result.push_command:
        lines.append(f"Push command:    {' '.join(result.push_command)}")
    if result.push_result is not None:
        lines.append(f"Push returncode: {result.push_result.get('returncode')}")
    if result.audit_path:
        try:
            rel_path = result.audit_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = result.audit_path
        lines.append(f"Audit record:    {rel_path}")
    elif not result.audit_write_ok:
        lines.append("Audit record:    NOT WRITTEN")
        if result.audit_write_error:
            lines.append(f"  error: {result.audit_write_error}")
    lines.append("-" * 64)
    lines.append("Messages:")
    if result.messages:
        for msg in result.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  (none)")
    lines.append("=" * 64)
    return "\n".join(lines)
