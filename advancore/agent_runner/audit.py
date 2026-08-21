"""Durable local audit records for runner invocations.

Audit records are written as JSON Lines (one JSON object per line) under
``.agent_runner/audit/runner.jsonl`` in the repository root. Only safe
metadata is recorded; no credentials, environment dumps, full task bodies,
or worker transcripts are persisted.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_DIR_NAME = ".agent_runner"
AUDIT_SUBDIR = "audit"
AUDIT_FILENAME = "runner.jsonl"


class AuditWriteError(Exception):
    """Raised when an audit record cannot be written durably."""


def default_audit_dir(repo_root: Path) -> Path:
    """Return the default audit directory for *repo_root*."""
    return repo_root / AUDIT_DIR_NAME / AUDIT_SUBDIR


def build_audit_payload(
    *,
    timestamp: datetime | None = None,
    task_id: str | None,
    task_filename: str | None,
    mode: str,
    worker_type: str | None,
    branch: str | None,
    pre_head: str | None,
    post_head: str | None,
    pre_validation_ok: bool | None,
    worker_success: bool | None,
    post_verification_ok: bool | None,
    final_status: str,
    changed_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Return a safe metadata payload for one audit record.

    The payload intentionally excludes environment dumps, credentials,
    connection strings, full task bodies, worker transcripts, and business or
    customer data.
    """
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "task_id": task_id,
        "task_filename": task_filename,
        "mode": mode,
        "worker_type": worker_type,
        "branch": branch,
        "pre_head": pre_head,
        "post_head": post_head,
        "pre_validation_ok": pre_validation_ok,
        "worker_success": worker_success,
        "post_verification_ok": post_verification_ok,
        "final_status": final_status,
        "changed_paths": changed_paths or [],
    }


def build_lifecycle_audit_payload(
    *,
    timestamp: datetime | None = None,
    task_id: str | None,
    task_filename: str | None,
    actor_role: str | None,
    previous_status: str | None,
    requested_status: str | None,
    transition_allowed: bool,
    applied: bool,
    branch: str | None,
    head_sha: str | None,
) -> dict[str, Any]:
    """Return a safe metadata payload for a task lifecycle transition attempt.

    The payload intentionally excludes the task body, worker transcripts,
    credentials, environment dumps, and business or customer data.
    """
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "task_id": task_id,
        "task_filename": task_filename,
        "mode": "lifecycle",
        "actor_role": actor_role,
        "previous_status": previous_status,
        "requested_status": requested_status,
        "transition_allowed": transition_allowed,
        "applied": applied,
        "branch": branch,
        "head_sha": head_sha,
    }


def build_bridge_audit_payload(
    *,
    timestamp: datetime | None = None,
    task_id: str | None,
    task_filename: str | None,
    actor_role: str | None,
    decision: str | None,
    target_status: str | None,
    transition_allowed: bool,
    applied: bool,
    branch: str | None,
    head_sha: str | None,
    decision_path: str | None,
    bundle_path: str | None,
    bundle_pre_head: str | None,
    bundle_post_head: str | None,
) -> dict[str, Any]:
    """Return a safe metadata payload for a decision-lifecycle bridge attempt.

    The payload intentionally excludes the task body, worker transcripts,
    credentials, environment dumps, arbitrary notes, and business or customer
    data. It records that a bridge preview/apply was attempted, the decision
    and target status, whether the transition was allowed/applied, and the
    linked artifact paths.
    """
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "task_id": task_id,
        "task_filename": task_filename,
        "mode": "bridge",
        "actor_role": actor_role,
        "decision": decision,
        "target_status": target_status,
        "transition_allowed": transition_allowed,
        "applied": applied,
        "branch": branch,
        "head_sha": head_sha,
        "decision_path": decision_path,
        "bundle_path": bundle_path,
        "bundle_pre_head": bundle_pre_head,
        "bundle_post_head": bundle_post_head,
    }


def build_controller_decision_audit_payload(
    *,
    timestamp: datetime | None = None,
    task_id: str | None,
    task_filename: str | None,
    actor_role: str | None,
    decision: str | None,
    bundle_path: str | None,
    bundle_branch: str | None,
    bundle_pre_head: str | None,
    bundle_post_head: str | None,
    decision_path: str | None,
) -> dict[str, Any]:
    """Return a safe metadata payload for a controller decision record.

    The payload intentionally excludes the full task body, worker transcripts,
    credentials, environment dumps, arbitrary notes, and business or customer
    data. It records only that a decision was recorded, by whom, against which
    bundle, and where the resulting decision record is stored.
    """
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "task_id": task_id,
        "task_filename": task_filename,
        "mode": "controller_decision",
        "actor_role": actor_role,
        "decision": decision,
        "bundle_path": bundle_path,
        "bundle_branch": bundle_branch,
        "bundle_pre_head": bundle_pre_head,
        "bundle_post_head": bundle_post_head,
        "decision_path": decision_path,
    }


def build_controller_adapter_audit_payload(
    *,
    timestamp: datetime | None = None,
    task_id: str | None,
    task_filename: str | None,
    adapter_name: str | None,
    state: str | None,
    request_path: str | None,
    bundle_path: str | None,
    decision_path: str | None = None,
    decision: str | None = None,
    reconciled: bool = False,
    branch: str | None = None,
    head_sha: str | None = None,
) -> dict[str, Any]:
    """Return a safe metadata payload for a controller-adapter dispatch attempt.

    The payload intentionally excludes the full task body, worker transcripts,
    credentials, environment dumps, arbitrary notes, and business or customer
    data. It records only the adapter invoked, the handoff reference, the
    adapter result state, and whether a decision was reconciled.
    """
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "task_id": task_id,
        "task_filename": task_filename,
        "mode": "controller_adapter",
        "adapter_name": adapter_name,
        "state": state,
        "request_path": request_path,
        "bundle_path": bundle_path,
        "decision_path": decision_path,
        "decision": decision,
        "reconciled": reconciled,
        "branch": branch,
        "head_sha": head_sha,
    }


def build_controller_transport_audit_payload(
    *,
    timestamp: datetime | None = None,
    task_id: str | None,
    task_filename: str | None,
    request_id: str | None,
    state: str | None,
    request_path: str | None,
    bundle_path: str | None,
    decision_path: str | None = None,
    decision: str | None = None,
    reconciled: bool = False,
    branch: str | None = None,
    head_sha: str | None = None,
) -> dict[str, Any]:
    """Return a safe metadata payload for a controller-transport operation.

    The payload intentionally excludes the full task body, worker transcripts,
    credentials, environment dumps, arbitrary notes, and business or customer
    data. It records only the transport envelope reference, result state, and
    whether a returned decision was reconciled through existing TASK-013 logic.
    """
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "task_id": task_id,
        "task_filename": task_filename,
        "mode": "controller_transport",
        "request_id": request_id,
        "state": state,
        "request_path": request_path,
        "bundle_path": bundle_path,
        "decision_path": decision_path,
        "decision": decision,
        "reconciled": reconciled,
        "branch": branch,
        "head_sha": head_sha,
    }


def build_handoff_audit_payload(
    *,
    timestamp: datetime | None = None,
    task_id: str | None,
    task_filename: str | None,
    request_id: str | None,
    mode: str,
    state: str | None,
    bundle_path: str | None,
    bundle_branch: str | None,
    bundle_pre_head: str | None,
    bundle_post_head: str | None,
    decision_path: str | None = None,
    decision: str | None = None,
    branch: str | None = None,
    head_sha: str | None = None,
) -> dict[str, Any]:
    """Return a safe metadata payload for a controller handoff operation.

    The payload intentionally excludes the full task body, worker transcripts,
    credentials, environment dumps, arbitrary notes, and business or customer
    data. It records only that a handoff request was prepared or reconciled,
    the linked artifact references, and the resulting state.
    """
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "task_id": task_id,
        "task_filename": task_filename,
        "request_id": request_id,
        "mode": mode,
        "state": state,
        "bundle_path": bundle_path,
        "bundle_branch": bundle_branch,
        "bundle_pre_head": bundle_pre_head,
        "bundle_post_head": bundle_post_head,
        "decision_path": decision_path,
        "decision": decision,
        "branch": branch,
        "head_sha": head_sha,
    }


def write_audit_record(
    payload: dict[str, Any],
    audit_dir: Path,
) -> Path:
    """Append *payload* as one JSON Lines record under *audit_dir*.

    Raises:
        AuditWriteError: if the audit file cannot be written.
    """
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / AUDIT_FILENAME
    line = json.dumps(payload, separators=(",", ":"), default=str, sort_keys=True) + "\n"

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        raise AuditWriteError(
            f"Failed to write audit record to {path}: {exc}"
        ) from exc

    return path
