"""Tests for the Project application service.

These tests use a fake repository so the service can be verified without a
live database or Streamlit runtime.
"""

from collections.abc import Sequence

from advancore.models import Project
from advancore.repositories import ProjectRepository
from advancore.services.project_service import ProjectService


class FakeProjectRepository(ProjectRepository):
    """In-memory stand-in for ``ProjectRepository``.

    This fake implements the same public surface as the real repository so
    services can be unit-tested in isolation.
    """

    def __init__(self):
        self._projects: list[Project] = []
        self._next_id = 1

    def get_by_id(self, project_id: int) -> Project | None:
        for project in self._projects:
            if project.id == project_id:
                return project
        return None

    def list(self) -> Sequence[Project]:
        return list(self._projects)

    def add(self, project: Project) -> Project:
        project.id = self._next_id
        self._next_id += 1
        self._projects.append(project)
        return project

    def get_by_name(self, name: str) -> Project | None:
        for project in self._projects:
            if project.name == name:
                return project
        return None


def test_create_project_delegates_to_repository():
    """The service creates a Project and delegates persistence to the repo."""
    repo = FakeProjectRepository()
    service = ProjectService(repo)

    created = service.create_project("Service Test", "Created by service")

    assert created.id == 1
    assert created.name == "Service Test"
    assert created.description == "Created by service"
    assert len(repo.list()) == 1


def test_get_project_delegates_to_repository():
    """The service retrieves a project by id through the repository."""
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    service.create_project("Findable")

    found = service.get_project(1)

    assert found is not None
    assert found.name == "Findable"


def test_find_project_by_name_delegates_to_repository():
    """The service retrieves a project by name through the repository."""
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    service.create_project("Named")

    found = service.find_project_by_name("Named")

    assert found is not None
    assert found.name == "Named"


def test_list_projects_delegates_to_repository():
    """The service returns all projects from the repository."""
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    service.create_project("One")
    service.create_project("Two")

    projects = service.list_projects()

    assert len(projects) == 2
    assert {p.name for p in projects} == {"One", "Two"}
