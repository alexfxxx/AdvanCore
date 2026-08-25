"""Deterministic tests for bounded Knowledge lifecycle transitions."""

from datetime import datetime, timedelta, timezone
from inspect import signature

import pytest
from sqlalchemy import create_engine, select

from advancore.models import Base, KnowledgeItem
from advancore.repositories import KnowledgeItemRepository
from advancore.services.database import create_session_factory, session_scope

from advancore.services.knowledge_service import (
    KnowledgeAlreadyApprovedError,
    KnowledgeAlreadyArchivedError,
    KnowledgeNotFoundError,
    KnowledgeReadOnlyError,
    KnowledgeReplacementConflictError,
    KnowledgeReplacementPendingError,
    KnowledgeReplacementSourceError,
    KnowledgeService,
    KnowledgeValidationError,
)


class FakeKnowledgeRepository:
    def __init__(self):
        self.items = []
        self.add_calls = 0
        self.save_calls = 0
        self.save_error = None
        self.save_error_on_call = None

    def add(self, item):
        self.add_calls += 1
        item.id = len(self.items) + 1
        self.items.append(item)
        return item

    def get_by_id(self, item_id):
        return next((item for item in self.items if item.id == item_id), None)
    def get_active_replacement_for(self, source_item_id):
        return next(
            (
                item
                for item in self.items
                if item.replaces_knowledge_item_id == source_item_id
                and item.status != "archived"
            ),
            None,
        )

    def list(self):
        return list(self.items)

    def save(self, item):
        self.save_calls += 1
        if self.save_error and (
            self.save_error_on_call is None
            or self.save_calls == self.save_error_on_call
        ):
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
    assert item.replaces_knowledge_item_id is None
    assert item.approved_at is None
    assert item.approved_by is None
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


def test_approve_draft_sets_fixed_owner_and_aware_utc_time_once():
    repo = FakeKnowledgeRepository()
    singapore = timezone(timedelta(hours=8))
    local_time = datetime(2026, 8, 25, 18, 30, tzinfo=singapore)
    service = KnowledgeService(repo, clock=lambda: local_time)
    item = service.create_draft("Official rule", "Approved content")

    approved = service.approve_draft(item.id)

    assert approved is item
    assert approved.status == "approved"
    assert approved.approved_by == "owner"
    assert approved.approved_at == datetime(
        2026, 8, 25, 10, 30, tzinfo=timezone.utc
    )
    assert approved.approved_at.tzinfo is timezone.utc
    assert list(signature(KnowledgeService.approve_draft).parameters) == [
        "self",
        "item_id",
    ]
    assert repo.save_calls == 1

    with pytest.raises(KnowledgeAlreadyApprovedError, match="already approved"):
        service.approve_draft(item.id)
    assert repo.save_calls == 1


def test_approve_rejects_missing_archived_and_unknown_without_save():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    with pytest.raises(KnowledgeNotFoundError):
        service.approve_draft(404)
    item = service.create_draft("Original", "Old")
    item.status = "archived"
    with pytest.raises(KnowledgeReadOnlyError, match="current status"):
        service.approve_draft(item.id)
    item.status = "unexpected"
    with pytest.raises(KnowledgeReadOnlyError, match="current status"):
        service.approve_draft(item.id)
    assert repo.save_calls == 0


def test_approved_item_is_immutable():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    item = service.create_draft("Official", "Content")
    service.approve_draft(item.id)

    with pytest.raises(KnowledgeReadOnlyError, match="read-only"):
        service.edit_draft(item.id, "Changed", "Changed content")
    assert (item.title, item.content, item.status) == (
        "Official",
        "Content",
        "approved",
    )
    assert repo.save_calls == 1


def test_approval_save_failure_restores_all_lifecycle_fields():
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Old")
    repo.save_error = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        KnowledgeService(repo).approve_draft(item.id)

    assert (item.status, item.approved_at, item.approved_by) == (
        "draft",
        None,
        None,
    )


def test_approval_rejects_naive_internal_clock_without_mutation():
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Old")
    service = KnowledgeService(repo, clock=lambda: datetime(2026, 8, 25, 10, 30))

    with pytest.raises(RuntimeError, match="aware time"):
        service.approve_draft(item.id)

    assert (item.status, item.approved_at, item.approved_by) == (
        "draft",
        None,
        None,
    )
    assert repo.save_calls == 0


def test_replacement_draft_copies_saved_fields_without_mutating_source():
    repo = FakeKnowledgeRepository()
    activity = FakeActivityService()
    approved_at = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    service = KnowledgeService(repo, activity, clock=lambda: approved_at)
    source = service.create_draft("Official", "Saved content")
    source.project_id = 12
    source.source_type = "manual"
    source.source_reference = "record-7"
    service.approve_draft(source.id)
    source_before = (
        source.title,
        source.content,
        source.status,
        source.approved_at,
        source.approved_by,
    )

    replacement = service.create_replacement_draft(source.id)

    assert (
        replacement.title,
        replacement.content,
        replacement.project_id,
        replacement.source_type,
        replacement.source_reference,
    ) == ("Official", "Saved content", 12, "manual", "record-7")
    assert replacement.status == "draft"
    assert replacement.approved_at is None
    assert replacement.approved_by is None
    assert replacement.replaces_knowledge_item_id == source.id
    assert (
        source.title,
        source.content,
        source.status,
        source.approved_at,
        source.approved_by,
    ) == source_before
    assert activity.calls[-1] == (
        "knowledge_replacement_created",
        "knowledge",
        replacement.id,
    )


def test_replacement_creation_fails_closed_for_invalid_source_and_conflict():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    with pytest.raises(KnowledgeNotFoundError):
        service.create_replacement_draft(404)

    draft = service.create_draft("Draft", "Content")
    with pytest.raises(KnowledgeReplacementSourceError, match="Only approved"):
        service.create_replacement_draft(draft.id)

    service.approve_draft(draft.id)
    first = service.create_replacement_draft(draft.id)
    with pytest.raises(KnowledgeReplacementConflictError, match="active"):
        service.create_replacement_draft(draft.id)

    service.archive_draft(first.id)
    second = service.create_replacement_draft(draft.id)
    assert second.id != first.id
    assert second.replaces_knowledge_item_id == draft.id


def test_replacement_approval_supersedes_source_and_records_minimal_events():
    repo = FakeKnowledgeRepository()
    activity = FakeActivityService()
    first_time = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    second_time = datetime(2026, 8, 26, 11, 45, tzinfo=timezone.utc)
    times = iter([first_time, second_time])
    service = KnowledgeService(repo, activity, clock=lambda: next(times))
    source = service.create_draft("Official", "Version one")
    service.approve_draft(source.id)
    replacement = service.create_replacement_draft(source.id)
    service.edit_draft(replacement.id, "Official", "Version two")
    activity.calls.clear()

    approved = service.approve_draft(replacement.id)

    assert approved.status == "approved"
    assert approved.approved_at == second_time
    assert approved.approved_by == "owner"
    assert source.status == "superseded"
    assert source.approved_at == first_time
    assert source.approved_by == "owner"
    assert repo.save_calls == 4
    assert activity.calls == [
        ("knowledge_approved", "knowledge", replacement.id),
        ("knowledge_superseded", "knowledge", source.id),
    ]


def test_replacement_approval_rejects_stale_source_without_mutation():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    source = service.create_draft("Official", "Version one")
    service.approve_draft(source.id)
    replacement = service.create_replacement_draft(source.id)
    source.status = "archived"
    save_calls_before = repo.save_calls

    with pytest.raises(KnowledgeReplacementSourceError, match="no longer approved"):
        service.approve_draft(replacement.id)

    assert replacement.status == "draft"
    assert replacement.approved_at is None
    assert replacement.approved_by is None
    assert repo.save_calls == save_calls_before


def test_replacement_second_save_failure_restores_both_lifecycle_states():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    source = service.create_draft("Official", "Version one")
    service.approve_draft(source.id)
    replacement = service.create_replacement_draft(source.id)
    repo.save_error = RuntimeError("database unavailable")
    repo.save_error_on_call = repo.save_calls + 2

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.approve_draft(replacement.id)

    assert source.status == "approved"
    assert (replacement.status, replacement.approved_at, replacement.approved_by) == (
        "draft",
        None,
        None,
    )


def test_replacement_activity_failure_restores_both_lifecycle_states():
    repo = FakeKnowledgeRepository()
    source_time = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    service = KnowledgeService(repo, clock=lambda: source_time)
    source = service.create_draft("Official", "Version one")
    service.approve_draft(source.id)
    replacement = service.create_replacement_draft(source.id)
    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")

    with pytest.raises(RuntimeError, match="activity unavailable"):
        KnowledgeService(repo, activity).approve_draft(replacement.id)

    assert source.status == "approved"
    assert source.approved_at == source_time
    assert (replacement.status, replacement.approved_at, replacement.approved_by) == (
        "draft",
        None,
        None,
    )


def test_approved_source_with_active_replacement_cannot_be_archived():
    repo = FakeKnowledgeRepository()
    service = KnowledgeService(repo)
    source = service.create_draft("Official", "Version one")
    service.approve_draft(source.id)
    service.create_replacement_draft(source.id)
    save_calls_before = repo.save_calls

    with pytest.raises(KnowledgeReplacementPendingError, match="active replacement"):
        service.archive_draft(source.id)

    assert source.status == "approved"
    assert repo.save_calls == save_calls_before


def test_archive_draft_is_one_way_and_preserves_content():
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Old")
    before = (item.id, item.title, item.content)
    archived = KnowledgeService(repo).archive_draft(item.id)
    assert (archived.id, archived.title, archived.content) == before
    assert archived.status == "archived"
    assert repo.save_calls == 1


def test_archive_approved_item_preserves_approval_evidence():
    repo = FakeKnowledgeRepository()
    approved_time = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    service = KnowledgeService(repo, clock=lambda: approved_time)
    item = service.create_draft("Official", "Content")
    service.approve_draft(item.id)

    archived = service.archive_draft(item.id)

    assert archived.status == "archived"
    assert archived.approved_at == approved_time
    assert archived.approved_by == "owner"


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
    service.approve_draft(created.id)
    service.archive_draft(created.id)

    assert activity.calls == [
        ("knowledge_created", "knowledge", created.id),
        ("knowledge_updated", "knowledge", created.id),
        ("knowledge_approved", "knowledge", created.id),
        ("knowledge_archived", "knowledge", created.id),
    ]
    assert all("Private" not in str(call) for call in activity.calls)


@pytest.mark.parametrize("operation", ["edit", "approve", "archive"])
def test_activity_failure_restores_knowledge_mutation_state(operation):
    repo = FakeKnowledgeRepository()
    item = KnowledgeService(repo).create_draft("Original", "Details")
    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")
    service = KnowledgeService(repo, activity)

    with pytest.raises(RuntimeError, match="activity unavailable"):
        if operation == "edit":
            service.edit_draft(item.id, "Changed", "New")
        elif operation == "approve":
            service.approve_draft(item.id)
        else:
            service.archive_draft(item.id)

    assert (item.title, item.content, item.status) == (
        "Original",
        "Details",
        "draft",
    )
    assert item.approved_at is None
    assert item.approved_by is None


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


def test_activity_failure_rolls_back_database_knowledge_approval():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        created = KnowledgeService(
            KnowledgeItemRepository(session)
        ).create_draft("Retained draft", "Private content")
        item_id = created.id

    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")
    with pytest.raises(RuntimeError, match="activity unavailable"):
        with session_scope(session_factory) as session:
            KnowledgeService(
                KnowledgeItemRepository(session), activity
            ).approve_draft(item_id)

    with session_scope(session_factory) as session:
        saved = session.get(KnowledgeItem, item_id)
        assert saved is not None
        assert (saved.status, saved.approved_at, saved.approved_by) == (
            "draft",
            None,
            None,
        )


def test_activity_failure_rolls_back_database_replacement_approval_pair():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        service = KnowledgeService(KnowledgeItemRepository(session))
        source = service.create_draft("Official", "Version one")
        service.approve_draft(source.id)
        replacement = service.create_replacement_draft(source.id)
        source_id = source.id
        replacement_id = replacement.id

    activity = FakeActivityService()
    activity.error = RuntimeError("activity unavailable")
    with pytest.raises(RuntimeError, match="activity unavailable"):
        with session_scope(session_factory) as session:
            KnowledgeService(
                KnowledgeItemRepository(session), activity
            ).approve_draft(replacement_id)

    with session_scope(session_factory) as session:
        source = session.get(KnowledgeItem, source_id)
        replacement = session.get(KnowledgeItem, replacement_id)
        assert source.status == "approved"
        assert replacement.status == "draft"
        assert replacement.approved_at is None
        assert replacement.approved_by is None
