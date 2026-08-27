"""Adapters between the local API and existing AdvanCore application layers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, Sequence

from advancore.agent_runner.goal_task import generate_goal_task
from advancore.agent_runner.worker import DryRunWorkerAdapter
from advancore.api.schemas import (
    KnowledgeResponse,
    OwnerGoalPreviewResponse,
    ProjectResponse,
    SystemStatusResponse,
)


class ReadModelUnavailable(RuntimeError):
    """Raised when a local read model cannot be reached safely."""


class ReadModelGateway(Protocol):
    def status(self) -> SystemStatusResponse: ...

    def list_projects(self) -> Sequence[ProjectResponse]: ...

    def list_knowledge(self) -> Sequence[KnowledgeResponse]: ...


class OwnerGoalPreviewer(Protocol):
    def preview(self, goal: str) -> OwnerGoalPreviewResponse: ...


class DatabaseReadModelGateway:
    """Read existing application services through rollback-only sessions."""

    @staticmethod
    def _database_configured() -> bool:
        return bool(os.getenv("DATABASE_URL"))

    def status(self) -> SystemStatusResponse:
        reachable = False
        if self._database_configured():
            try:
                from advancore.services.database import test_database_connection

                reachable = test_database_connection()
            except (ImportError, RuntimeError):
                reachable = False
        return SystemStatusResponse(
            state="ready" if reachable else "degraded",
            database_configured=self._database_configured(),
            database_reachable=reachable,
            controller_available=True,
        )

    @staticmethod
    def _open_session():
        try:
            from advancore.services.database import SessionLocal
        except (ImportError, RuntimeError) as exc:
            raise ReadModelUnavailable("Local database is not configured.") from exc
        return SessionLocal()

    def list_projects(self) -> Sequence[ProjectResponse]:
        from advancore.repositories import ProjectRepository
        from advancore.services.project_service import ProjectService

        session = self._open_session()
        try:
            projects = ProjectService(ProjectRepository(session)).list_projects()
            return [ProjectResponse.model_validate(project) for project in projects]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Projects are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_knowledge(self) -> Sequence[KnowledgeResponse]:
        from advancore.repositories import KnowledgeItemRepository
        from advancore.services.knowledge_service import KnowledgeService

        session = self._open_session()
        try:
            items = KnowledgeService(
                KnowledgeItemRepository(session)
            ).list_items()
            return [KnowledgeResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Knowledge is temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()


class ControllerOwnerGoalPreviewer:
    """Pass Owner Goal text through the governed dry-run controller path."""

    def __init__(self, repo_root: Path):
        self._repo_root = repo_root.resolve()

    def preview(self, goal: str) -> OwnerGoalPreviewResponse:
        result = generate_goal_task(
            repo_root=self._repo_root,
            tasks_dir=self._repo_root / "tasks",
            goal=goal,
            planner=DryRunWorkerAdapter(),
            execute=False,
        )
        return OwnerGoalPreviewResponse(
            accepted=result.goal_accepted,
            normalized_goal=" ".join(goal.split()),
            status=result.status.value,
            candidate_task_id=result.task_id,
            planner_launched=False,
            task_written=result.task_written,
            execution_requested=False,
            publication_performed=not result.no_publication_performed,
            next_action=result.next_action,
            messages=result.messages,
        )
