"""Read-only application service for the bounded Dashboard overview."""

from dataclasses import dataclass

from advancore.repositories import (
    ActivityLogRepository,
    KnowledgeItemRepository,
    ProjectRepository,
)


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
    total_activity: int
    project_activity: int
    knowledge_activity: int
    other_activity: int


class DashboardService:
    """Build a read-only summary from existing repository results."""

    def __init__(
        self,
        project_repository: ProjectRepository,
        knowledge_repository: KnowledgeItemRepository,
        activity_repository: ActivityLogRepository,
    ):
        self._projects = project_repository
        self._knowledge = knowledge_repository
        self._activity = activity_repository

    def get_summary(self) -> DashboardSummary:
        projects = list(self._projects.list())
        knowledge = list(self._knowledge.list())
        activities = list(self._activity.list())
        active_projects = sum(item.status == "active" for item in projects)
        archived_projects = sum(item.status == "archived" for item in projects)
        draft_knowledge = sum(item.status == "draft" for item in knowledge)
        project_activity = sum(item.entity_type == "project" for item in activities)
        knowledge_activity = sum(
            item.entity_type == "knowledge" for item in activities
        )
        return DashboardSummary(
            total_projects=len(projects),
            active_projects=active_projects,
            archived_projects=archived_projects,
            other_projects=len(projects) - active_projects - archived_projects,
            total_knowledge=len(knowledge),
            draft_knowledge=draft_knowledge,
            other_knowledge=len(knowledge) - draft_knowledge,
            total_activity=len(activities),
            project_activity=project_activity,
            knowledge_activity=knowledge_activity,
            other_activity=len(activities) - project_activity - knowledge_activity,
        )
