"""Read-only application service for the bounded Dashboard overview."""

from dataclasses import dataclass

from advancore.repositories import KnowledgeItemRepository, ProjectRepository


@dataclass(frozen=True)
class DashboardSummary:
    """Bounded aggregate counts displayed by the landing Dashboard."""

    total_projects: int
    active_projects: int
    archived_projects: int
    other_projects: int
    total_knowledge: int
    draft_knowledge: int
    other_knowledge: int


class DashboardService:
    """Build a read-only summary from existing repository results."""

    def __init__(
        self,
        project_repository: ProjectRepository,
        knowledge_repository: KnowledgeItemRepository,
    ):
        self._projects = project_repository
        self._knowledge = knowledge_repository

    def get_summary(self) -> DashboardSummary:
        projects = list(self._projects.list())
        knowledge = list(self._knowledge.list())
        active_projects = sum(item.status == "active" for item in projects)
        archived_projects = sum(item.status == "archived" for item in projects)
        draft_knowledge = sum(item.status == "draft" for item in knowledge)
        return DashboardSummary(
            total_projects=len(projects),
            active_projects=active_projects,
            archived_projects=archived_projects,
            other_projects=len(projects) - active_projects - archived_projects,
            total_knowledge=len(knowledge),
            draft_knowledge=draft_knowledge,
            other_knowledge=len(knowledge) - draft_knowledge,
        )
