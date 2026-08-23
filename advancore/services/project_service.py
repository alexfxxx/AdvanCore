"""Project application service.

Services orchestrate use cases and delegate persistence to repositories.
They must not contain presentation logic and must not depend on Streamlit.
"""

from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from advancore.models import Project
from advancore.repositories import ProjectRepository


class ProjectValidationError(ValueError):
    """Raised when submitted project data is invalid."""


class DuplicateProjectNameError(ValueError):
    """Raised when an exact project name is already in use."""


class ProjectService:
    """Application service for project use cases.

    The repository is injected through the constructor so the service can be
    tested with a fake or in-memory repository without a live database.
    """

    def __init__(self, project_repository: ProjectRepository):
        self._repo = project_repository

    def create_project(self, name: str, description: str | None = None) -> Project:
        """Validate, normalize, and persist an active project.

        The exact-name lookup provides deterministic feedback in the common
        duplicate case. The integrity-error translation also covers a race in
        which another transaction inserts the name after that lookup.
        """
        normalized_name = name.strip()
        if not normalized_name:
            raise ProjectValidationError("Project name is required.")
        if len(normalized_name) > 200:
            raise ProjectValidationError(
                "Project name must be 200 characters or fewer."
            )

        normalized_description = description.strip() if description else None
        if not normalized_description:
            normalized_description = None

        if self._repo.get_by_name(normalized_name) is not None:
            raise DuplicateProjectNameError(
                "A project with this exact name already exists."
            )

        project = Project(
            name=normalized_name,
            description=normalized_description,
            status="active",
        )
        try:
            return self._repo.add(project)
        except IntegrityError as exc:
            raise DuplicateProjectNameError(
                "A project with this exact name already exists."
            ) from exc

    def get_project(self, project_id: int) -> Project | None:
        """Retrieve a project by its primary key."""
        return self._repo.get_by_id(project_id)

    def find_project_by_name(self, name: str) -> Project | None:
        """Retrieve a project by its exact name."""
        return self._repo.get_by_name(name)

    def list_projects(self) -> Sequence[Project]:
        """Return all projects."""
        return self._repo.list()
