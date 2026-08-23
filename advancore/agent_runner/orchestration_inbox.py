"""Read-only, fail-closed projection of orchestration exceptions.

The inbox discovers local orchestration checkpoints and revalidates their
bounded references.  It never normalizes or writes evidence and never invokes
the orchestration, lifecycle, decision, worker, or publication paths.
"""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from advancore.agent_runner.controller_decision import (
    DecisionValue,
    default_decisions_dir,
    load_controller_decision,
)
from advancore.agent_runner.controller_handoff import load_controller_handoff
from advancore.agent_runner.git_info import get_git_info
from advancore.agent_runner.orchestration import (
    ORCHESTRATION_SCHEMA_VERSION,
    OrchestrationCheckpoint,
    OrchestrationPhase,
    OrchestrationStatus,
    default_orchestration_dir,
)
from advancore.agent_runner.review_bundle import default_review_dir, load_review_bundle
from advancore.agent_runner.finalize import (
    FINALIZE_ARTIFACT_FILENAME,
    FinalizationStatus,
    default_finalize_dir,
)
from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.task import TaskError, find_task


INBOX_SCHEMA_VERSION = "advancore-orchestration-inbox-v1"
MAX_REASON_LENGTH = 240
MAX_REFERENCE_COUNT = 7
_RUN_ID_RE = re.compile(r"^ORCH-[A-Za-z0-9_-]{1,120}$")


class InboxClassification(str, Enum):
    """Owner-facing exception classes; none grants authority."""

    ACTION_REQUIRED = "action-required"
    OPERATOR_INVESTIGATION = "operator-investigation"
    STALE_OR_INVALID_EVIDENCE = "stale-or-invalid-evidence"


@dataclass(frozen=True)
class OrchestrationInboxEntry:
    """One bounded unresolved orchestration exception."""

    run_id: str
    task_id: str | None
    task_title: str | None
    phase: str
    status: str
    classification: str
    reason: str
    evidence_references: tuple[str, ...]
    owner_decision_required: bool
    command: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_references"] = list(self.evidence_references)
        return payload


@dataclass(frozen=True)
class OrchestrationInbox:
    """Versioned, deterministic inbox result."""

    schema_version: str
    entries: tuple[OrchestrationInboxEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _bounded(value: object, *, fallback: str = "unknown") -> str:
    text = " ".join(str(value).split()) if value is not None else fallback
    if not text:
        text = fallback
    if len(text) > MAX_REASON_LENGTH:
        return text[: MAX_REASON_LENGTH - 3].rstrip() + "..."
    return text


def _preview_command(run_id: str) -> str:
    return (
        ".venv/bin/python -m advancore.agent_runner orchestrate "
        f"--resume {run_id}"
    )


def _safe_run_id(value: object, filename: str) -> str:
    candidate = str(value) if isinstance(value, str) else Path(filename).stem
    if _RUN_ID_RE.fullmatch(candidate):
        return candidate
    digest = hashlib.sha256(filename.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"ORCH-invalid-{digest}"


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _resolve_reference(value: str, repo_root: Path) -> Path:
    path = Path(value)
    unresolved = path if path.is_absolute() else repo_root / path
    if unresolved.is_symlink():
        raise ValueError("symlink evidence is not accepted")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("evidence path escapes repository") from exc
    return candidate


def _references(checkpoint: OrchestrationCheckpoint, repo_root: Path) -> tuple[str, ...]:
    values = [
        checkpoint.task_path,
        checkpoint.goal_task_artifact_path,
        checkpoint.auto_artifact_path,
        checkpoint.review_bundle_path,
        checkpoint.handoff_path,
        checkpoint.decision_path,
        checkpoint.finalization_artifact_path,
    ]
    refs: list[str] = []
    for value in values:
        if not value:
            continue
        try:
            path = _resolve_reference(value, repo_root)
            refs.append(str(path.relative_to(repo_root.resolve())))
        except (OSError, ValueError):
            refs.append("unsafe-reference")
    return tuple(sorted(set(refs))[:MAX_REFERENCE_COUNT])


def _invalid_entry(
    path: Path,
    reason: object,
    *,
    run_id: object = None,
    task_id: object = None,
    phase: object = "INVALID",
    status: object = "INVALID_EVIDENCE",
) -> OrchestrationInboxEntry:
    safe_id = _safe_run_id(run_id, path.name)
    safe_task = task_id if isinstance(task_id, str) and len(task_id) <= 128 else None
    return OrchestrationInboxEntry(
        run_id=safe_id,
        task_id=safe_task,
        task_title=None,
        phase=_bounded(phase),
        status=_bounded(status),
        classification=InboxClassification.STALE_OR_INVALID_EVIDENCE.value,
        reason=_bounded(reason, fallback="checkpoint evidence is invalid"),
        evidence_references=(str(path.name),),
        owner_decision_required=False,
        command=_preview_command(safe_id),
    )


def _load_candidate(path: Path) -> tuple[OrchestrationCheckpoint | None, dict[str, Any], str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None, {}, "checkpoint root must be an object"
    except Exception as exc:
        return None, {}, f"cannot read checkpoint: {type(exc).__name__}"
    if data.get("schema_version") != ORCHESTRATION_SCHEMA_VERSION:
        return None, data, "unsupported checkpoint schema"
    try:
        checkpoint = OrchestrationCheckpoint(**data)
    except Exception as exc:
        return None, data, f"invalid checkpoint format: {type(exc).__name__}"
    return checkpoint, data, None


def _validate_artifact(
    value: str | None,
    repo_root: Path,
    label: str,
    loader: Callable[[Path], object] | None = None,
) -> tuple[Path | None, str | None]:
    if not value:
        return None, None
    try:
        path = _resolve_reference(value, repo_root)
    except (OSError, ValueError) as exc:
        return None, f"{label} path is unsafe: {exc}"
    if not path.exists():
        return None, f"{label} evidence is missing"
    if not path.is_file():
        return None, f"{label} evidence is not a regular file"
    if loader is not None:
        try:
            loader(path)
        except Exception:
            return None, f"{label} evidence is malformed"
    return path, None


def _validate_checkpoint(
    checkpoint: OrchestrationCheckpoint,
    path: Path,
    repo_root: Path,
    *,
    check_current_freshness: bool = True,
) -> tuple[str | None, str | None, str | None]:
    """Return task title, invalid reason, or stale reason."""
    if not _RUN_ID_RE.fullmatch(checkpoint.run_id) or path.stem != checkpoint.run_id:
        return None, "checkpoint filename and run ID conflict", None
    if checkpoint.phase not in {item.value for item in OrchestrationPhase}:
        return None, "checkpoint phase is unknown", None
    if checkpoint.status not in {item.value for item in OrchestrationStatus}:
        return None, "checkpoint status is unknown", None
    if _parse_timestamp(checkpoint.updated_at) is None:
        return None, "checkpoint timestamp is invalid", None
    if not isinstance(checkpoint.completed_phases, list) or not all(
        isinstance(value, str) for value in checkpoint.completed_phases
    ):
        return None, "checkpoint completed phases are invalid", None
    if not isinstance(checkpoint.path_fingerprint, list) or not all(
        isinstance(value, str) for value in checkpoint.path_fingerprint
    ):
        return None, "checkpoint path fingerprint is invalid", None

    title: str | None = None
    if checkpoint.task_id or checkpoint.task_path:
        if not checkpoint.task_id or not checkpoint.task_path:
            return None, "task linkage is incomplete", None
        try:
            task_path = _resolve_reference(checkpoint.task_path, repo_root)
            if task_path.parent != (repo_root / "tasks").resolve():
                return None, "task path is outside authoritative tasks directory", None
            task = find_task(repo_root / "tasks", checkpoint.task_id)
            if task.path.resolve() != task_path or task.task_id != checkpoint.task_id:
                return None, "checkpoint task linkage conflicts with task evidence", None
            title = _bounded(task.title)
        except (OSError, ValueError, TaskError):
            return None, "authoritative task evidence is missing or malformed", None

    loaders = (
        (checkpoint.review_bundle_path, "review bundle", load_review_bundle),
        (checkpoint.handoff_path, "handoff", load_controller_handoff),
        (checkpoint.decision_path, "decision", load_controller_decision),
        (checkpoint.goal_task_artifact_path, "goal-task artifact", None),
        (checkpoint.auto_artifact_path, "auto artifact", None),
    )
    loaded: dict[str, object] = {}
    for value, label, loader in loaders:
        artifact_path, error = _validate_artifact(value, repo_root, label, loader)
        if error:
            return title, error, None
        if artifact_path is not None and loader is not None:
            try:
                loaded[label] = loader(artifact_path)
            except Exception:
                return title, f"{label} evidence is malformed", None

    for label in ("review bundle", "handoff", "decision"):
        artifact = loaded.get(label)
        artifact_task = getattr(artifact, "task_id", checkpoint.task_id)
        if artifact is not None and artifact_task != checkpoint.task_id:
            return title, f"{label} task linkage conflicts with checkpoint", None

    bundle = loaded.get("review bundle")
    handoff = loaded.get("handoff")
    decision = loaded.get("decision")
    if not check_current_freshness:
        return title, None, None

    try:
        bundle_path = (
            _resolve_reference(checkpoint.review_bundle_path, repo_root)
            if checkpoint.review_bundle_path else None
        )
        if handoff is not None and bundle_path is not None:
            linked = _resolve_reference(getattr(handoff, "bundle_path"), repo_root)
            if linked != bundle_path:
                return title, "handoff bundle linkage conflicts with checkpoint", None
        if decision is not None and bundle_path is not None:
            linked = _resolve_reference(getattr(decision, "bundle_path"), repo_root)
            if linked != bundle_path:
                return title, "decision bundle linkage conflicts with checkpoint", None
        if bundle is not None and checkpoint.branch:
            bundle_branch = getattr(bundle, "branch", None)
            if bundle_branch and bundle_branch != checkpoint.branch:
                return title, "review bundle branch conflicts with checkpoint", None
    except (AttributeError, OSError, TypeError, ValueError):
        return title, "artifact linkage is incomplete or unsafe", None

    try:
        git_info = get_git_info(cwd=repo_root)
    except Exception:
        return title, "current Git evidence cannot be read", None
    if checkpoint.branch and checkpoint.branch != git_info.current_branch:
        return title, None, "checkpoint branch differs from current branch"
    if checkpoint.expected_head and checkpoint.expected_head != git_info.head_sha:
        return title, None, "checkpoint HEAD differs from current HEAD"
    changed_paths: list[str] = []
    for line in git_info.status_lines:
        if "->" in line:
            changed_paths.append(line.split("->")[-1].strip())
        elif len(line) > 3:
            changed_paths.append(line[3:].strip())
        elif line.strip():
            changed_paths.append(line.strip())
    if checkpoint.path_fingerprint and sorted(changed_paths) != sorted(
        checkpoint.path_fingerprint
    ):
        return title, None, "checkpoint path fingerprint differs from current repository"
    return title, None, None


def _same_reference(path: Path, value: object, repo_root: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return _resolve_reference(value, repo_root) == path
    except (OSError, ValueError):
        return False


def _terminal_finalization_path(value: str | None, repo_root: Path) -> Path:
    if not value:
        raise ValueError("finalization artifact linkage is missing")
    path = _resolve_reference(value, repo_root)
    canonical_dir = default_finalize_dir(repo_root).resolve()
    if path == canonical_dir:
        path = path / FINALIZE_ARTIFACT_FILENAME
    if path != canonical_dir / FINALIZE_ARTIFACT_FILENAME:
        raise ValueError("finalization artifact is not the canonical finalize.jsonl")
    if path.is_symlink():
        raise ValueError("symlink evidence is not accepted")
    if not path.exists():
        raise ValueError("canonical finalize.jsonl evidence is missing")
    if not path.is_file():
        raise ValueError("canonical finalize.jsonl evidence is not a regular file")
    return path


def _load_finalization_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("record is not an object")
            records.append(record)
    except Exception as exc:
        raise ValueError("finalization evidence is malformed") from exc
    return records


def _validate_terminal_publication(
    checkpoint: OrchestrationCheckpoint, repo_root: Path
) -> str | None:
    """Validate one immutable PUBLISHED evidence chain without current freshness."""
    # The orchestrator records FINALIZATION as completed, then exposes
    # PUBLISHED as the current terminal phase/status. Requiring PUBLISHED in
    # both places would reject its own authoritative checkpoint shape.
    required_phases = {OrchestrationPhase.FINALIZATION.value}
    if (
        checkpoint.phase != OrchestrationPhase.PUBLISHED.value
        or checkpoint.status != OrchestrationStatus.PUBLISHED.value
        or checkpoint.push_verified is not True
        or not isinstance(checkpoint.commit_sha, str)
        or not checkpoint.commit_sha
        or checkpoint.decision != DecisionValue.APPROVE.value
        or not required_phases.issubset(set(checkpoint.completed_phases))
    ):
        return "published state is incomplete or lacks verified terminal evidence"
    if not checkpoint.task_id or not checkpoint.task_path or not checkpoint.branch:
        return "terminal task or feature-line linkage is incomplete"
    if not checkpoint.review_bundle_path or not checkpoint.decision_path:
        return "terminal review or decision linkage is incomplete"

    try:
        task_path = _resolve_reference(checkpoint.task_path, repo_root)
        task = find_task(repo_root / "tasks", checkpoint.task_id)
        if task.path.resolve() != task_path or task.task_id != checkpoint.task_id:
            return "terminal task linkage conflicts with authoritative task evidence"
        if task.status != "APPROVED":
            return "terminal task is not currently APPROVED"
        task_filename = task.path.name

        bundle_path = _resolve_reference(checkpoint.review_bundle_path, repo_root)
        if (
            bundle_path.parent != default_review_dir(repo_root).resolve()
            or bundle_path.is_symlink()
            or not bundle_path.is_file()
        ):
            return "terminal review bundle evidence is missing or unsafe"
        bundle = load_review_bundle(bundle_path)
        if (
            bundle.task_id != checkpoint.task_id
            or bundle.task_filename != task_filename
            or bundle.branch != checkpoint.branch
            or not bundle.post_head
        ):
            return "terminal review bundle linkage conflicts with checkpoint"

        decision_path = _resolve_reference(checkpoint.decision_path, repo_root)
        if (
            decision_path.parent != default_decisions_dir(repo_root).resolve()
            or decision_path.is_symlink()
            or not decision_path.is_file()
        ):
            return "terminal controller decision evidence is missing or unsafe"
        decision = load_controller_decision(decision_path)
        if decision.decision != DecisionValue.APPROVE.value:
            return "terminal controller decision is not APPROVE"
        if decision.actor_role not in {
            ActorRole.CONTROLLER.value,
            ActorRole.OWNER.value,
        }:
            return "terminal controller decision actor is unauthorized"
        if (
            decision.task_id != checkpoint.task_id
            or decision.task_filename != task_filename
            or decision.bundle_task_id != checkpoint.task_id
            or decision.bundle_task_filename != task_filename
            or decision.bundle_branch != checkpoint.branch
            or decision.bundle_pre_head != bundle.pre_head
            or decision.bundle_post_head != bundle.post_head
            or not _same_reference(bundle_path, decision.bundle_path, repo_root)
        ):
            return "terminal controller decision linkage conflicts with review bundle"

        finalization_path = _terminal_finalization_path(
            checkpoint.finalization_artifact_path, repo_root
        )
        records = _load_finalization_records(finalization_path)
    except (OSError, ValueError, TaskError):
        return "terminal evidence is missing, malformed, or unsafe"
    except Exception:
        return "terminal task, review, or decision evidence is malformed"

    matches = [
        record
        for record in records
        if record.get("mode") == "finalize"
        and record.get("status") == FinalizationStatus.PUSHED.value
        and record.get("task_id") == checkpoint.task_id
    ]
    if len(matches) != 1:
        return "successful finalization evidence is missing or ambiguous"
    record = matches[0]
    if (
        record.get("task_filename") != task_filename
        or record.get("branch") != checkpoint.branch
        or record.get("pre_head") != bundle.post_head
        or record.get("post_head") != checkpoint.commit_sha
        or record.get("commit_sha") != checkpoint.commit_sha
        or not _same_reference(bundle_path, record.get("bundle_path"), repo_root)
        or not _same_reference(decision_path, record.get("decision_path"), repo_root)
    ):
        return "finalization evidence linkage conflicts with terminal checkpoint"

    commit_check = subprocess.run(
        ["git", "cat-file", "-e", f"{checkpoint.commit_sha}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if commit_check.returncode != 0:
        return "finalized commit evidence is missing or invalid"
    return None


_OWNER_STATUSES = {
    OrchestrationStatus.AWAITING_TASK_APPROVAL.value,
    OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value,
    OrchestrationStatus.OWNER_DECISION_REQUIRED.value,
}
_INVESTIGATION_STATUSES = {
    OrchestrationStatus.TASK_EXECUTION.value,
    OrchestrationStatus.FINALIZATION.value,
    OrchestrationStatus.REWORK_REQUIRED.value,
    OrchestrationStatus.REWORK_EXHAUSTED.value,
    OrchestrationStatus.NON_REPAIRABLE.value,
    OrchestrationStatus.REPAIR_EXHAUSTED.value,
    OrchestrationStatus.BLOCKED.value,
    OrchestrationStatus.FAILED.value,
}


def _reason(checkpoint: OrchestrationCheckpoint) -> str:
    if checkpoint.status == OrchestrationStatus.OWNER_DECISION_REQUIRED.value:
        return "owner decision is required before task approval can proceed"
    if checkpoint.status == OrchestrationStatus.AWAITING_TASK_APPROVAL.value:
        return "task is awaiting an authorized approval decision"
    if checkpoint.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value:
        return "implementation is awaiting an authorized decision"
    if checkpoint.worker_terminal_reason:
        return _bounded(checkpoint.worker_terminal_reason)
    if checkpoint.status == OrchestrationStatus.REWORK_EXHAUSTED.value:
        return "bounded rework budget is exhausted"
    if checkpoint.status == OrchestrationStatus.REPAIR_EXHAUSTED.value:
        return "bounded repair budget is exhausted"
    if checkpoint.status == OrchestrationStatus.NON_REPAIRABLE.value:
        return "worker result was classified as non-repairable"
    return f"orchestration requires investigation at {checkpoint.status}"


def _entry_for_checkpoint(
    checkpoint: OrchestrationCheckpoint, path: Path, repo_root: Path
) -> OrchestrationInboxEntry | None:
    terminal_claim = (
        checkpoint.phase == OrchestrationPhase.PUBLISHED.value
        or checkpoint.status == OrchestrationStatus.PUBLISHED.value
    )
    title, invalid_reason, stale_reason = _validate_checkpoint(
        checkpoint,
        path,
        repo_root,
        check_current_freshness=not terminal_claim,
    )
    if not invalid_reason and terminal_claim:
        invalid_reason = _validate_terminal_publication(checkpoint, repo_root)
    if invalid_reason or stale_reason:
        classification = InboxClassification.STALE_OR_INVALID_EVIDENCE.value
        reason = invalid_reason or stale_reason or "checkpoint evidence is invalid"
        status = (
            OrchestrationStatus.STALE_EVIDENCE.value
            if stale_reason
            else "INVALID_EVIDENCE"
        )
    elif terminal_claim:
        return None
    elif checkpoint.status in _OWNER_STATUSES:
        classification = InboxClassification.ACTION_REQUIRED.value
        reason = _reason(checkpoint)
        status = checkpoint.status
    elif checkpoint.status in _INVESTIGATION_STATUSES:
        classification = InboxClassification.OPERATOR_INVESTIGATION.value
        reason = _reason(checkpoint)
        status = checkpoint.status
    else:
        classification = InboxClassification.OPERATOR_INVESTIGATION.value
        reason = "orchestration is not terminal and requires investigation"
        status = checkpoint.status

    owner_required = (
        not (invalid_reason or stale_reason)
        and checkpoint.status in _OWNER_STATUSES
    )
    return OrchestrationInboxEntry(
        run_id=checkpoint.run_id,
        task_id=checkpoint.task_id,
        task_title=title,
        phase=checkpoint.phase,
        status=status,
        classification=classification,
        reason=_bounded(reason),
        evidence_references=_references(checkpoint, repo_root),
        owner_decision_required=owner_required,
        command=_preview_command(checkpoint.run_id),
    )


_URGENCY = {
    InboxClassification.ACTION_REQUIRED.value: 0,
    InboxClassification.STALE_OR_INVALID_EVIDENCE.value: 1,
    InboxClassification.OPERATOR_INVESTIGATION.value: 2,
}


def _sort_key(
    entry: OrchestrationInboxEntry, checkpoint_timestamp: object
) -> tuple[int, float, str]:
    timestamp = _parse_timestamp(checkpoint_timestamp)
    # Older unresolved entries appear first within the same urgency.
    epoch = timestamp.timestamp() if timestamp else float("-inf")
    return (_URGENCY[entry.classification], epoch, entry.run_id)


def build_orchestration_inbox(
    repo_root: Path, run_id: str | None = None
) -> OrchestrationInbox:
    """Discover and return unresolved checkpoint exceptions without mutation."""
    root = repo_root.resolve()
    inbox_dir = default_orchestration_dir(root)
    candidates: list[Path]
    if run_id is not None:
        if not _RUN_ID_RE.fullmatch(run_id):
            synthetic = inbox_dir / f"{_bounded(run_id)}.json"
            entry = _invalid_entry(synthetic, "requested run ID is invalid", run_id=run_id)
            return OrchestrationInbox(INBOX_SCHEMA_VERSION, (entry,))
        candidate = inbox_dir / f"{run_id}.json"
        if not candidate.is_file():
            entry = _invalid_entry(candidate, "checkpoint was not found", run_id=run_id)
            return OrchestrationInbox(INBOX_SCHEMA_VERSION, (entry,))
        candidates = [candidate]
    else:
        try:
            candidates = sorted(
                (path for path in inbox_dir.iterdir() if path.suffix == ".json"),
                key=lambda item: item.name,
            ) if inbox_dir.is_dir() else []
        except OSError as exc:
            entry = _invalid_entry(inbox_dir / "unreadable.json", f"cannot enumerate checkpoints: {type(exc).__name__}")
            return OrchestrationInbox(INBOX_SCHEMA_VERSION, (entry,))

    entries: list[tuple[OrchestrationInboxEntry, object]] = []
    for path in candidates:
        checkpoint, data, error = _load_candidate(path)
        if error or checkpoint is None:
            entries.append(
                (_invalid_entry(
                    path,
                    error,
                    run_id=data.get("run_id"),
                    task_id=data.get("task_id"),
                    phase=data.get("phase", "INVALID"),
                    status=data.get("status", "INVALID_EVIDENCE"),
                ), data.get("updated_at"))
            )
            continue
        entry = _entry_for_checkpoint(checkpoint, path, root)
        if entry is not None:
            entries.append((entry, checkpoint.updated_at))
    ordered = sorted(entries, key=lambda item: _sort_key(item[0], item[1]))
    return OrchestrationInbox(
        INBOX_SCHEMA_VERSION, tuple(entry for entry, _timestamp in ordered)
    )


def format_orchestration_inbox(inbox: OrchestrationInbox) -> str:
    """Return concise human output with exactly one command per entry."""
    if not inbox.entries:
        return "Orchestration exception inbox: no unresolved exceptions."
    lines = [f"Orchestration exception inbox ({len(inbox.entries)})"]
    for entry in inbox.entries:
        task = entry.task_id or "no task"
        if entry.task_title:
            task = f"{task} — {entry.task_title}"
        lines.extend(
            [
                f"- {entry.run_id} | {task} | {entry.phase}/{entry.status}",
                f"  {entry.classification}: {entry.reason}",
                f"  Next: {entry.command}",
            ]
        )
    return "\n".join(lines)


def serialize_orchestration_inbox(inbox: OrchestrationInbox) -> str:
    """Return stable JSON for an inbox result."""
    return json.dumps(inbox.to_dict(), indent=2, sort_keys=True)
