"""Standing-authority wrappers for fixed Kimi-first worker routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from advancore.agent_runner.standing_authority import (
    RoutineAction,
    StandingAuthorityError,
    StandingAuthorityService,
)
from advancore.agent_runner.worker import (
    DEFAULT_WORKER_TIMEOUT_SECONDS,
    WorkerAdapter,
    WorkerResult,
    build_worker_adapter,
)
from advancore.agent_runner.worker_registry import WorkerRole, get_worker_profile


class AuthorizedWorkerAdapter(WorkerAdapter):
    """Consume exact routine authority immediately before a worker launch."""

    def __init__(
        self,
        delegate: WorkerAdapter,
        authority: StandingAuthorityService,
        task_id: str,
        branch: str,
        actions: tuple[RoutineAction, ...],
    ):
        self.delegate = delegate
        self.authority = authority
        self.task_id = task_id
        self.branch = branch
        self.actions = actions

    @property
    def name(self) -> str:
        return self.delegate.name

    @property
    def allowed_scope(self) -> list[str]:
        return list(getattr(self.delegate, "allowed_scope", []))

    @allowed_scope.setter
    def allowed_scope(self, value: list[str]) -> None:
        if hasattr(self.delegate, "allowed_scope"):
            self.delegate.allowed_scope = list(value)

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return self.delegate.build_command(instruction, working_dir)

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        try:
            for action in self.actions:
                self.authority.consume(self.task_id, self.branch, action)
        except StandingAuthorityError:
            return WorkerResult(
                success=False,
                message="Routine worker authority is unavailable; owner attention is required.",
                terminal_reason="authority_blocked",
            )
        return self.delegate.run(instruction, working_dir)


@dataclass(frozen=True)
class KimiFirstWorkerRoute:
    primary: AuthorizedWorkerAdapter
    fallback: AuthorizedWorkerAdapter


class WorkerSelectionError(RuntimeError):
    """Raised when controller evidence cannot produce one safe worker."""


class WorkerAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    PAUSED = "PAUSED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    SETUP_REQUIRED = "SETUP_REQUIRED"


@dataclass(frozen=True)
class WorkerAvailabilityEvidence:
    worker: str
    state: WorkerAvailability

    def __post_init__(self) -> None:
        get_worker_profile(self.worker)
        if not isinstance(self.state, WorkerAvailability):
            raise WorkerSelectionError("Worker availability state is invalid")


@dataclass(frozen=True)
class WorkerSelection:
    role: WorkerRole
    selected_worker: str
    considered: tuple[tuple[str, str], ...]


_ROLE_PREFERENCES: dict[WorkerRole, tuple[str, ...]] = {
    WorkerRole.IMPLEMENTATION: ("kimi-swarm", "codex"),
    WorkerRole.PLANNING: ("kimi", "codex"),
    WorkerRole.REVIEW: ("kimi-swarm",),
    WorkerRole.FALLBACK: ("codex",),
}


def governed_worker_preferences(role: WorkerRole | str) -> tuple[str, ...]:
    """Return the immutable code-owned preference order for one routable role."""
    try:
        resolved_role = role if isinstance(role, WorkerRole) else WorkerRole(role)
    except (TypeError, ValueError) as exc:
        raise WorkerSelectionError("Worker role is not routable") from exc
    if resolved_role not in _ROLE_PREFERENCES:
        raise WorkerSelectionError("Worker role is not routable")
    return _ROLE_PREFERENCES[resolved_role]


def select_governed_worker(
    role: WorkerRole | str,
    evidence: tuple[WorkerAvailabilityEvidence, ...],
) -> WorkerSelection:
    """Select from fixed preferences using explicit controller evidence only."""
    try:
        resolved_role = role if isinstance(role, WorkerRole) else WorkerRole(role)
        preferences = governed_worker_preferences(resolved_role)
    except (TypeError, ValueError, WorkerSelectionError) as exc:
        raise WorkerSelectionError("Worker role is not routable") from exc
    if not isinstance(evidence, tuple):
        raise WorkerSelectionError("Worker availability evidence is invalid")
    by_worker: dict[str, WorkerAvailability] = {}
    for item in evidence:
        if not isinstance(item, WorkerAvailabilityEvidence):
            raise WorkerSelectionError("Worker availability evidence is invalid")
        if item.worker in by_worker:
            raise WorkerSelectionError("Duplicate worker availability evidence")
        by_worker[item.worker] = item.state

    considered: list[tuple[str, str]] = []
    for name in preferences:
        profile = get_worker_profile(name)
        state = by_worker.get(name, WorkerAvailability.UNAVAILABLE)
        if not profile.is_eligible(resolved_role):
            considered.append((name, "NOT_AUTHORISED"))
            continue
        if state != WorkerAvailability.AVAILABLE:
            considered.append((name, state.value))
            continue
        considered.append((name, "SELECTED"))
        return WorkerSelection(
            role=resolved_role,
            selected_worker=name,
            considered=tuple(considered),
        )
    raise WorkerSelectionError("No approved worker is currently available")


def build_kimi_first_worker_route(
    *,
    task_id: str,
    branch: str,
    authority: StandingAuthorityService,
    allowed_scope: list[str] | None = None,
    timeout_seconds: int = DEFAULT_WORKER_TIMEOUT_SECONDS,
) -> KimiFirstWorkerRoute:
    """Build the fixed Kimi-Swarm -> Codex route with no caller argv."""
    scope = list(allowed_scope or [])
    primary = AuthorizedWorkerAdapter(
        build_worker_adapter("kimi-swarm", scope, timeout_seconds),
        authority,
        task_id,
        branch,
        (RoutineAction.RUN_WORKER,),
    )
    fallback = AuthorizedWorkerAdapter(
        build_worker_adapter("codex", scope, timeout_seconds),
        authority,
        task_id,
        branch,
        (RoutineAction.APPROVED_FALLBACK, RoutineAction.RUN_WORKER),
    )
    return KimiFirstWorkerRoute(primary, fallback)
