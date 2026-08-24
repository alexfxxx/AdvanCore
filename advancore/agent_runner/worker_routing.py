"""Standing-authority wrappers for fixed Kimi-first worker routing."""

from __future__ import annotations

from dataclasses import dataclass
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

