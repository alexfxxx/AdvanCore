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
