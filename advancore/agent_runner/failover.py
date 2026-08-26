"""Strict credential-free failover checkpoints and safe next-worker selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import re
import tempfile

from advancore.agent_runner.auto_pipeline import ProviderFailure
from advancore.agent_runner.worker import WorkerError
from advancore.agent_runner.worker_registry import WorkerRole, get_worker_profile
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
    WorkerSelectionError,
    select_governed_worker,
)


FAILOVER_SCHEMA_VERSION = 1
MAX_FAILOVER_WORKERS = 3
_RUN_ID = re.compile(r"FAILOVER-[A-Za-z0-9][A-Za-z0-9-]{0,63}")
_TASK_ID = re.compile(r"TASK-[0-9]{3,6}")
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_CHECKPOINT_KEYS = {
    "schema_version",
    "run_id",
    "task_id",
    "branch",
    "role",
    "selected_worker",
    "attempted_workers",
    "last_failure",
    "repository_fingerprint",
}


class FailoverError(RuntimeError):
    """Raised when a failover checkpoint or transition is unsafe."""


@dataclass(frozen=True)
class FailoverCheckpoint:
    schema_version: int
    run_id: str
    task_id: str
    branch: str
    role: WorkerRole
    selected_worker: str
    attempted_workers: tuple[str, ...]
    last_failure: ProviderFailure | None
    repository_fingerprint: str


def _validate_checkpoint(checkpoint: FailoverCheckpoint) -> FailoverCheckpoint:
    if not isinstance(checkpoint, FailoverCheckpoint):
        raise FailoverError("Failover checkpoint is invalid")
    if checkpoint.schema_version != FAILOVER_SCHEMA_VERSION:
        raise FailoverError("Failover checkpoint version is unsupported")
    if not _RUN_ID.fullmatch(checkpoint.run_id):
        raise FailoverError("Failover run identifier is invalid")
    if not _TASK_ID.fullmatch(checkpoint.task_id):
        raise FailoverError("Failover task identifier is invalid")
    if not _BRANCH.fullmatch(checkpoint.branch) or ".." in checkpoint.branch.split("/"):
        raise FailoverError("Failover branch is invalid")
    if not isinstance(checkpoint.role, WorkerRole):
        raise FailoverError("Failover role is invalid")
    if not _FINGERPRINT.fullmatch(checkpoint.repository_fingerprint):
        raise FailoverError("Failover repository fingerprint is invalid")
    if not isinstance(checkpoint.attempted_workers, tuple) or not all(
        isinstance(worker, str) for worker in checkpoint.attempted_workers
    ):
        raise FailoverError("Failover attempt history is invalid")
    try:
        selected = get_worker_profile(checkpoint.selected_worker)
    except WorkerError as exc:
        raise FailoverError("Selected worker is invalid") from exc
    if not selected.is_eligible(checkpoint.role):
        raise FailoverError("Selected worker is not eligible")
    if (
        len(checkpoint.attempted_workers) > MAX_FAILOVER_WORKERS
        or len(set(checkpoint.attempted_workers)) != len(checkpoint.attempted_workers)
        or checkpoint.selected_worker in checkpoint.attempted_workers
    ):
        raise FailoverError("Failover attempt history is invalid")
    try:
        for worker in checkpoint.attempted_workers:
            get_worker_profile(worker)
    except WorkerError as exc:
        raise FailoverError("Failover attempt history is invalid") from exc
    if checkpoint.last_failure is not None and not isinstance(
        checkpoint.last_failure, ProviderFailure
    ):
        raise FailoverError("Failover failure class is invalid")
    return checkpoint


def start_failover_checkpoint(
    *,
    run_id: str,
    task_id: str,
    branch: str,
    role: WorkerRole | str,
    repository_fingerprint: str,
    evidence: tuple[WorkerAvailabilityEvidence, ...],
) -> FailoverCheckpoint:
    try:
        selection = select_governed_worker(role, evidence)
    except WorkerSelectionError as exc:
        raise FailoverError("No safe initial worker is available") from exc
    return _validate_checkpoint(
        FailoverCheckpoint(
            schema_version=FAILOVER_SCHEMA_VERSION,
            run_id=run_id,
            task_id=task_id,
            branch=branch,
            role=selection.role,
            selected_worker=selection.selected_worker,
            attempted_workers=(),
            last_failure=None,
            repository_fingerprint=repository_fingerprint,
        )
    )


def advance_failover_checkpoint(
    checkpoint: FailoverCheckpoint,
    *,
    failed_worker: str,
    failure: ProviderFailure,
    repository_fingerprint: str,
    evidence: tuple[WorkerAvailabilityEvidence, ...],
) -> FailoverCheckpoint:
    current = _validate_checkpoint(checkpoint)
    if failed_worker != current.selected_worker:
        raise FailoverError("Failover worker does not match the selected worker")
    if repository_fingerprint != current.repository_fingerprint:
        raise FailoverError("Repository fingerprint changed; failover is blocked")
    if failure == ProviderFailure.UNKNOWN or not isinstance(failure, ProviderFailure):
        raise FailoverError("Worker failure is not eligible for failover")
    attempted = current.attempted_workers + (failed_worker,)
    if len(attempted) >= MAX_FAILOVER_WORKERS:
        raise FailoverError("Failover worker limit is exhausted")

    if not isinstance(evidence, tuple):
        raise FailoverError("Worker availability evidence is invalid")
    by_name: dict[str, WorkerAvailabilityEvidence] = {}
    for item in evidence:
        if not isinstance(item, WorkerAvailabilityEvidence):
            raise FailoverError("Worker availability evidence is invalid")
        if item.worker in by_name:
            raise FailoverError("Duplicate worker availability evidence")
        by_name[item.worker] = item
    for previous in attempted:
        by_name[previous] = WorkerAvailabilityEvidence(
            previous, WorkerAvailability.UNAVAILABLE
        )
    try:
        selection = select_governed_worker(current.role, tuple(by_name.values()))
    except WorkerSelectionError as exc:
        raise FailoverError("No safe fallback worker is available") from exc
    if selection.selected_worker in attempted:
        raise FailoverError("Failover would repeat an attempted worker")
    return _validate_checkpoint(
        replace(
            current,
            selected_worker=selection.selected_worker,
            attempted_workers=attempted,
            last_failure=failure,
        )
    )


def save_failover_checkpoint(
    checkpoint: FailoverCheckpoint, state_directory: Path
) -> Path:
    checked = _validate_checkpoint(checkpoint)
    directory = Path(state_directory)
    if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
        raise FailoverError("Failover state directory is unsafe")
    try:
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        resolved = directory.resolve(strict=True)
    except OSError as exc:
        raise FailoverError("Failover state directory is unavailable") from exc
    path = resolved / f"{checked.run_id}.json"
    if path.exists() and path.is_symlink():
        raise FailoverError("Failover checkpoint path is unsafe")
    payload = asdict(checked)
    payload["role"] = checked.role.value
    payload["attempted_workers"] = list(checked.attempted_workers)
    payload["last_failure"] = (
        checked.last_failure.value if checked.last_failure is not None else None
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=resolved, prefix=".failover-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise FailoverError("Failover checkpoint could not be saved") from exc
    return path


def load_failover_checkpoint(run_id: str, state_directory: Path) -> FailoverCheckpoint:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise FailoverError("Failover run identifier is invalid")
    directory = Path(state_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise FailoverError("Failover state directory is unavailable")
    try:
        resolved = directory.resolve(strict=True)
    except OSError as exc:
        raise FailoverError("Failover state directory is unavailable") from exc
    path = resolved / f"{run_id}.json"
    if path.is_symlink() or not path.is_file() or path.parent != resolved:
        raise FailoverError("Failover checkpoint is unavailable")
    try:
        if path.stat().st_size > 16_384:
            raise FailoverError("Failover checkpoint is invalid")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise FailoverError("Failover checkpoint is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != _CHECKPOINT_KEYS:
        raise FailoverError("Failover checkpoint is invalid")
    try:
        checkpoint = FailoverCheckpoint(
            schema_version=payload["schema_version"],
            run_id=payload["run_id"],
            task_id=payload["task_id"],
            branch=payload["branch"],
            role=WorkerRole(payload["role"]),
            selected_worker=payload["selected_worker"],
            attempted_workers=tuple(payload["attempted_workers"]),
            last_failure=(
                ProviderFailure(payload["last_failure"])
                if payload["last_failure"] is not None
                else None
            ),
            repository_fingerprint=payload["repository_fingerprint"],
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise FailoverError("Failover checkpoint is invalid") from exc
    return _validate_checkpoint(checkpoint)
