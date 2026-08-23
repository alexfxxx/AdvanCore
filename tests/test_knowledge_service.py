"""Deterministic tests for the draft-only KnowledgeService."""

import pytest

from advancore.services.knowledge_service import (
    KnowledgeService,
    KnowledgeValidationError,
)


class FakeKnowledgeRepository:
    def __init__(self):
        self.items = []
        self.add_calls = 0

    def add(self, item):
        self.add_calls += 1
        item.id = len(self.items) + 1
        self.items.append(item)
        return item

    def get_by_id(self, item_id):
        return next((item for item in self.items if item.id == item_id), None)

    def list(self):
        return list(self.items)


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
