"""Tests for the repository layer using an isolated SQLite database."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine

from advancore.models import ActivityLog, Base, KnowledgeItem, Project, SystemSetting
from advancore.repositories import (
    ActivityLogRepository,
    KnowledgeItemRepository,
    ProjectRepository,
    SystemSettingRepository,
)
from advancore.services.database import create_session_factory, session_scope


@pytest.fixture
def sqlite_engine():
    """Create an in-memory SQLite engine for isolated tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def sqlite_session_factory(sqlite_engine):
    """Return a session factory bound to the isolated SQLite engine."""
    return create_session_factory(sqlite_engine)


class TestProjectRepository:
    def test_add_and_retrieve_project(self, sqlite_session_factory):
        """A project added through the repository can be retrieved by id."""
        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            project = repo.add(Project(name="Alpha", description="First project"))
            project_id = project.id

        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            found = repo.get_by_id(project_id)
            assert found is not None
            assert found.name == "Alpha"
            assert found.description == "First project"

    def test_list_projects(self, sqlite_session_factory):
        """The repository returns all persisted projects."""
        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            repo.add(Project(name="One"))
            repo.add(Project(name="Two"))

        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            projects = repo.list()
            assert len(projects) == 2
            assert {p.name for p in projects} == {"One", "Two"}

    def test_get_by_name(self, sqlite_session_factory):
        """A project can be looked up by its exact name."""
        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            repo.add(Project(name="Named Project"))

        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            found = repo.get_by_name("Named Project")
            assert found is not None
            assert found.name == "Named Project"

    def test_get_by_name_returns_none_when_missing(self, sqlite_session_factory):
        """Lookup by name returns None when no project matches."""
        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            assert repo.get_by_name("Missing") is None

    def test_save_flushes_refreshes_and_persists_project_changes(
        self, sqlite_session_factory
    ):
        with session_scope(sqlite_session_factory) as session:
            repo = ProjectRepository(session)
            project = repo.add(Project(name="Lifecycle", status="active"))
            project_id = project.id
            project.name = "Updated lifecycle"
            project.status = "archived"
            saved = repo.save(project)
            assert saved is project
            assert saved.name == "Updated lifecycle"
            assert saved.status == "archived"

        with session_scope(sqlite_session_factory) as session:
            persisted = ProjectRepository(session).get_by_id(project_id)
            assert persisted.name == "Updated lifecycle"
            assert persisted.status == "archived"


class TestKnowledgeItemRepository:
    def test_add_and_retrieve_item(self, sqlite_session_factory):
        """A knowledge item added through the repository can be retrieved by id."""
        with session_scope(sqlite_session_factory) as session:
            project_repo = ProjectRepository(session)
            project = project_repo.add(Project(name="Knowledge Base"))
            project_id = project.id

            item_repo = KnowledgeItemRepository(session)
            item = item_repo.add(
                KnowledgeItem(
                    title="How-to",
                    content="Do this.",
                    project_id=project_id,
                )
            )
            item_id = item.id

        with session_scope(sqlite_session_factory) as session:
            repo = KnowledgeItemRepository(session)
            found = repo.get_by_id(item_id)
            assert found is not None
            assert found.title == "How-to"
            assert found.content == "Do this."
            assert found.project_id == project_id

    def test_list_items(self, sqlite_session_factory):
        """The repository returns all persisted knowledge items."""
        with session_scope(sqlite_session_factory) as session:
            repo = KnowledgeItemRepository(session)
            repo.add(KnowledgeItem(title="A", content="content A"))
            repo.add(KnowledgeItem(title="B", content="content B"))

        with session_scope(sqlite_session_factory) as session:
            repo = KnowledgeItemRepository(session)
            items = repo.list()
            assert len(items) == 2
            assert {i.title for i in items} == {"A", "B"}

    def test_list_items_by_project(self, sqlite_session_factory):
        """Items can be filtered by the project they belong to."""
        with session_scope(sqlite_session_factory) as session:
            project_repo = ProjectRepository(session)
            project_a = project_repo.add(Project(name="Project A"))
            project_b = project_repo.add(Project(name="Project B"))
            project_a_id = project_a.id

            item_repo = KnowledgeItemRepository(session)
            item_repo.add(
                KnowledgeItem(title="A1", content="x", project_id=project_a_id)
            )
            item_repo.add(
                KnowledgeItem(title="B1", content="y", project_id=project_b.id)
            )

        with session_scope(sqlite_session_factory) as session:
            item_repo = KnowledgeItemRepository(session)
            a_items = item_repo.list_by_project(project_a_id)
            assert len(a_items) == 1
            assert a_items[0].title == "A1"

    def test_active_replacement_lookup_ignores_archived_attempts(
        self, sqlite_session_factory
    ):
        with session_scope(sqlite_session_factory) as session:
            repo = KnowledgeItemRepository(session)
            source = repo.add(KnowledgeItem(title="Source", content="Content"))
            source_id = source.id
            repo.add(
                KnowledgeItem(
                    title="Old attempt",
                    content="Content",
                    status="archived",
                    replaces_knowledge_item_id=source_id,
                )
            )
            active = repo.add(
                KnowledgeItem(
                    title="Current attempt",
                    content="Content",
                    replaces_knowledge_item_id=source_id,
                )
            )
            active_id = active.id

        with session_scope(sqlite_session_factory) as session:
            repo = KnowledgeItemRepository(session)
            assert repo.get_active_replacement_for(source_id).id == active_id
            assert repo.get_active_replacement_for(999_999) is None


class TestActivityLogRepository:
    def test_add_persists_minimal_activity(self, sqlite_session_factory):
        with session_scope(sqlite_session_factory) as session:
            repo = ActivityLogRepository(session)
            saved = repo.add(
                ActivityLog(
                    action="project_created",
                    entity_type="project",
                    entity_id="17",
                    details=None,
                )
            )
            saved_id = saved.id

        with session_scope(sqlite_session_factory) as session:
            loaded = ActivityLogRepository(session).get_by_id(saved_id)
            assert loaded.action == "project_created"
            assert loaded.entity_type == "project"
            assert loaded.entity_id == "17"
            assert loaded.details is None

    def test_get_and_list_newest_first(self, sqlite_session_factory):
        older_time = datetime(2026, 8, 22, 9, 0)
        newer_time = older_time + timedelta(hours=1)

        with session_scope(sqlite_session_factory) as session:
            older = ActivityLog(action="older", created_at=older_time)
            newer = ActivityLog(action="newer", created_at=newer_time)
            session.add_all([older, newer])
            session.flush()
            older_id = older.id
            newer_id = newer.id

        with session_scope(sqlite_session_factory) as session:
            repo = ActivityLogRepository(session)
            assert repo.get_by_id(older_id).action == "older"
            assert repo.get_by_id(999_999) is None
            assert [record.id for record in repo.list()] == [newer_id, older_id]


class TestSystemSettingRepository:
    def test_add_get_and_update_setting(self, sqlite_session_factory):
        with session_scope(sqlite_session_factory) as session:
            repo = SystemSettingRepository(session)
            saved = repo.add(
                SystemSetting(
                    key="dashboard.command_center.v1",
                    value='{"version":1}',
                    description="Dashboard preference",
                )
            )
            saved_id = saved.id

        with session_scope(sqlite_session_factory) as session:
            repo = SystemSettingRepository(session)
            setting = repo.get_by_key("dashboard.command_center.v1")
            assert setting.id == saved_id
            setting.value = '{"version":2}'
            repo.save(setting)

        with session_scope(sqlite_session_factory) as session:
            repo = SystemSettingRepository(session)
            assert repo.get_by_key("dashboard.command_center.v1").value == (
                '{"version":2}'
            )
            assert repo.get_by_key("missing") is None
