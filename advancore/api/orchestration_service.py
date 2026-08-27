"""Single-run local coordinator over the existing governed orchestrator."""

from __future__ import annotations

import re
import errno
import hashlib
import json
import os
import pwd
import stat
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from advancore.agent_runner.orchestration import (
    OrchestrationConfig,
    OrchestrationError,
    OrchestrationResult,
    OwnerAction,
    default_orchestration_dir,
    load_checkpoint,
    run_orchestration,
)
from advancore.api.schemas import (
    OrchestrationJobResponse,
    OrchestrationPreviewResponse,
    OrchestrationRunResponse,
)


MAX_PROGRESS_MESSAGE_LENGTH = 500
MAX_PROGRESS_MESSAGES = 8
MAX_JOB_RECORDS = 50
_TERMINAL_JOB_STATES = frozenset({"completed", "failed"})
_CREDENTIAL_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s/@]+@", re.I)
_RUN_ID = re.compile(r"^ORCH-[A-Za-z0-9_-]{1,120}$")
_LOCK_MAX_BYTES = 4096


class OrchestrationJobBusy(RuntimeError):
    """Raised when a second repository-mutating job is requested."""


class OrchestrationJobNotFound(RuntimeError):
    """Raised when a local job identifier is unknown."""


class OrchestrationRunNotFound(RuntimeError):
    """Raised when a governed orchestration checkpoint is unavailable."""


def _repository_identity(repo_root: Path) -> Path | None:
    """Return the shared Git identity, or None for a non-repository test root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return Path(result.stdout.strip()).resolve(strict=True)
    except OSError:
        return None


def default_repository_lock_path(repo_root: Path) -> Path:
    """Return one controller-owned lock shared by this Git repository."""
    identity = _repository_identity(repo_root)
    if identity is None:
        return repo_root / ".agent_runner" / "api" / "orchestration.lock"
    digest = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:32]
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    if sys.platform == "darwin":
        state_root = account_home / "Library" / "Application Support" / "AdvanCore"
    else:
        state_root = account_home / ".local" / "state" / "advancore"
    return state_root / "agent_runner" / "repository-locks" / f"{digest}.lock"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_message(value: object, fallback: str = "Controller is working.") -> str:
    text = " ".join(str(value).split()) if value is not None else fallback
    text = _CREDENTIAL_URL.sub("[redacted-credential-url]", text)
    if not text:
        text = fallback
    if len(text) > MAX_PROGRESS_MESSAGE_LENGTH:
        return text[: MAX_PROGRESS_MESSAGE_LENGTH - 3].rstrip() + "..."
    return text


@dataclass
class _JobRecord:
    job_id: str
    operation: str
    state: str
    created_at: datetime
    updated_at: datetime
    run_id: str | None = None
    task_id: str | None = None
    phase: str | None = None
    status: str | None = None
    owner_decision_required: bool = False
    message: str = "Queued for the governed controller."
    next_action: str | None = None
    known_run_ids: frozenset[str] = frozenset()


class GovernedOrchestrationService:
    """Run one existing orchestration at a time without copying its rules."""

    def __init__(
        self,
        repo_root: Path,
        *,
        runner: Callable[[OrchestrationConfig, Path], OrchestrationResult] = run_orchestration,
        repository_lock_path: Path | None = None,
    ):
        self._repo_root = repo_root.resolve()
        self._runner = runner
        self._lock = threading.Lock()
        self._jobs: dict[str, _JobRecord] = {}
        self._active_job_id: str | None = None
        self._active_thread: threading.Thread | None = None
        self._shutting_down = False
        self._repository_lock_path = Path(
            repository_lock_path or default_repository_lock_path(self._repo_root)
        ).resolve()

    @staticmethod
    def _new_run_config(goal: str, *, apply: bool) -> OrchestrationConfig:
        return OrchestrationConfig(
            goal=goal,
            planner="kimi-swarm",
            fallback_planner="codex",
            worker="kimi-swarm",
            fallback_worker="codex",
            controller="manual",
            repair_attempts=2,
            max_rework=1,
            unattended=True,
            apply=apply,
        )

    def preview(self, goal: str) -> OrchestrationPreviewResponse:
        result = self._runner(
            self._new_run_config(goal, apply=False), self._repo_root
        )
        return OrchestrationPreviewResponse(
            run_id=result.run_id,
            task_id=result.task_id,
            phase=result.phase,
            status=result.status,
            owner_decision_required=result.owner_decision_required,
            next_action=_bounded_message(result.next_action),
            mutations_performed=list(result.mutations_performed),
        )

    def start(self, goal: str) -> OrchestrationJobResponse:
        return self._submit(
            "start",
            self._new_run_config(goal, apply=True),
            run_id=None,
        )

    def resume(self, run_id: str) -> OrchestrationJobResponse:
        return self._submit(
            "resume",
            OrchestrationConfig(resume_run_id=run_id, apply=True),
            run_id=run_id,
        )

    def owner_action(
        self,
        run_id: str,
        action: str,
        owner_note: str | None = None,
    ) -> OrchestrationJobResponse:
        return self._submit(
            "owner_action",
            OrchestrationConfig(
                resume_run_id=run_id,
                apply=True,
                owner_action=OwnerAction(action),
                owner_note=owner_note,
            ),
            run_id=run_id,
        )

    def _submit(
        self,
        operation: str,
        config: OrchestrationConfig,
        *,
        run_id: str | None,
    ) -> OrchestrationJobResponse:
        with self._lock:
            if self._shutting_down:
                raise OrchestrationJobBusy(
                    "The local controller is shutting down and cannot start new work."
                )
            if self._active_job_id is not None:
                active = self._jobs.get(self._active_job_id)
                if active is not None and active.state not in _TERMINAL_JOB_STATES:
                    raise OrchestrationJobBusy(
                        "Another governed orchestration job is already running."
                    )
            self._prune_jobs_locked()
            job_id = f"JOB-{uuid.uuid4().hex}"
            lock_token = uuid.uuid4().hex
            known_run_ids = (
                self._checkpoint_run_ids() if operation == "start" else frozenset()
            )
            self._acquire_repository_lock(job_id, run_id, lock_token)
            now = _now()
            record = _JobRecord(
                job_id=job_id,
                operation=operation,
                state="queued",
                created_at=now,
                updated_at=now,
                run_id=run_id,
                known_run_ids=known_run_ids,
            )
            self._jobs[job_id] = record
            self._active_job_id = job_id

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, config, lock_token),
            name=f"advancore-{job_id}",
            daemon=False,
        )
        with self._lock:
            self._active_thread = thread
        try:
            thread.start()
        except Exception as exc:
            with self._lock:
                self._jobs.pop(job_id, None)
                self._active_job_id = None
                self._active_thread = None
            self._release_repository_lock(job_id, lock_token)
            raise OrchestrationJobBusy(
                "The governed orchestration job could not start safely."
            ) from exc
        return self.get_job(job_id)

    def _prepare_lock_parent(self) -> None:
        parent = self._repository_lock_path.parent
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        details = parent.lstat()
        if (
            stat.S_ISLNK(details.st_mode)
            or not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o022
        ):
            raise OrchestrationJobBusy(
                "The repository orchestration lock location is unsafe."
            )

    def _acquire_repository_lock(
        self, job_id: str, run_id: str | None, token: str
    ) -> None:
        try:
            self._prepare_lock_parent()
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self._repository_lock_path, flags, 0o600)
            try:
                payload = json.dumps(
                    {
                        "job_id": job_id,
                        "run_id": run_id,
                        "token": token,
                        "created_at": _now().isoformat(),
                        "pid": os.getpid(),
                    },
                    sort_keys=True,
                ).encode("utf-8")
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except FileExistsError as exc:
            raise OrchestrationJobBusy(
                "Another governed repository orchestration is active or requires recovery review."
            ) from exc
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise OrchestrationJobBusy(
                    "Another governed repository orchestration is active or requires recovery review."
                ) from exc
            raise OrchestrationJobBusy(
                "The repository orchestration lock could not be established safely."
            ) from exc

    def _release_repository_lock(self, job_id: str, token: str) -> None:
        path = self._repository_lock_path
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags)
            try:
                details = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(details.st_mode)
                    or details.st_uid != os.getuid()
                    or details.st_nlink != 1
                    or details.st_size > _LOCK_MAX_BYTES
                    or stat.S_IMODE(details.st_mode) & 0o077
                ):
                    return
                payload = json.loads(os.read(descriptor, _LOCK_MAX_BYTES).decode("utf-8"))
            finally:
                os.close(descriptor)
            if payload.get("job_id") != job_id or payload.get("token") != token:
                return
            path.unlink()
        except (OSError, UnicodeError, ValueError, AttributeError):
            return

    def _checkpoint_run_ids(self) -> frozenset[str]:
        directory = default_orchestration_dir(self._repo_root)
        try:
            if not directory.exists():
                return frozenset()
            if directory.is_symlink() or not directory.is_dir():
                raise OrchestrationJobBusy(
                    "The orchestration checkpoint directory is unsafe."
                )
            return frozenset(
                path.stem
                for path in directory.iterdir()
                if path.is_file() and not path.is_symlink() and _RUN_ID.fullmatch(path.stem)
            )
        except OSError as exc:
            raise OrchestrationJobBusy(
                "The orchestration checkpoint directory is unavailable."
            ) from exc

    def _discover_started_run(self, snapshot: _JobRecord) -> str | None:
        if snapshot.operation != "start" or snapshot.run_id is not None:
            return snapshot.run_id
        candidates = self._checkpoint_run_ids() - snapshot.known_run_ids
        if len(candidates) != 1:
            return None
        candidate = next(iter(candidates))
        try:
            checkpoint = load_checkpoint(candidate, self._repo_root)
            created_at = datetime.fromisoformat(checkpoint.created_at)
        except (OrchestrationError, OSError, ValueError):
            return None
        if created_at.tzinfo is None or created_at < snapshot.created_at:
            return None
        with self._lock:
            record = self._jobs.get(snapshot.job_id)
            if record is not None and record.run_id is None:
                record.run_id = candidate
        return candidate

    def shutdown(self) -> None:
        """Stop intake and wait for active governed work to reach its checkpoint."""
        with self._lock:
            self._shutting_down = True
            active_thread = self._active_thread
        if active_thread is not None and active_thread is not threading.current_thread():
            active_thread.join()

    def _prune_jobs_locked(self) -> None:
        """Keep bounded process-local progress history; never remove active work."""
        removable = sorted(
            (
                record
                for record in self._jobs.values()
                if record.state in _TERMINAL_JOB_STATES
                and record.job_id != self._active_job_id
            ),
            key=lambda record: record.updated_at,
        )
        while len(self._jobs) >= MAX_JOB_RECORDS and removable:
            self._jobs.pop(removable.pop(0).job_id, None)

    def _run_job(
        self, job_id: str, config: OrchestrationConfig, lock_token: str
    ) -> None:
        self._update_job(
            job_id,
            state="running",
            message="Controller accepted the request and is advancing governed state.",
        )
        try:
            result = self._runner(config, self._repo_root)
            message = (
                result.blocking_reason
                or (result.messages[-1] if result.messages else None)
                or result.next_action
            )
            self._update_job(
                job_id,
                state="completed",
                run_id=result.run_id,
                task_id=result.task_id,
                phase=result.phase,
                status=result.status,
                owner_decision_required=result.owner_decision_required,
                message=_bounded_message(message),
                next_action=_bounded_message(result.next_action),
            )
        except (OrchestrationError, OSError, ValueError) as exc:
            self._update_job(
                job_id,
                state="failed",
                message=_bounded_message(
                    f"Governed orchestration stopped: {type(exc).__name__}."
                ),
                next_action="Inspect the repository and controller evidence before retrying.",
            )
        except Exception as exc:  # pragma: no cover - defensive redaction boundary
            self._update_job(
                job_id,
                state="failed",
                message=f"Governed orchestration stopped: {type(exc).__name__}.",
                next_action="Inspect local controller logs before retrying.",
            )
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None
                if self._active_thread is threading.current_thread():
                    self._active_thread = None
            self._release_repository_lock(job_id, lock_token)

    def _update_job(self, job_id: str, **changes: object) -> None:
        with self._lock:
            record = self._jobs[job_id]
            for name, value in changes.items():
                setattr(record, name, value)
            record.updated_at = _now()

    def get_job(self, job_id: str) -> OrchestrationJobResponse:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise OrchestrationJobNotFound("Orchestration job was not found.")
            snapshot = _JobRecord(**record.__dict__)

        if snapshot.run_id is None and snapshot.state not in _TERMINAL_JOB_STATES:
            snapshot.run_id = self._discover_started_run(snapshot)

        if snapshot.run_id and snapshot.state not in _TERMINAL_JOB_STATES:
            try:
                checkpoint = load_checkpoint(snapshot.run_id, self._repo_root)
                snapshot.task_id = checkpoint.task_id
                snapshot.phase = checkpoint.phase
                snapshot.status = checkpoint.status
                snapshot.updated_at = datetime.fromisoformat(checkpoint.updated_at)
                if checkpoint.messages:
                    snapshot.message = _bounded_message(checkpoint.messages[-1])
            except (OrchestrationError, OSError, ValueError):
                pass

        return OrchestrationJobResponse(
            job_id=snapshot.job_id,
            operation=snapshot.operation,
            state=snapshot.state,
            terminal=snapshot.state in _TERMINAL_JOB_STATES,
            run_id=snapshot.run_id,
            task_id=snapshot.task_id,
            phase=snapshot.phase,
            status=snapshot.status,
            owner_decision_required=snapshot.owner_decision_required,
            message=_bounded_message(snapshot.message),
            next_action=snapshot.next_action,
            events_url=f"/api/orchestration-jobs/{snapshot.job_id}/events",
            updated_at=snapshot.updated_at,
        )

    def get_current_job(self) -> OrchestrationJobResponse:
        """Return active work, or the latest bounded terminal snapshot."""
        with self._lock:
            if self._active_job_id in self._jobs:
                job_id = self._active_job_id
            elif self._jobs:
                job_id = max(
                    self._jobs.values(), key=lambda record: record.updated_at
                ).job_id
            else:
                raise OrchestrationJobNotFound(
                    "No orchestration job exists in this server session."
                )
        return self.get_job(job_id)

    def get_run(self, run_id: str) -> OrchestrationRunResponse:
        try:
            checkpoint = load_checkpoint(run_id, self._repo_root)
            updated_at = datetime.fromisoformat(checkpoint.updated_at)
        except (OrchestrationError, OSError, ValueError) as exc:
            raise OrchestrationRunNotFound(
                "Orchestration checkpoint was not found or is invalid."
            ) from exc
        return OrchestrationRunResponse(
            run_id=checkpoint.run_id,
            task_id=checkpoint.task_id,
            phase=checkpoint.phase,
            status=checkpoint.status,
            branch=checkpoint.branch,
            completed_phases=list(checkpoint.completed_phases),
            owner_decision_count=checkpoint.owner_decision_count,
            push_verified=checkpoint.push_verified,
            updated_at=updated_at,
            messages=[
                _bounded_message(message)
                for message in checkpoint.messages[-MAX_PROGRESS_MESSAGES:]
            ],
        )
