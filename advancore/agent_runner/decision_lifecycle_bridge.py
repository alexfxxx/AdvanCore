"""Bounded bridge from controller decision record to task lifecycle transition.

The bridge is intentionally fail-closed: it validates the decision record, its
linkage to a trusted review bundle, and the target task file before requesting
any lifecycle transition through the existing authority-aware lifecycle helper
from TASK-009. Preview is the default; an explicit ``apply=True`` is required to
mutate the linked task file, and then only the ``STATUS:`` line is changed.

This module does **not** stage, commit, push, merge, deploy, switch branches, or
grant workers controller authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_bridge_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    ControllerDecisionError,
    DecisionValue,
    load_controller_decision,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.lifecycle import (
    ActorRole,
    LifecycleResult,
    TaskStatus,
    transition_task,
)
from advancore.agent_runner.review_bundle import (
    ReviewBundle,
    ReviewBundleError,
    load_review_bundle,
)
from advancore.agent_runner.task import TaskError, find_task


class DecisionLifecycleBridgeError(Exception):
    """Raised when a controller decision cannot be bridged to a lifecycle transition."""


@dataclass
class DecisionLifecycleResult:
    """Outcome of a controller-decision-to-lifecycle bridge attempt."""

    ok: bool
    task_id: str | None = None
    task_filename: str | None = None
    current_status: str | None = None
    decision: str | None = None
    actor_role: str | None = None
    target_status: str | None = None
    transition_allowed: bool = False
    applied: bool = False
    mode: str = "preview"
    decision_path: Path | None = None
    bundle_path: Path | None = None
    head_evidence: dict[str, str | None] = field(default_factory=dict)
    lifecycle_result: LifecycleResult | None = None
    audit_path: Path | None = None
    audit_write_ok: bool = True
    audit_write_error: str | None = None
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


_DECISION_TO_STATUS: dict[str, TaskStatus] = {
    DecisionValue.APPROVE.value: TaskStatus.APPROVED,
    DecisionValue.REWORK.value: TaskStatus.REWORK,
    DecisionValue.BLOCKED.value: TaskStatus.BLOCKED,
}


def _normalize_decision(value: str) -> DecisionValue:
    """Return a ``DecisionValue`` enum member or raise ``DecisionLifecycleBridgeError``."""
    try:
        return DecisionValue(value.upper())
    except ValueError as exc:
        raise DecisionLifecycleBridgeError(
            f"Unknown controller decision: {value!r}. "
            f"Allowed values are: {', '.join(d.value for d in DecisionValue)}."
        ) from exc


def _normalize_actor(value: str) -> ActorRole:
    """Return an ``ActorRole`` enum member or raise ``DecisionLifecycleBridgeError``."""
    try:
        return ActorRole(value.lower())
    except ValueError as exc:
        raise DecisionLifecycleBridgeError(f"Unknown actor role: {value!r}") from exc


def _resolve_bundle_path(decision: ControllerDecision, repo_root: Path) -> Path:
    """Return the absolute path to the linked review bundle."""
    bundle_path = Path(decision.bundle_path)
    if not bundle_path.is_absolute():
        bundle_path = repo_root / bundle_path
    return bundle_path.resolve()


def _validate_identity(
    decision: ControllerDecision,
    bundle: ReviewBundle,
    task,
) -> None:
    """Fail closed if decision, bundle, and task identities do not agree."""
    decision_task_id = decision.task_id
    bundle_task_id = bundle.task_id
    task_task_id = task.task_id

    if decision_task_id is None or bundle_task_id is None or task_task_id is None:
        raise DecisionLifecycleBridgeError(
            "Missing task identity in decision, bundle, or task file"
        )

    if decision_task_id != bundle_task_id:
        raise DecisionLifecycleBridgeError(
            f"Decision/bundle task ID mismatch: decision {decision_task_id!r}, "
            f"bundle {bundle_task_id!r}"
        )

    if decision.bundle_task_id is not None and decision.bundle_task_id != bundle_task_id:
        raise DecisionLifecycleBridgeError(
            f"Decision bundle_task_id mismatch: {decision.bundle_task_id!r} != {bundle_task_id!r}"
        )

    if bundle_task_id != task_task_id:
        raise DecisionLifecycleBridgeError(
            f"Bundle/task task ID mismatch: bundle {bundle_task_id!r}, task {task_task_id!r}"
        )

    decision_filename = decision.task_filename
    bundle_filename = bundle.task_filename
    task_filename = task.filename

    if decision_filename is None or bundle_filename is None:
        raise DecisionLifecycleBridgeError(
            "Missing task filename in decision or bundle"
        )

    if decision_filename != bundle_filename:
        raise DecisionLifecycleBridgeError(
            f"Decision/bundle task filename mismatch: decision {decision_filename!r}, "
            f"bundle {bundle_filename!r}"
        )

    if decision.bundle_task_filename is not None and decision.bundle_task_filename != bundle_filename:
        raise DecisionLifecycleBridgeError(
            f"Decision bundle_task_filename mismatch: {decision.bundle_task_filename!r} != {bundle_filename!r}"
        )

    if bundle_filename != task_filename:
        raise DecisionLifecycleBridgeError(
            f"Bundle/task task filename mismatch: bundle {bundle_filename!r}, task {task_filename!r}"
        )


def _validate_branch(
    bundle: ReviewBundle,
    git_info: GitInfo,
) -> None:
    """Fail closed if the current branch differs from the bundle branch."""
    bundle_branch = bundle.branch
    if bundle_branch is None:
        raise DecisionLifecycleBridgeError("Review bundle is missing branch evidence")

    if git_info.current_branch != bundle_branch:
        raise DecisionLifecycleBridgeError(
            f"Branch mismatch: current branch {git_info.current_branch!r}, "
            f"bundle branch {bundle_branch!r}"
        )


def _map_decision_to_target_status(decision_value: str) -> TaskStatus:
    """Map a controller decision value to its requested lifecycle target status."""
    decision_enum = _normalize_decision(decision_value)
    target = _DECISION_TO_STATUS.get(decision_enum.value)
    if target is None:
        raise DecisionLifecycleBridgeError(
            f"Decision {decision_enum.value!r} has no mapped lifecycle target"
        )
    return target


def _build_head_evidence(
    git_info: GitInfo,
    bundle: ReviewBundle,
) -> dict[str, str | None]:
    """Return HEAD/branch evidence for surfacing freshness without enforcing policy."""
    return {
        "current_branch": git_info.current_branch,
        "current_head": git_info.head_sha,
        "bundle_branch": bundle.branch,
        "bundle_pre_head": bundle.pre_head,
        "bundle_post_head": bundle.post_head,
    }


def _maybe_write_bridge_audit(
    result: DecisionLifecycleResult,
    git_info: GitInfo | None,
) -> None:
    """Append a bridge-specific audit record if a Git snapshot is available."""
    if git_info is None:
        return

    payload = build_bridge_audit_payload(
        timestamp=datetime.now(timezone.utc),
        task_id=result.task_id,
        task_filename=result.task_filename,
        actor_role=result.actor_role,
        decision=result.decision,
        target_status=result.target_status,
        transition_allowed=result.transition_allowed,
        applied=result.applied,
        branch=git_info.current_branch,
        head_sha=git_info.head_sha,
        decision_path=str(result.decision_path) if result.decision_path else None,
        bundle_path=str(result.bundle_path) if result.bundle_path else None,
        bundle_pre_head=result.head_evidence.get("bundle_pre_head"),
        bundle_post_head=result.head_evidence.get("bundle_post_head"),
    )

    try:
        audit_path = write_audit_record(payload, default_audit_dir(git_info.repo_root))
        result.audit_path = audit_path
        rel_path = audit_path.relative_to(git_info.repo_root)
        result.messages.append(f"Bridge audit record written to {rel_path}")
    except AuditWriteError as exc:
        result.audit_write_ok = False
        result.audit_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")


def apply_controller_decision(
    repo_root: Path,
    tasks_dir: Path,
    decision_path: Path,
    *,
    apply: bool = False,
    git_info: GitInfo | None = None,
) -> DecisionLifecycleResult:
    """Validate a controller decision record and preview/apply the mapped transition.

    Arguments:
        repo_root: Repository root used to resolve relative bundle paths.
        tasks_dir: Directory containing ``TASK-###-name.md`` files.
        decision_path: Path to the controller decision record.
        apply: If ``True`` and the transition is allowed, rewrite the task file.
            Defaults to ``False`` (dry-run preview).
        git_info: Optional repository snapshot for audit metadata and branch
            validation. When supplied, a bridge audit record is appended.

    Returns:
        A ``DecisionLifecycleResult`` describing the outcome. The result is
        truthy only when all linkage evidence validated and the lifecycle
        transition was allowed (and applied, if requested).
    """
    result = DecisionLifecycleResult(
        ok=False,
        mode="apply" if apply else "preview",
        decision_path=decision_path,
        messages=[],
    )

    # 1. Load and parse the decision record.
    try:
        decision = load_controller_decision(decision_path)
    except ControllerDecisionError as exc:
        result.messages.append(f"FAIL: cannot load decision record: {exc}")
        _maybe_write_bridge_audit(result, git_info)
        return result

    result.decision = decision.decision
    result.actor_role = decision.actor_role
    result.task_id = decision.task_id
    result.task_filename = decision.task_filename

    # 2. Validate the decision value is known.
    try:
        target_status = _map_decision_to_target_status(decision.decision)
    except DecisionLifecycleBridgeError as exc:
        result.messages.append(f"FAIL: {exc}")
        _maybe_write_bridge_audit(result, git_info)
        return result

    result.target_status = target_status.value

    # 3. Validate the actor role is controller or owner, never worker.
    try:
        actor_enum = _normalize_actor(decision.actor_role)
    except DecisionLifecycleBridgeError as exc:
        result.messages.append(f"FAIL: {exc}")
        _maybe_write_bridge_audit(result, git_info)
        return result

    if actor_enum == ActorRole.WORKER:
        result.messages.append("FAIL: worker cannot apply a controller decision")
        _maybe_write_bridge_audit(result, git_info)
        return result

    # 4. Resolve and load the linked review bundle.
    try:
        bundle_path = _resolve_bundle_path(decision, repo_root)
        result.bundle_path = bundle_path
        bundle = load_review_bundle(bundle_path)
    except (ControllerDecisionError, ReviewBundleError, OSError) as exc:
        result.messages.append(f"FAIL: cannot load linked review bundle: {exc}")
        _maybe_write_bridge_audit(result, git_info)
        return result

    # 5. Validate branch evidence if a Git snapshot is available.
    if git_info is not None:
        try:
            _validate_branch(bundle, git_info)
        except DecisionLifecycleBridgeError as exc:
            result.messages.append(f"FAIL: {exc}")
            _maybe_write_bridge_audit(result, git_info)
            return result

    # 6. Find the linked task file.
    try:
        task = find_task(tasks_dir, decision.task_id)
    except TaskError as exc:
        result.messages.append(f"FAIL: cannot find linked task: {exc}")
        _maybe_write_bridge_audit(result, git_info)
        return result

    result.task_id = task.task_id
    result.task_filename = task.filename
    result.current_status = task.status

    # 7. Validate decision/bundle/task identity linkage.
    try:
        _validate_identity(decision, bundle, task)
    except DecisionLifecycleBridgeError as exc:
        result.messages.append(f"FAIL: {exc}")
        _maybe_write_bridge_audit(result, git_info)
        return result

    # 8. Surface HEAD/branch freshness evidence without enforcing a HEAD policy.
    if git_info is not None:
        result.head_evidence = _build_head_evidence(git_info, bundle)
        result.messages.append(
            f"HEAD evidence: current={git_info.head_sha}, "
            f"bundle_pre={bundle.pre_head or 'n/a'}, "
            f"bundle_post={bundle.post_head or 'n/a'}"
        )

    # 9. Request the lifecycle transition through the existing authority model.
    lifecycle_result = transition_task(
        tasks_dir,
        task.task_id,
        target_status,
        actor_enum,
        apply=apply,
        git_info=git_info,
    )
    result.lifecycle_result = lifecycle_result
    result.transition_allowed = lifecycle_result.allowed
    result.applied = lifecycle_result.applied
    result.messages.extend(lifecycle_result.messages)

    if not lifecycle_result.allowed:
        result.messages.append(
            "Transition not applied: lifecycle state machine denied the request"
        )
        _maybe_write_bridge_audit(result, git_info)
        return result

    if apply:
        if lifecycle_result.applied:
            result.messages.append(
                f"Applied {lifecycle_result.previous_status} -> {result.target_status} "
                f"for {task.task_id} via controller decision"
            )
        else:
            result.messages.append(
                "Transition was allowed but the task file was not rewritten"
            )
            _maybe_write_bridge_audit(result, git_info)
            return result
    else:
        result.messages.append(
            f"Preview: {lifecycle_result.previous_status} -> {result.target_status} "
            f"for {task.task_id} (use --apply to mutate)"
        )

    result.ok = True
    _maybe_write_bridge_audit(result, git_info)
    return result
