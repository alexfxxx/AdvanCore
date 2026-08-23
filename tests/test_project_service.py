"""Deterministic tests for the Project application service."""

from collections.abc import Sequence

import pytest
from sqlalchemy.exc import IntegrityError

from advancore.models import Project
from advancore.repositories import ProjectRepository
from advancore.services.project_service import (
    DuplicateProjectNameError,
    ProjectService,
    ProjectValidationError,
)


class FakeProjectRepository(ProjectRepository):
    """In-memory stand-in for ``ProjectRepository``."""

    def __init__(self):
        self._projects: list[Project] = []
        self._next_id = 1
        self.add_calls = 0
        self.add_error: Exception | None = None

    def get_by_id(self, project_id: int) -> Project | None:
        return next((p for p in self._projects if p.id == project_id), None)

    def list(self) -> Sequence[Project]:
        return list(self._projects)

    def add(self, project: Project) -> Project:
        self.add_calls += 1
        if self.add_error:
            raise self.add_error
        project.id = self._next_id
        self._next_id += 1
        self._projects.append(project)
        return project

    def get_by_name(self, name: str) -> Project | None:
        return next((p for p in self._projects if p.name == name), None)


def test_create_project_normalizes_fields_and_defaults_active():
    repo = FakeProjectRepository()
    created = ProjectService(repo).create_project("  Service Test  ", "  Details  ")

    assert created.name == "Service Test"
    assert created.description == "Details"
    assert created.status == "active"
    assert repo.add_calls == 1


@pytest.mark.parametrize("description", [None, "", "   "])
def test_create_project_normalizes_empty_description_to_none(description):
    created = ProjectService(FakeProjectRepository()).create_project(
        "Project", description
    )
    assert created.description is None


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_create_project_rejects_blank_name_without_persisting(name):
    repo = FakeProjectRepository()
    with pytest.raises(ProjectValidationError, match="required"):
        ProjectService(repo).create_project(name)
    assert repo.add_calls == 0


def test_create_project_rejects_name_over_200_characters():
    repo = FakeProjectRepository()
    with pytest.raises(ProjectValidationError, match="200 characters"):
        ProjectService(repo).create_project("x" * 201)
    assert repo.add_calls == 0


def test_create_project_accepts_name_at_200_character_limit():
    created = ProjectService(FakeProjectRepository()).create_project("x" * 200)
    assert len(created.name) == 200


def test_create_project_rejects_exact_duplicate_before_add():
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    service.create_project("Named")
    with pytest.raises(DuplicateProjectNameError, match="exact name"):
        service.create_project("Named")
    assert repo.add_calls == 1


def test_create_project_translates_database_uniqueness_conflict():
    repo = FakeProjectRepository()
    repo.add_error = IntegrityError("insert", {}, RuntimeError("unique violation"))
    with pytest.raises(DuplicateProjectNameError, match="exact name"):
        ProjectService(repo).create_project("Racing insert")
    assert repo.add_calls == 1


def test_get_project_delegates_to_repository():
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    service.create_project("Findable")
    assert service.get_project(1).name == "Findable"


def test_find_project_by_name_uses_exact_match():
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    service.create_project("Named")
    assert service.find_project_by_name("Named").name == "Named"
    assert service.find_project_by_name("named") is None


def test_list_projects_delegates_to_repository():
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    service.create_project("One")
    service.create_project("Two")
    assert [project.name for project in service.list_projects()] == ["One", "Two"]
