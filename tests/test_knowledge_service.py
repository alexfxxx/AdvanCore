"""Deterministic tests for the draft-only KnowledgeService."""

import pytest
from sqlalchemy import create_engine, select

from advancore.models import Base, KnowledgeItem
from advancore.repositories import KnowledgeItemRepository
from advancore.services.database import create_session_factory, session_scope

from advancore.services.knowledge_service import (
    KnowledgeAlreadyArchivedError,
    KnowledgeNotFoundError,
    KnowledgeReadOnlyError,
    KnowledgeService,
    KnowledgeValidationError,
)


class FakeKnowledgeRepository:
    def __init__(self):
        self.items = []
        self.add_calls = 0
        self.save_calls = 0
        self.save_error = None

    def add(self, item):
        self.add_calls += 1
        item.id = len(self.items) + 1
        self.items.append(item)
        return item

    def get_by_id(self, item_id):
        return next((item for item in self.items if item.id == item_id), None)

    def list(self):
        return list(self.items)

    def save(self, item):
        self.save_calls += 1
        if self.save_error:
            raise self.save_error
        return item


class FakeActivityService:
    def __init__(self):
        self.calls = []
        self.error = None

    def record_activity(self, action, entity_type, entity_id):
        self.calls.append((action, entity_type, entity_id))
        if self.error:
            raise self.error

def test_create_draft_normalizes_and_sets_bounded_defaults():
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("  Operating note  ", "  Details  ")
    assert (item.title, item.content, item.status) == (
        "Operating note",
        "Details",
        "draft",
    )
    assert item.project_id is None
    assert item.source_type is None
    assert item.source_reference is None
    assert repo.add_calls == 1


@pytest.mark.parametrize(
    ("title", "content", "expected"),
    [
        ("", "Content", "title is required"),
        ("   ", "Content", "title is required"),
        ("x" * 301, "Content", "300 characters"),
        ("Title", "", "content is required"),
        ("Title", "  ", "content is required"),
    ],
)
def test_create_draft_rejects_invalid_fields_without_persistence(
    title, content, expected
):
    repo = FakeKnowledgeRepository()
    with pytest.raises(KnowledgeValidationError, match=expected):
        KnowledgeService(repo).create_draft(title, content)
    assert repo.add_calls == 0


def test_create_draft_accepts_300_character_title():
    item = KnowledgeService(FakeKnowledgeRepository()).create_draft(
        "x" * 300, "Content"
    )
    assert len(item.title) == 300


def test_list_and_get_delegate_to_repository():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    first = service.create_draft("First", "One")
    second = service.create_draft("Second", "Two")
    assert service.list_items() == [first, second]
    assert service.get_item(second.id) is second
    assert service.get_item(404) is None


def test_edit_draft_normalizes_and_persists_without_changing_lifecycle_fields():
    repo = FakeKnowledgeRepository()
    original = KnowledgeService(repo).create_draft("Original", "Old")
    original.project_id = 12
    original.source_type = "manual"
    edited = KnowledgeService(repo).edit_draft(
        original.id, "  Updated  ", "  New content  "
    )
    assert edited is original
    assert (edited.title, edited.content, edited.status) == (
        "Updated", "New content", "draft"
    )
    assert (edited.project_id, edited.source_type) == (12, "manual")
    assert repo.save_calls == 1


@pytest.mark.parametrize(
    ("title", "content"),
    [(" ", "Content"), ("x" * 301, "Content"), ("Title", " ")],
)
def test_edit_draft_rejects_invalid_fields_without_mutation(title, content):
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Old")
    with pytest.raises(KnowledgeValidationError):
        KnowledgeService(repo).edit_draft(item.id, title, content)
    assert (item.title, item.content) == ("Original", "Old")
    assert repo.save_calls == 0


def test_edit_draft_rejects_missing_and_non_draft_without_save():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    with pytest.raises(KnowledgeNotFoundError):
        service.edit_draft(404, "Title", "Content")
    item = service.create_draft("Original", "Old")
    item.status = "archived"
    with pytest.raises(KnowledgeReadOnlyError, match="read-only"):
        service.edit_draft(item.id, "Title", "Content")
    assert repo.save_calls == 0


def test_edit_failure_restores_in_memory_fields():
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Old")
    repo.save_error = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        KnowledgeService(repo).edit_draft(item.id, "Updated", "New")
    assert (item.title, item.content) == ("Original", "Old")


def test_archive_draft_is_one_way_and_preserves_content():
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Old")
    before = (item.id, item.title, item.content)
    archived = KnowledgeService(repo).archive_draft(item.id)
    assert (archived.id, archived.title, archived.content) == before
    assert archived.status == "archived"
    assert repo.save_calls == 1


def test_archive_rejects_missing_archived_and_unknown_without_save():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    with pytest.raises(KnowledgeNotFoundError):
        service.archive_draft(404)
    item = service.create_draft("Original", "Old")
    item.status = "archived"
    with pytest.raises(KnowledgeAlreadyArchivedError):
        service.archive_draft(item.id)
    item.status = "unexpected"
    with pytest.raises(KnowledgeReadOnlyError):
        service.archive_draft(item.id)
    assert repo.save_calls == 0


def test_archive_failure_restores_draft_status():
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Old")
    repo.save_error = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        KnowledgeService(repo).archive_draft(item.id)
    assert item.status == "draft"


def test_successful_mutations_record_exact_minimal_knowledge_events():
    repo = FakeKnowledgeRepository()
    activity = FakeActivityService()
    service = KnowledgeService(repo, activity)

    created = service.create_draft("Recorded", "Private content")
    service.edit_draft(created.id, "Recorded update", "Changed")
    service.archive_draft(created.id)

    assert activity.calls == [
        ("knowledge_created", "knowledge", created.id),
        ("knowledge_updated", "knowledge", created.id),
        ("knowledge_archived", "knowledge", created.id),
    ]
    assert all("Private" not in str(call) for call in activity.calls)


@pytest.mark.parametrize("operation", ["edit", "archive"])
def test_activity_failure_restores_knowledge_mutation_state(operation):
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Details")
    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")
    service = KnowledgeService(repo, activity)

    with pytest.raises(RuntimeError, match="activity unavailable"):
        if operation == "edit":
            service.edit_draft(item.id, "Changed", "New")
        else:
            service.archive_draft(item.id)

    assert (item.title, item.content, item.status) == (
        "Original",
        "Details",
        "draft",
    )


def test_activity_failure_rolls_back_database_knowledge_insert():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")

    with pytest.raises(RuntimeError, match="activity unavailable"):
        with session_scope(session_factory) as session:
            KnowledgeService(
                KnowledgeItemRepository(session), activity
            ).create_draft("Rolled back", "Private content")

    with session_scope(session_factory) as session:
        assert session.scalars(select(KnowledgeItem)).all() == []
