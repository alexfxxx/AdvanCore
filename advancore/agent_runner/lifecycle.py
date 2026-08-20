"""Task lifecycle state machine and authority-aware transition helper.

This module provides an explicit, fail-closed control plane for task-status
changes. It knows nothing about workers, Git mutations, or remote systems; it
only validates whether a requested transition is allowed for a given actor and,
optionally, rewrites the single ``STATUS:`` line in a task file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_lifecycle_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.task import TaskError, find_task


class TaskStatus(str, Enum):
    """Authoritative lifecycle statuses for AdvanCore task files."""

    DRAFT = "DRAFT"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    REWORK = "REWORK"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


class ActorRole(str, Enum):
    """Actor roles that may request task lifecycle transitions.

    ``controller`` represents both controller and reviewer authority.
    """

    WORKER = "worker"
    CONTROLLER = "controller"
    OWNER = "owner"


# Non-final working states from which a task may be moved to BLOCKED.
_NON_FINAL_WORKING_STATES = {
    TaskStatus.DRAFT,
    TaskStatus.READY,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
    TaskStatus.REWORK,
}

# Normal transitions and the roles that may perform them.
# Owner is modelled as a superset of controller authority plus the worker
# transitions, because owner authority includes controller/reviewer transitions
# and should not be more restrictive than the roles it already supersedes.
_TRANSITION_AUTHORITY: dict[tuple[TaskStatus, TaskStatus], set[ActorRole]] = {
    (TaskStatus.DRAFT, TaskStatus.READY): {ActorRole.CONTROLLER, ActorRole.OWNER},
    (TaskStatus.READY, TaskStatus.IN_PROGRESS): {ActorRole.WORKER, ActorRole.OWNER},
    (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW): {ActorRole.WORKER, ActorRole.OWNER},
    (TaskStatus.REVIEW, TaskStatus.APPROVED): {ActorRole.CONTROLLER, ActorRole.OWNER},
    (TaskStatus.REVIEW, TaskStatus.REWORK): {ActorRole.CONTROLLER, ActorRole.OWNER},
    (TaskStatus.REWORK, TaskStatus.IN_PROGRESS): {ActorRole.WORKER, ActorRole.OWNER},
    (TaskStatus.BLOCKED, TaskStatus.READY): {ActorRole.CONTROLLER, ActorRole.OWNER},
    (TaskStatus.BLOCKED, TaskStatus.REWORK): {ActorRole.CONTROLLER, ActorRole.OWNER},
}

_STATUS_LINE_RE = re.compile(r"^STATUS:\s*(\w+)", re.IGNORECASE)


class LifecycleError(Exception):
    """Raised when a lifecycle transition cannot be validated or applied."""


@dataclass
class LifecycleResult:
    """Outcome of a task lifecycle transition request."""

    ok: bool
    task_id: str | None = None
    task_filename: str | None = None
    previous_status: str | None = None
    requested_status: str | None = None
    actor: ActorRole | None = None
    allowed: bool = False
    applied: bool = False
    mode: str = "preview"
    messages: list[str] = field(default_factory=list)
    audit_path: Path | None = None
    audit_write_ok: bool = True
    audit_write_error: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def _normalize_status(value: str | TaskStatus) -> TaskStatus:
    """Return a ``TaskStatus`` enum member or raise ``LifecycleError``."""
    if isinstance(value, TaskStatus):
        return value
    try:
        return TaskStatus(value.upper())
    except ValueError as exc:
        raise LifecycleError(f"Unknown task status: {value!r}") from exc


def _normalize_actor(value: str | ActorRole) -> ActorRole:
    """Return an ``ActorRole`` enum member or raise ``LifecycleError``."""
    if isinstance(value, ActorRole):
        return value
    try:
        return ActorRole(value.lower())
    except ValueError as exc:
        raise LifecycleError(f"Unknown actor role: {value!r}") from exc


def is_transition_allowed(
    current: TaskStatus | str,
    requested: TaskStatus | str,
    actor: ActorRole | str,
) -> tuple[bool, str]:
    """Return whether *actor* may move a task from *current* to *requested*.

    The returned string is a human-readable reason suitable for terminal output
    and audit records.
    """
    current_status = _normalize_status(current)
    requested_status = _normalize_status(requested)
    actor_role = _normalize_actor(actor)

    if current_status == requested_status:
        return False, f"No transition requested: task is already {current_status.value}"

    # Transitions to BLOCKED are allowed from any non-final working state by a
    # controller/reviewer or owner.
    if requested_status == TaskStatus.BLOCKED:
        if current_status in _NON_FINAL_WORKING_STATES:
            if actor_role in {ActorRole.CONTROLLER, ActorRole.OWNER}:
                return True, f"{current_status.value} -> {requested_status.value} allowed for {actor_role.value}"
            return (
                False,
                f"{current_status.value} -> {requested_status.value} denied for {actor_role.value}: "
                "only controller/reviewer or owner may block a task",
            )
        return (
            False,
            f"{current_status.value} -> {requested_status.value} denied: "
            "only non-final working states may be blocked",
        )

    allowed_roles = _TRANSITION_AUTHORITY.get((current_status, requested_status))
    if allowed_roles is None:
        return (
            False,
            f"{current_status.value} -> {requested_status.value} is not a valid transition",
        )

    if actor_role in allowed_roles:
        return True, f"{current_status.value} -> {requested_status.value} allowed for {actor_role.value}"

    return (
        False,
        f"{current_status.value} -> {requested_status.value} denied for {actor_role.value}",
    )


def _read_status_line(path: Path) -> tuple[int, TaskStatus]:
    """Locate the single ``STATUS:`` line in *path*.

    Returns:
        A tuple of ``(line_index, status_enum)``.

    Raises:
        LifecycleError: if the line is missing, duplicated, or carries an
            unknown status value.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise LifecycleError(f"Cannot read task file {path}: {exc}") from exc

    matches: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        match = _STATUS_LINE_RE.match(line)
        if match:
            matches.append((index, match.group(1).upper()))

    if not matches:
        raise LifecycleError(f"No STATUS line found in {path.name}")
    if len(matches) > 1:
        raise LifecycleError(
            f"Ambiguous STATUS lines in {path.name}: "
            f"found at lines {[m[0] + 1 for m in matches]}"
        )

    line_index, status_value = matches[0]
    try:
        status_enum = TaskStatus(status_value)
    except ValueError as exc:
        raise LifecycleError(
            f"Unknown status value {status_value!r} in {path.name}"
        ) from exc

    return line_index, status_enum


def _rewrite_status_line(path: Path, line_index: int, new_status: TaskStatus) -> None:
    """Replace the status on *line_index* with *new_status* and rewrite *path*."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    original = lines[line_index]
    replaced = re.sub(
        r"^(STATUS:\s*)\w+",
        lambda m: f"{m.group(1)}{new_status.value}",
        original,
        flags=re.IGNORECASE,
        count=1,
    )
    lines[line_index] = replaced
    # Re-assemble with LF line endings. This is the unavoidable normalization
    # documented in the task spec; the original trailing newline is preserved.
    path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")


def transition_task(
    tasks_dir: Path,
    task_id: str,
    to_status: TaskStatus | str,
    actor: ActorRole | str,
    *,
    apply: bool = False,
    git_info: GitInfo | None = None,
) -> LifecycleResult:
    """Validate and optionally apply a task-status transition.

    Arguments:
        tasks_dir: Directory containing ``TASK-###-name.md`` files.
        task_id: Task identifier, filename, or path fragment.
        to_status: Requested status.
        actor: Role requesting the transition.
        apply: If ``True`` and the transition is allowed, rewrite the task file.
            Defaults to ``False`` (dry-run preview).
        git_info: Optional repository snapshot for audit metadata. When supplied,
            a lifecycle audit record is appended regardless of whether the
            transition was allowed or applied.

    Returns:
        A ``LifecycleResult`` describing the outcome. The result is truthy only
        when the transition was allowed and, if ``apply`` was requested, the
        file was successfully rewritten.
    """
    requested_enum = _normalize_status(to_status)
    actor_enum = _normalize_actor(actor)
    result = LifecycleResult(
        ok=False,
        requested_status=requested_enum.value,
        actor=actor_enum,
        mode="apply" if apply else "preview",
        messages=[],
    )

    try:
        task = find_task(tasks_dir, task_id)
    except TaskError as exc:
        result.messages.append(f"FAIL: {exc}")
        _maybe_write_audit(result, git_info)
        return result

    result.task_id = task.task_id
    result.task_filename = task.filename
    result.previous_status = task.status

    try:
        line_index, current_status = _read_status_line(task.path)
    except LifecycleError as exc:
        result.messages.append(f"FAIL: {exc}")
        _maybe_write_audit(result, git_info)
        return result

    # The parsed task status must agree with the dedicated status-line read.
    if current_status.value != task.status.upper():
        result.messages.append(
            f"FAIL: status mismatch in {task.filename} "
            f"(parse says {task.status}, status line says {current_status.value})"
        )
        _maybe_write_audit(result, git_info)
        return result

    allowed, reason = is_transition_allowed(current_status, requested_enum, actor_enum)
    result.allowed = allowed
    result.messages.append(reason)

    if not allowed:
        result.messages.append("Transition not applied.")
        _maybe_write_audit(result, git_info)
        return result

    if apply:
        try:
            _rewrite_status_line(task.path, line_index, requested_enum)
            result.applied = True
            result.messages.append(
                f"Applied {current_status.value} -> {requested_enum.value} in {task.filename}"
            )
        except Exception as exc:  # pragma: no cover - defensive
            result.messages.append(f"FAIL: could not rewrite task file: {exc}")
            _maybe_write_audit(result, git_info)
            return result
    else:
        result.messages.append(
            f"Preview: {current_status.value} -> {requested_enum.value} "
            f"in {task.filename} (use --apply to mutate)"
        )

    result.ok = True
    _maybe_write_audit(result, git_info)
    return result


def _maybe_write_audit(result: LifecycleResult, git_info: GitInfo | None) -> None:
    """Append a lifecycle audit record if a Git snapshot is available."""
    if git_info is None:
        return

    payload = build_lifecycle_audit_payload(
        timestamp=datetime.now(timezone.utc),
        task_id=result.task_id,
        task_filename=result.task_filename,
        actor_role=result.actor.value if result.actor else None,
        previous_status=result.previous_status,
        requested_status=result.requested_status,
        transition_allowed=result.allowed,
        applied=result.applied,
        branch=git_info.current_branch,
        head_sha=git_info.head_sha,
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
