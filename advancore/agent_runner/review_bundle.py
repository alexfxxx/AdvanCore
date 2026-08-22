"""Controller review bundle for the local agent runner.

A review bundle is a deterministic, machine-readable JSON artifact produced
after a worker run. It collects bounded review metadata so an independent
controller/reviewer can evaluate the result without relying on terminal
screenshots or full worker transcripts.

Bundles are stored under ``.agent_runner/review/`` which is gitignored via the
existing ``.agent_runner/`` rule. They intentionally exclude credentials,
environment dumps, connection strings, full task bodies, worker transcripts,
customer data, and arbitrary command output.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from advancore.agent_runner.runner import RunnerResult


REVIEW_SUBDIR = "review"


class ControllerAction(str, Enum):
    """Recommended controller action derived from runner evidence only."""

    REVIEW = "REVIEW"
    REWORK = "REWORK"
    BLOCKED = "BLOCKED"


class ReviewBundleWriteError(Exception):
    """Raised when a review bundle cannot be written durably."""


@dataclass
class ReviewBundle:
    """Machine-readable review metadata for a single runner invocation."""

    timestamp: str
    task_id: str | None
    task_filename: str | None
    previous_status: str | None
    current_status: str | None
    branch: str | None
    pre_head: str | None
    post_head: str | None
    runner_status: str
    worker_type: str | None
    worker_success: bool | None
    post_verification_ok: bool | None
    post_verification_messages: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    diff_summary: dict[str, Any] = field(default_factory=dict)
    audit_path: str | None = None
    recommended_action: str = ControllerAction.BLOCKED.value
    messages: list[str] = field(default_factory=list)


class ReviewBundleError(Exception):
    """Raised when a review bundle cannot be built from runner state."""


def default_review_dir(repo_root: Path) -> Path:
    """Return the default review-bundle directory for *repo_root*."""
    return repo_root / ".agent_runner" / REVIEW_SUBDIR


def _sanitize_filename(value: str | None) -> str:
    """Return a filesystem-safe fragment from *value*."""
    if not value:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9_\-]", "_", value)[:64]


def _build_diff_summary(changed_paths: list[str]) -> dict[str, Any]:
    """Return bounded diff statistics from ``git status --porcelain`` paths.

    The summary counts paths by status category and reports totals. It does
    not include file contents or arbitrary command output.
    """
    counts: dict[str, int] = {
        "modified": 0,
        "added": 0,
        "deleted": 0,
        "renamed": 0,
        "untracked": 0,
        "other": 0,
    }
    for line in changed_paths:
        if not line:
            continue
        # ``git status --porcelain`` index/work-tree codes are in columns 0/1.
        # We receive only the path here, but the caller may pass raw lines.
        # Normalize by taking the first two non-space characters if present.
        status_part = line[:3].strip()
        path_part = line[3:].strip() if len(line) > 3 else line.strip()
        code = status_part[:2] if status_part else "??"

        if "M" in code:
            counts["modified"] += 1
        elif "A" in code:
            counts["added"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        elif "R" in code:
            counts["renamed"] += 1
        elif code == "??":
            counts["untracked"] += 1
        else:
            counts["other"] += 1

    return {
        "total": len(changed_paths),
        "counts": counts,
    }


def _derive_changed_paths(post_verification) -> list[str]:  # type: ignore[no-untyped-def]
    """Return the changed paths captured by post-worker verification."""
    if post_verification is None:
        return []
    return list(post_verification.changed_paths or [])


def _derive_recommended_action(
    runner_status: str,
    post_verification_ok: bool | None,
    worker_success: bool | None,
) -> ControllerAction:
    """Return the controller action implied by runner evidence.

    The bundle may recommend only ``REVIEW``, ``REWORK``, or ``BLOCKED``.
    It must never recommend or assert ``APPROVED``.
    """
    if not post_verification_ok or runner_status == "post_worker_verification_failed":
        return ControllerAction.BLOCKED
    if worker_success is False or runner_status == "worker_failed":
        return ControllerAction.REWORK
    if worker_success is True and post_verification_ok is True:
        return ControllerAction.REVIEW
    return ControllerAction.BLOCKED


def build_review_bundle(result: RunnerResult) -> ReviewBundle:
    """Build a ``ReviewBundle`` from a completed ``RunnerResult``.

    Raises:
        ReviewBundleError: if required runner state is missing.
    """
    pre = result.pre_git_info or result.git_info
    post = result.post_git_info
    if pre is None:
        raise ReviewBundleError("Cannot build review bundle: no pre-worker Git snapshot")

    changed_paths = _derive_changed_paths(result.post_verification)
    diff_summary = _build_diff_summary(changed_paths)

    worker_success: bool | None = None
    if result.worker_result is not None:
        worker_success = result.worker_result.success

    post_verification_ok: bool | None = None
    post_verification_messages: list[str] = []
    if result.post_verification is not None:
        post_verification_ok = result.post_verification.ok
        post_verification_messages = list(result.post_verification.messages or [])

    previous_status = None
    current_status = None
    if result.task is not None:
        current_status = result.task.status

    audit_rel_path: str | None = None
    if result.audit_path is not None:
        try:
            audit_rel_path = str(result.audit_path.relative_to(pre.repo_root))
        except ValueError:
            audit_rel_path = str(result.audit_path)

    recommended_action = _derive_recommended_action(
        result.status.value,
        post_verification_ok,
        worker_success,
    )

    return ReviewBundle(
        timestamp=datetime.now(timezone.utc).isoformat(),
        task_id=result.task.task_id if result.task else None,
        task_filename=result.task.filename if result.task else None,
        previous_status=previous_status,
        current_status=current_status,
        branch=pre.current_branch,
        pre_head=pre.head_sha,
        post_head=post.head_sha if post else None,
        runner_status=result.status.value,
        worker_type=result.worker_type,
        worker_success=worker_success,
        post_verification_ok=post_verification_ok,
        post_verification_messages=post_verification_messages,
        changed_paths=changed_paths,
        diff_summary=diff_summary,
        audit_path=audit_rel_path,
        recommended_action=recommended_action.value,
        messages=list(result.messages or []),
    )


def serialize_bundle(bundle: ReviewBundle) -> dict[str, Any]:
    """Return a JSON-serializable dict for *bundle*."""
    data = asdict(bundle)
    # Ensure the recommended action is a plain string.
    data["recommended_action"] = str(bundle.recommended_action)
    return data


def write_review_bundle(
    bundle: ReviewBundle,
    review_dir: Path,
) -> Path:
    """Write *bundle* as JSON under *review_dir* and return the path.

    Raises:
        ReviewBundleWriteError: if the bundle cannot be written.
    """
    try:
        review_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise ReviewBundleWriteError(
            f"Failed to create review bundle directory {review_dir}: {exc}"
        ) from exc

    ts = datetime.fromisoformat(bundle.timestamp).strftime("%Y%m%dT%H%M%S")
    task_part = _sanitize_filename(bundle.task_id)
    filename = f"{ts}_{task_part}.json"
    path = review_dir / filename

    payload = serialize_bundle(bundle)
    try:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise ReviewBundleWriteError(
            f"Failed to write review bundle to {path}: {exc}"
        ) from exc

    return path


def load_review_bundle(path: Path) -> ReviewBundle:
    """Load a ``ReviewBundle`` from *path*.

    Raises:
        ReviewBundleError: if the file cannot be read or parsed.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReviewBundleError(f"Cannot read review bundle {path}: {exc}") from exc

    try:
        return ReviewBundle(**data)
    except Exception as exc:
        raise ReviewBundleError(f"Invalid review bundle format in {path}: {exc}") from exc


def find_latest_bundle(review_dir: Path) -> Path | None:
    """Return the most recently modified bundle under *review_dir*, or ``None``."""
    if not review_dir.exists():
        return None
    candidates = sorted(review_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def format_bundle_summary(bundle: ReviewBundle) -> str:
    """Return a concise, human-readable summary of *bundle*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Review Bundle")
    lines.append("=" * 64)
    lines.append(f"Task:          {bundle.task_id or 'n/a'}")
    lines.append(f"File:          {bundle.task_filename or 'n/a'}")
    lines.append(f"Branch:        {bundle.branch or 'n/a'}")
    lines.append(f"Pre HEAD:      {bundle.pre_head or 'n/a'}")
    lines.append(f"Post HEAD:     {bundle.post_head or 'n/a'}")
    lines.append(f"Runner status: {bundle.runner_status}")
    lines.append(f"Worker type:   {bundle.worker_type or 'n/a'}")
    lines.append(f"Worker success: {bundle.worker_success}")
    lines.append(f"Verification:  {'PASS' if bundle.post_verification_ok else 'FAIL'}")
    lines.append(f"Changed paths: {len(bundle.changed_paths)}")
    if bundle.changed_paths:
        for changed_path in bundle.changed_paths:
            lines.append(f"  {changed_path}")
    lines.append(f"Recommended action: {bundle.recommended_action}")
    lines.append(f"Audit record: {bundle.audit_path or 'n/a'}")
    lines.append("=" * 64)
    return "\n".join(lines)
