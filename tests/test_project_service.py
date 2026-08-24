"""Deterministic tests for the Project application service."""

from collections.abc import Sequence

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from advancore.models import Base, Project
from advancore.repositories import ProjectRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.project_service import (
    DuplicateProjectNameError,
    ProjectAlreadyArchivedError,
    ProjectNotFoundError,
    ProjectReadOnlyError,
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
        self.save_calls = 0
        self.save_error: Exception | None = None

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

    def save(self, project: Project) -> Project:
        self.save_calls += 1
        if self.save_error:
            raise self.save_error
        return project


class FakeActivityService:
    def __init__(self):
        self.calls = []
        self.error = None

    def record_activity(self, action, entity_type, entity_id):
        self.calls.append((action, entity_type, entity_id))
        if self.error:
            raise self.error


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


def _active_project(
    repo: FakeProjectRepository,
    name: str = "Original",
    description: str = "Details",
) -> Project:
    return ProjectService(repo).create_project(name, description)


def test_edit_project_normalizes_and_persists_active_project():
    repo = FakeProjectRepository()
    original = _active_project(repo)
    edited = ProjectService(repo).edit_project(original.id, "  Renamed  ", "  New  ")
    assert edited is original
    assert (edited.name, edited.description, edited.status) == (
        "Renamed",
        "New",
        "active",
    )
    assert repo.save_calls == 1
    assert repo.add_calls == 1


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_edit_project_rejects_invalid_name_without_mutation(name):
    repo = FakeProjectRepository()
    original = _active_project(repo)
    before = (original.name, original.description)
    with pytest.raises(ProjectValidationError):
        ProjectService(repo).edit_project(original.id, name, "Changed")
    assert (original.name, original.description) == before
    assert repo.save_calls == 0


def test_edit_project_accepts_limit_blank_description_and_unchanged_self_name():
    repo = FakeProjectRepository()
    original = _active_project(repo)
    edited = ProjectService(repo).edit_project(original.id, "x" * 200, "   ")
    assert len(edited.name) == 200
    assert edited.description is None
    same = ProjectService(repo).edit_project(original.id, "x" * 200, None)
    assert same is original


def test_edit_project_rejects_name_owned_by_another_project():
    repo = FakeProjectRepository()
    first = _active_project(repo, "First")
    _active_project(repo, "Second")
    with pytest.raises(DuplicateProjectNameError, match="exact name"):
        ProjectService(repo).edit_project(first.id, "Second")
    assert first.name == "First"
    assert repo.save_calls == 0


def test_edit_project_translates_race_and_restores_in_memory_values():
    repo = FakeProjectRepository()
    original = _active_project(repo)
    repo.save_error = IntegrityError("update", {}, RuntimeError("secret violation"))
    with pytest.raises(DuplicateProjectNameError, match="exact name") as error:
        ProjectService(repo).edit_project(original.id, "Racing update", "Changed")
    assert "secret" not in str(error.value)
    assert (original.name, original.description) == ("Original", "Details")


def test_edit_project_missing_and_non_active_outcomes_do_not_save():
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    with pytest.raises(ProjectNotFoundError, match="could not be found"):
        service.edit_project(404, "Missing")
    item = _active_project(repo)
    item.status = "archived"
    with pytest.raises(ProjectReadOnlyError, match="read-only"):
        service.edit_project(item.id, "Changed")
    item.status = "unexpected"
    with pytest.raises(ProjectReadOnlyError, match="read-only"):
        service.edit_project(item.id, "Changed")
    assert repo.save_calls == 0


def test_archive_project_transitions_only_status_and_persists():
    repo = FakeProjectRepository()
    original = _active_project(repo)
    before = (original.id, original.name, original.description)
    archived = ProjectService(repo).archive_project(original.id)
    assert (archived.id, archived.name, archived.description) == before
    assert archived.status == "archived"
    assert repo.save_calls == 1


def test_archive_project_rejects_missing_archived_and_unknown_without_save():
    repo = FakeProjectRepository()
    service = ProjectService(repo)
    with pytest.raises(ProjectNotFoundError):
        service.archive_project(404)
    item = _active_project(repo)
    item.status = "archived"
    with pytest.raises(ProjectAlreadyArchivedError, match="already archived"):
        service.archive_project(item.id)
    item.status = "unexpected"
    with pytest.raises(ProjectReadOnlyError, match="unsupported status"):
        service.archive_project(item.id)
    assert repo.save_calls == 0


def test_archive_failure_restores_active_status():
    repo = FakeProjectRepository()
    item = _active_project(repo)
    repo.save_error = RuntimeError("persistence unavailable")
    with pytest.raises(RuntimeError):
        ProjectService(repo).archive_project(item.id)
    assert item.status == "active"


def test_successful_mutations_record_exact_minimal_project_events():
    repo = FakeProjectRepository()
    activity = FakeActivityService()
    service = ProjectService(repo, activity)

    created = service.create_project("Recorded", "Private description")
    service.edit_project(created.id, "Recorded update", "Changed")
    service.archive_project(created.id)

    assert activity.calls == [
        ("project_created", "project", created.id),
        ("project_updated", "project", created.id),
        ("project_archived", "project", created.id),
    ]
    assert all("Private" not in str(call) for call in activity.calls)


@pytest.mark.parametrize("operation", ["edit", "archive"])
def test_activity_failure_restores_project_mutation_state(operation):
    repo = FakeProjectRepository()
    item = ProjectService(repo).create_project("Original", "Details")
    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")
    service = ProjectService(repo, activity)

    with pytest.raises(RuntimeError, match="activity unavailable"):
        if operation == "edit":
            service.edit_project(item.id, "Changed", "New")
        else:
            service.archive_project(item.id)

    assert (item.name, item.description, item.status) == (
        "Original",
        "Details",
        "active",
    )


def test_activity_failure_rolls_back_database_project_insert():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")

    with pytest.raises(RuntimeError, match="activity unavailable"):
        with session_scope(session_factory) as session:
            ProjectService(ProjectRepository(session), activity).create_project(
                "Rolled back"
            )

    with session_scope(session_factory) as session:
        assert session.scalars(select(Project)).all() == []
