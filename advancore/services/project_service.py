"""Project application service.

Services orchestrate use cases and delegate persistence to repositories.
They must not contain presentation logic and must not depend on Streamlit.
"""

from collections.abc import Sequence

from advancore.models import Project
from advancore.repositories import ProjectRepository


class ProjectService:
    """Application service for project use cases.

    The repository is injected through the constructor so the service can be
    tested with a fake or in-memory repository without a live database.
    """

    def __init__(self, project_repository: ProjectRepository):
        self._repo = project_repository

    def create_project(self, name: str, description: str | None = None) -> Project:
        """Create and persist a new project."""
        project = Project(name=name, description=description)
        return self._repo.add(project)

    def get_project(self, project_id: int) -> Project | None:
        """Retrieve a project by its primary key."""
        return self._repo.get_by_id(project_id)

    def find_project_by_name(self, name: str) -> Project | None:
        """Retrieve a project by its exact name."""
        return self._repo.get_by_name(name)

    def list_projects(self) -> Sequence[Project]:
        """Return all projects."""
        return self._repo.list()
