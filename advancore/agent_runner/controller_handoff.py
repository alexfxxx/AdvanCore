"""Controller handoff queue for the local agent runner.

A controller handoff request is a deterministic, machine-readable JSON artifact
that represents an outstanding review bundle awaiting an independent controller
decision. It decouples the production of review evidence from the return of a
controller decision so that a future adapter or transport can be added without
redesigning the local governance model.

Handoff requests are stored under ``.agent_runner/controller_handoff/`` which is
gitignored via the existing ``.agent_runner/`` rule. They intentionally exclude
credentials, environment dumps, connection strings, full task bodies, full worker
transcripts, customer data, and arbitrary command output.

A handoff request is an orchestration artifact only. It is not controller
approval, owner approval, or permission to commit, push, merge, deploy, mutate
lifecycle state, or impersonate the controller.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_handoff_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    ControllerDecisionError,
    load_controller_decision,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.review_bundle import (
    ControllerAction,
    ReviewBundle,
    ReviewBundleError,
    load_review_bundle,
)


HANDOFF_SUBDIR = "controller_handoff"
HANDOFF_REQUEST_VERSION = "1"


class HandoffState(str, Enum):
    """States of a controller handoff request."""

    WAITING_DECISION = "WAITING_DECISION"
    DECISION_RECEIVED = "DECISION_RECEIVED"
    BLOCKED = "BLOCKED"


class ControllerHandoffError(Exception):
    """Raised when a controller handoff request cannot be built or reconciled."""


class ControllerHandoffWriteError(Exception):
    """Raised when a controller handoff request cannot be written durably."""


@dataclass
class ControllerHandoff:
    """Machine-readable local controller handoff request."""

    request_version: str
    request_id: str
    timestamp: str
    task_id: str
    task_filename: str
    bundle_path: str
    bundle_branch: str
    bundle_pre_head: str
    bundle_post_head: str | None
    bundle_recommended_action: str
    state: str
    decision_path: str | None = None
    decision: str | None = None
    audit_path: str | None = None
    messages: list[str] = field(default_factory=list)


@dataclass
class HandoffReconciliationResult:
    """Outcome of a handoff reconciliation attempt."""

    ok: bool
    handoff: ControllerHandoff | None = None
    audit_path: Path | None = None
    audit_write_ok: bool = True
    audit_write_error: str | None = None
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def default_handoff_dir(repo_root: Path) -> Path:
    """Return the default controller-handoff directory for *repo_root*."""
    return repo_root / ".agent_runner" / HANDOFF_SUBDIR


def _sanitize_filename(value: str | None) -> str:
    """Return a filesystem-safe fragment from *value*."""
    if not value:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9_\-]", "_", value)[:64]


def _normalize_actor_role(value: str) -> ActorRole:
    """Return an ``ActorRole`` enum member or raise ``ControllerHandoffError``."""
    try:
        return ActorRole(value.lower())
    except ValueError as exc:
        raise ControllerHandoffError(f"Unknown actor role: {value!r}") from exc


def _normalize_bundle_path(path: Path, repo_root: Path | None) -> str:
    """Return a repository-relative path when possible for portability."""
    stored = str(path)
    if repo_root is not None:
        try:
            stored = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            pass
    return stored


def _require_bundle_field(name: str, value: str | None) -> str:
    """Return *value* if it is a non-empty string, else raise."""
    if not value or not isinstance(value, str):
        raise ControllerHandoffError(
            f"Review bundle is missing required handoff field: {name}"
        )
    return value


def _validate_bundle_action(bundle: ReviewBundle) -> None:
    """Fail closed if the bundle recommends an unsupported action."""
    action = bundle.recommended_action
    if action not in {a.value for a in ControllerAction}:
        raise ControllerHandoffError(
            f"Unsupported review-bundle recommended action: {action!r}. "
            f"Allowed values are: {', '.join(a.value for a in ControllerAction)}."
        )


def _generate_request_id() -> str:
    """Return a short, unique handoff request identifier."""
    return f"CHR-{uuid.uuid4().hex}"


def build_controller_handoff(
    bundle_path: Path,
    bundle: ReviewBundle,
    *,
    git_info: GitInfo | None = None,
    repo_root: Path | None = None,
) -> ControllerHandoff:
    """Build a ``ControllerHandoff`` request from a valid review bundle.

    Raises:
        ControllerHandoffError: if the bundle is missing required linkage
            evidence, carries an unsupported recommended action, or its branch
            evidence does not match the current Git snapshot.
    """
    task_id = _require_bundle_field("task_id", bundle.task_id)
    task_filename = _require_bundle_field("task_filename", bundle.task_filename)
    bundle_branch = _require_bundle_field("branch", bundle.branch)
    bundle_pre_head = _require_bundle_field("pre_head", bundle.pre_head)
    _validate_bundle_action(bundle)

    if git_info is not None and git_info.current_branch != bundle_branch:
        raise ControllerHandoffError(
            f"Branch mismatch: current branch {git_info.current_branch!r}, "
            f"bundle branch {bundle_branch!r}"
        )

    stored_bundle_path = _normalize_bundle_path(bundle_path, repo_root)

    return ControllerHandoff(
        request_version=HANDOFF_REQUEST_VERSION,
        request_id=_generate_request_id(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        task_id=task_id,
        task_filename=task_filename,
        bundle_path=stored_bundle_path,
        bundle_branch=bundle_branch,
        bundle_pre_head=bundle_pre_head,
        bundle_post_head=bundle.post_head,
        bundle_recommended_action=bundle.recommended_action,
        state=HandoffState.WAITING_DECISION.value,
        decision_path=None,
        decision=None,
        audit_path=None,
        messages=[
            f"Handoff request prepared for {task_id} from {stored_bundle_path}"
        ],
    )


def serialize_controller_handoff(handoff: ControllerHandoff) -> dict[str, Any]:
    """Return a JSON-serializable dict for *handoff*."""
    data = asdict(handoff)
    data["state"] = str(handoff.state)
    data["bundle_recommended_action"] = str(handoff.bundle_recommended_action)
    data["request_version"] = str(handoff.request_version)
    return data


def write_controller_handoff(
    handoff: ControllerHandoff,
    handoff_dir: Path,
) -> Path:
    """Write *handoff* as JSON under *handoff_dir* and return the path.

    Raises:
        ControllerHandoffWriteError: if the handoff request cannot be written.
    """
    try:
        handoff_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise ControllerHandoffWriteError(
            f"Failed to create handoff directory {handoff_dir}: {exc}"
        ) from exc

    ts = datetime.fromisoformat(handoff.timestamp).strftime("%Y%m%dT%H%M%S")
    task_part = _sanitize_filename(handoff.task_id)
    state_part = _sanitize_filename(handoff.state)
    filename = f"{ts}_{task_part}_{state_part}.json"
    path = handoff_dir / filename

    payload = serialize_controller_handoff(handoff)
    try:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise ControllerHandoffWriteError(
            f"Failed to write handoff request to {path}: {exc}"
        ) from exc

    return path


def load_controller_handoff(path: Path) -> ControllerHandoff:
    """Load a ``ControllerHandoff`` from *path*.

    Raises:
        ControllerHandoffError: if the file cannot be read or parsed.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControllerHandoffError(
            f"Cannot read handoff request {path}: {exc}"
        ) from exc

    try:
        return ControllerHandoff(**data)
    except Exception as exc:
        raise ControllerHandoffError(
            f"Invalid handoff request format in {path}: {exc}"
        ) from exc


def find_latest_handoff(handoff_dir: Path) -> Path | None:
    """Return the most recently modified handoff request under *handoff_dir*."""
    if not handoff_dir.exists():
        return None
    candidates = sorted(
        handoff_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def _resolve_relative_path(value: str, repo_root: Path | None) -> Path:
    """Return an absolute path from a possibly repository-relative string."""
    path = Path(value)
    if not path.is_absolute() and repo_root is not None:
        path = (repo_root / path).resolve()
    return path.resolve()


def _same_bundle_path(
    request_bundle_path: str,
    decision_bundle_path: str,
    repo_root: Path | None,
) -> bool:
    """Return whether the two bundle paths refer to the same file."""
    try:
        left = _resolve_relative_path(request_bundle_path, repo_root)
        right = _resolve_relative_path(decision_bundle_path, repo_root)
        return left == right
    except (OSError, ValueError):
        return request_bundle_path == decision_bundle_path


def reconcile_controller_handoff(
    request_path: Path,
    decision_path: Path,
    *,
    repo_root: Path | None = None,
    git_info: GitInfo | None = None,
) -> HandoffReconciliationResult:
    """Reconcile an existing controller decision with an outstanding handoff.

    The handoff request is updated in place and rewritten to *request_path* when
    reconciliation succeeds. Reconciliation does not apply any lifecycle
    transition; TASK-012 remains the only decision-to-lifecycle bridge.

    Returns:
        A ``HandoffReconciliationResult`` describing the outcome. The result is
        truthy only when all linkage evidence validated and the handoff was
        successfully updated.
    """
    result = HandoffReconciliationResult(ok=False, messages=[])

    # 1. Load and parse the handoff request.
    try:
        handoff = load_controller_handoff(request_path)
    except ControllerHandoffError as exc:
        result.messages.append(f"FAIL: cannot load handoff request: {exc}")
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    result.handoff = handoff

    # 2. Load and parse the controller decision record.
    try:
        decision = load_controller_decision(decision_path)
    except ControllerDecisionError as exc:
        result.messages.append(f"FAIL: cannot load controller decision: {exc}")
        _maybe_write_handoff_audit(
            result,
            git_info,
            request_path=request_path,
            decision_path=decision_path,
        )
        return result

    # 3. Validate the decision actor is controller or owner, never worker.
    try:
        actor_enum = _normalize_actor_role(decision.actor_role)
    except ControllerHandoffError as exc:
        result.messages.append(f"FAIL: {exc}")
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    if actor_enum == ActorRole.WORKER:
        result.messages.append("FAIL: worker cannot act as a controller decision actor")
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    # 4. Validate task identity linkage.
    if decision.task_id != handoff.task_id:
        result.messages.append(
            f"FAIL: task ID mismatch: decision {decision.task_id!r}, "
            f"handoff {handoff.task_id!r}"
        )
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    if decision.task_filename != handoff.task_filename:
        result.messages.append(
            f"FAIL: task filename mismatch: decision {decision.task_filename!r}, "
            f"handoff {handoff.task_filename!r}"
        )
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    if decision.bundle_task_id != handoff.task_id:
        result.messages.append(
            f"FAIL: decision bundle_task_id mismatch: {decision.bundle_task_id!r} "
            f"!= {handoff.task_id!r}"
        )
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    if decision.bundle_task_filename != handoff.task_filename:
        result.messages.append(
            f"FAIL: decision bundle_task_filename mismatch: "
            f"{decision.bundle_task_filename!r} != {handoff.task_filename!r}"
        )
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    # 5. Validate the decision links to the same review bundle.
    if not _same_bundle_path(handoff.bundle_path, decision.bundle_path, repo_root):
        result.messages.append(
            f"FAIL: review-bundle reference mismatch: handoff {handoff.bundle_path!r}, "
            f"decision {decision.bundle_path!r}"
        )
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    # 6. Validate branch/task evidence consistency.
    if decision.bundle_branch != handoff.bundle_branch:
        result.messages.append(
            f"FAIL: branch evidence mismatch: decision {decision.bundle_branch!r}, "
            f"handoff {handoff.bundle_branch!r}"
        )
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    if decision.bundle_pre_head != handoff.bundle_pre_head:
        result.messages.append(
            f"FAIL: pre HEAD evidence mismatch: decision {decision.bundle_pre_head!r}, "
            f"handoff {handoff.bundle_pre_head!r}"
        )
        _maybe_write_handoff_audit(result, git_info, request_path=request_path)
        return result

    if handoff.bundle_post_head is not None:
        if decision.bundle_post_head != handoff.bundle_post_head:
            result.messages.append(
                f"FAIL: post HEAD evidence mismatch: decision {decision.bundle_post_head!r}, "
                f"handoff {handoff.bundle_post_head!r}"
            )
            _maybe_write_handoff_audit(result, git_info, request_path=request_path)
            return result

    # 7. Store a repository-relative decision path when possible.
    stored_decision_path = _normalize_bundle_path(decision_path, repo_root)

    # 8. Handle already-reconciled requests deterministically.
    if handoff.state == HandoffState.DECISION_RECEIVED.value:
        if (
            handoff.decision_path == stored_decision_path
            and handoff.decision == decision.decision
        ):
            result.ok = True
            result.messages.append(
                f"Handoff {handoff.request_id} is already reconciled to this decision "
                f"({decision.decision})"
            )
            _maybe_write_handoff_audit(
                result,
                git_info,
                request_path=request_path,
                decision_path=stored_decision_path,
            )
            return result

        result.messages.append(
            "FAIL: handoff is already reconciled to a different decision "
            f"({handoff.decision_path}); refusing to overwrite"
        )
        _maybe_write_handoff_audit(
            result,
            git_info,
            request_path=request_path,
            decision_path=stored_decision_path,
        )
        return result

    # 9. Update the handoff request.
    handoff.state = HandoffState.DECISION_RECEIVED.value
    handoff.decision_path = stored_decision_path
    handoff.decision = decision.decision
    handoff.messages.append(
        f"Reconciled with decision {decision.decision} from {stored_decision_path}"
    )

    # 10. Write the updated handoff request back to the same path.
    try:
        payload = serialize_controller_handoff(handoff)
        request_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        result.messages.append(f"FAIL: could not rewrite handoff request: {exc}")
        _maybe_write_handoff_audit(
            result,
            git_info,
            request_path=request_path,
            decision_path=stored_decision_path,
        )
        return result

    result.ok = True
    result.messages.append(
        f"Handoff {handoff.request_id} reconciled to decision {decision.decision}"
    )
    _maybe_write_handoff_audit(
        result,
        git_info,
        request_path=request_path,
        decision_path=stored_decision_path,
    )
    return result


def _maybe_write_handoff_audit(
    result: HandoffReconciliationResult,
    git_info: GitInfo | None,
    *,
    request_path: Path | None = None,
    decision_path: str | None = None,
) -> None:
    """Append a handoff-specific audit record if a Git snapshot is available."""
    if git_info is None:
        return

    handoff = result.handoff
    payload = build_handoff_audit_payload(
        timestamp=datetime.now(timezone.utc),
        task_id=handoff.task_id if handoff else None,
        task_filename=handoff.task_filename if handoff else None,
        request_id=handoff.request_id if handoff else None,
        mode="handoff_reconcile",
        state=handoff.state if handoff else None,
        bundle_path=handoff.bundle_path if handoff else None,
        bundle_branch=handoff.bundle_branch if handoff else None,
        bundle_pre_head=handoff.bundle_pre_head if handoff else None,
        bundle_post_head=handoff.bundle_post_head if handoff else None,
        decision_path=decision_path,
        decision=handoff.decision if handoff else None,
        branch=git_info.current_branch,
        head_sha=git_info.head_sha,
    )

    try:
        audit_path = write_audit_record(payload, default_audit_dir(git_info.repo_root))
        result.audit_path = audit_path
    except AuditWriteError as exc:
        result.audit_write_ok = False
        result.audit_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")


def format_handoff_summary(handoff: ControllerHandoff) -> str:
    """Return a concise, human-readable summary of *handoff*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Controller Handoff Request")
    lines.append("=" * 64)
    lines.append(f"Request ID:    {handoff.request_id}")
    lines.append(f"Version:       {handoff.request_version}")
    lines.append(f"Task:          {handoff.task_id or 'n/a'}")
    lines.append(f"File:          {handoff.task_filename or 'n/a'}")
    lines.append(f"Bundle:        {handoff.bundle_path}")
    lines.append(f"Branch:        {handoff.bundle_branch or 'n/a'}")
    lines.append(f"Pre HEAD:      {handoff.bundle_pre_head or 'n/a'}")
    lines.append(f"Post HEAD:     {handoff.bundle_post_head or 'n/a'}")
    lines.append(f"Recommended:   {handoff.bundle_recommended_action}")
    lines.append(f"State:         {handoff.state}")
    if handoff.decision_path:
        lines.append(f"Decision:      {handoff.decision}")
        lines.append(f"Decision path: {handoff.decision_path}")
    if handoff.audit_path:
        lines.append(f"Audit record:  {handoff.audit_path}")
    if handoff.messages:
        lines.append("-" * 64)
        lines.append("Messages:")
        for msg in handoff.messages:
            lines.append(f"  {msg}")
    lines.append("=" * 64)
    return "\n".join(lines)
