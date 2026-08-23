"""Controller decision record for the local agent runner.

A controller decision record is a deterministic, machine-readable JSON artifact
that records an independent controller/reviewer decision against an existing
review bundle. It is the return-path handoff artifact from controller review
back into the local control plane.

Decision records are stored under ``.agent_runner/decisions/`` which is
gitignored via the existing ``.agent_runner/`` rule. They intentionally exclude
credentials, environment dumps, connection strings, full task bodies, full worker
transcripts, customer data, and arbitrary command output.

This module does **not** grant commit, push, merge, deployment, owner, or
approval authority to a worker. An ``APPROVE`` decision is only a local record;
it does not perform any publication or lifecycle transition.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.review_bundle import ReviewBundle


DECISIONS_SUBDIR = "decisions"
DECISION_RECORD_VERSION = "1"


class DecisionValue(str, Enum):
    """Allowed controller decisions for a decision record.

    These values represent the controller/reviewer's decision about the
    implementation described by a review bundle. They do not trigger any
    automatic action.
    """

    APPROVE = "APPROVE"
    REWORK = "REWORK"
    BLOCKED = "BLOCKED"


class ControllerDecisionError(Exception):
    """Raised when a controller decision record cannot be built or validated."""


class ControllerDecisionWriteError(Exception):
    """Raised when a controller decision record cannot be written durably."""


@dataclass
class ControllerDecision:
    """Machine-readable controller decision record for a single review bundle."""

    timestamp: str
    task_id: str | None
    task_filename: str | None
    bundle_path: str
    bundle_task_id: str | None
    bundle_task_filename: str | None
    bundle_branch: str | None
    bundle_pre_head: str | None
    bundle_post_head: str | None
    decision: str
    actor_role: str
    note: str | None = None
    record_version: str = DECISION_RECORD_VERSION


def default_decisions_dir(repo_root: Path) -> Path:
    """Return the default decision-record directory for *repo_root*."""
    return repo_root / ".agent_runner" / DECISIONS_SUBDIR


def _sanitize_filename(value: str | None) -> str:
    """Return a filesystem-safe fragment from *value*."""
    if not value:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9_\-]", "_", value)[:64]


def _normalize_decision(value: str | DecisionValue) -> DecisionValue:
    """Return a ``DecisionValue`` enum member or raise ``ControllerDecisionError``."""
    if isinstance(value, DecisionValue):
        return value
    try:
        return DecisionValue(value.upper())
    except ValueError as exc:
        raise ControllerDecisionError(
            f"Unknown controller decision: {value!r}. "
            f"Allowed values are: {', '.join(d.value for d in DecisionValue)}."
        ) from exc


def _normalize_actor_role(value: str | ActorRole) -> ActorRole:
    """Return an ``ActorRole`` enum member or raise ``ControllerDecisionError``."""
    if isinstance(value, ActorRole):
        return value
    try:
        return ActorRole(value.lower())
    except ValueError as exc:
        raise ControllerDecisionError(f"Unknown actor role: {value!r}") from exc


def _require_bundle_field(name: str, value: str | None) -> str:
    """Return *value* if it is a non-empty string, else raise."""
    if not value or not isinstance(value, str):
        raise ControllerDecisionError(
            f"Review bundle is missing required linkage field: {name}"
        )
    return value


def build_controller_decision(
    bundle_path: Path,
    bundle: ReviewBundle,
    *,
    decision: str | DecisionValue,
    actor_role: str | ActorRole,
    note: str | None = None,
    task_id: str | None = None,
    task_filename: str | None = None,
    repo_root: Path | None = None,
) -> ControllerDecision:
    """Build a ``ControllerDecision`` from an existing review bundle.

    The function validates the decision value, actor role, bundle integrity, and
    task identity linkage. It fails closed on any inconsistency or missing
    required evidence.

    Arguments:
        bundle_path: Path to the linked review bundle. Stored as a
            repository-relative path when *repo_root* is supplied and the path
            is inside it; otherwise stored as given.
        bundle: The loaded ``ReviewBundle`` to link against.
        decision: Controller decision value. Must be one of ``APPROVE``,
            ``REWORK``, or ``BLOCKED``.
        actor_role: Role recording the decision. ``worker`` is rejected;
            ``controller`` and ``owner`` are accepted.
        note: Optional bounded human-readable rationale.
        task_id: Optional task identifier from the decision request. When
            supplied, it must match the bundle's task ID.
        task_filename: Optional task filename from the decision request. When
            supplied, it must match the bundle's task filename.
        repo_root: Optional repository root used to make *bundle_path* relative.

    Raises:
        ControllerDecisionError: if validation fails or required bundle linkage
            evidence is missing/inconsistent.
    """
    decision_enum = _normalize_decision(decision)
    actor_enum = _normalize_actor_role(actor_role)

    if actor_enum == ActorRole.WORKER:
        raise ControllerDecisionError(
            "Worker cannot act as a controller decision actor"
        )

    # Validate task identity linkage when explicitly provided.
    if task_id is not None and task_id != bundle.task_id:
        raise ControllerDecisionError(
            f"Task ID mismatch: decision request says {task_id!r}, "
            f"bundle says {bundle.task_id!r}"
        )
    if task_filename is not None and task_filename != bundle.task_filename:
        raise ControllerDecisionError(
            f"Task filename mismatch: decision request says {task_filename!r}, "
            f"bundle says {bundle.task_filename!r}"
        )

    # Fail closed on missing required bundle linkage evidence.
    bundle_task_id = _require_bundle_field("task_id", bundle.task_id)
    bundle_task_filename = _require_bundle_field(
        "task_filename", bundle.task_filename
    )
    bundle_branch = _require_bundle_field("branch", bundle.branch)
    bundle_pre_head = _require_bundle_field("pre_head", bundle.pre_head)

    # bundle.post_head may legitimately be None if post-worker verification failed
    # before a post snapshot was captured; we still record it when present.

    # Store a repository-relative bundle path when possible for portability.
    stored_bundle_path = str(bundle_path)
    if repo_root is not None:
        try:
            stored_bundle_path = str(bundle_path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            pass

    # Bound the note length to avoid accidental inclusion of large content.
    safe_note = None
    if note is not None:
        safe_note = note.strip()[:4000] or None

    return ControllerDecision(
        timestamp=datetime.now(timezone.utc).isoformat(),
        task_id=bundle_task_id,
        task_filename=bundle_task_filename,
        bundle_path=stored_bundle_path,
        bundle_task_id=bundle_task_id,
        bundle_task_filename=bundle_task_filename,
        bundle_branch=bundle_branch,
        bundle_pre_head=bundle_pre_head,
        bundle_post_head=bundle.post_head,
        decision=decision_enum.value,
        actor_role=actor_enum.value,
        note=safe_note,
        record_version=DECISION_RECORD_VERSION,
    )


def serialize_controller_decision(decision: ControllerDecision) -> dict[str, Any]:
    """Return a JSON-serializable dict for *decision*."""
    data = asdict(decision)
    data["decision"] = str(decision.decision)
    data["actor_role"] = str(decision.actor_role)
    data["record_version"] = str(decision.record_version)
    return data


def write_controller_decision(
    decision: ControllerDecision,
    decisions_dir: Path,
) -> Path:
    """Write *decision* as JSON under *decisions_dir* and return the path.

    Raises:
        ControllerDecisionWriteError: if the decision record cannot be written.
    """
    try:
        decisions_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise ControllerDecisionWriteError(
            f"Failed to create decision directory {decisions_dir}: {exc}"
        ) from exc

    ts = datetime.fromisoformat(decision.timestamp).strftime("%Y%m%dT%H%M%S")
    task_part = _sanitize_filename(decision.task_id)
    decision_part = _sanitize_filename(decision.decision)
    filename = f"{ts}_{task_part}_{decision_part}.json"
    path = decisions_dir / filename

    payload = serialize_controller_decision(decision)
    try:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise ControllerDecisionWriteError(
            f"Failed to write decision record to {path}: {exc}"
        ) from exc

    return path


def load_controller_decision(path: Path) -> ControllerDecision:
    """Load a ``ControllerDecision`` from *path*.

    Raises:
        ControllerDecisionError: if the file cannot be read or parsed.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControllerDecisionError(
            f"Cannot read controller decision record {path}: {exc}"
        ) from exc

    try:
        return ControllerDecision(**data)
    except Exception as exc:
        raise ControllerDecisionError(
            f"Invalid controller decision record format in {path}: {exc}"
        ) from exc


def find_latest_decision(decisions_dir: Path) -> Path | None:
    """Return the most recently modified decision record under *decisions_dir*."""
    if not decisions_dir.exists():
        return None
    candidates = sorted(
        decisions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def format_decision_summary(decision: ControllerDecision) -> str:
    """Return a concise, human-readable summary of *decision*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Controller Decision Record")
    lines.append("=" * 64)
    lines.append(f"Task:          {decision.task_id or 'n/a'}")
    lines.append(f"File:          {decision.task_filename or 'n/a'}")
    lines.append(f"Bundle:        {decision.bundle_path}")
    lines.append(f"Bundle task:   {decision.bundle_task_id or 'n/a'}")
    lines.append(f"Bundle file:   {decision.bundle_task_filename or 'n/a'}")
    lines.append(f"Branch:        {decision.bundle_branch or 'n/a'}")
    lines.append(f"Pre HEAD:      {decision.bundle_pre_head or 'n/a'}")
    lines.append(f"Post HEAD:     {decision.bundle_post_head or 'n/a'}")
    lines.append(f"Decision:      {decision.decision}")
    lines.append(f"Actor role:    {decision.actor_role}")
    if decision.note:
        lines.append(f"Note:          {decision.note}")
    lines.append(f"Record version: {decision.record_version}")
    lines.append("=" * 64)
    return "\n".join(lines)
