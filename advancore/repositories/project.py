"""Project repository."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import Project


class ProjectRepository:
    """Persistence operations for :class:`advancore.models.Project`.

    The repository receives a SQLAlchemy session via constructor injection so
    callers control the unit of work (typically through
    :func:`advancore.services.database.session_scope`).
    """

    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, project_id: int) -> Project | None:
        """Return the project with the given primary key, or ``None``."""
        return self._session.get(Project, project_id)

    def list(self) -> Sequence[Project]:
        """Return all projects ordered by creation time."""
        statement = select(Project).order_by(Project.created_at)
        return self._session.scalars(statement).all()

    def add(self, project: Project) -> Project:
        """Persist a new or updated project and return it."""
        self._session.add(project)
        self._session.flush()
        self._session.refresh(project)
        return project

    def get_by_name(self, name: str) -> Project | None:
        """Return the project with the exact name, or ``None``."""
        statement = select(Project).where(Project.name == name)
        return self._session.scalar(statement)
