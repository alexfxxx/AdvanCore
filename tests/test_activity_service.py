"""Deterministic tests for the bounded ActivityLogService."""

import pytest

from advancore.models import ActivityLog
from advancore.services.activity_service import (
    ActivityLogService,
    ActivityValidationError,
)


class FakeActivityRepository:
    def __init__(self, activities=None):
        self.activities = list(activities or [])
        self.requested_ids = []
        self.add_calls = 0

    def add(self, activity):
        self.add_calls += 1
        activity.id = len(self.activities) + 1
        self.activities.append(activity)
        return activity

    def list(self):
        return list(self.activities)

    def get_by_id(self, activity_id):
        self.requested_ids.append(activity_id)
        return next(
            (activity for activity in self.activities if activity.id == activity_id),
            None,
        )


def _activity(activity_id, action):
    activity = ActivityLog(action=action)
    activity.id = activity_id
    return activity


def test_list_and_get_delegate_to_repository():
    first = _activity(1, "created")
    second = _activity(2, "archived")
    repository = FakeActivityRepository([second, first])
    service = ActivityLogService(repository)

    assert service.list_activities() == [second, first]
    assert service.get_activity(1) is first
    assert service.get_activity(404) is None
    assert repository.requested_ids == [1, 404]


@pytest.mark.parametrize(
    ("action", "entity_type"),
    [
        ("project_created", "project"),
        ("project_updated", "project"),
        ("project_archived", "project"),
        ("knowledge_created", "knowledge"),
        ("knowledge_updated", "knowledge"),
        ("knowledge_approved", "knowledge"),
        ("knowledge_archived", "knowledge"),
    ],
)
def test_record_activity_accepts_only_approved_minimal_values(action, entity_type):
    repository = FakeActivityRepository()
    recorded = ActivityLogService(repository).record_activity(
        action, entity_type, 17
    )
    assert recorded.action == action
    assert recorded.entity_type == entity_type
    assert recorded.entity_id == "17"
    assert recorded.details is None
    assert repository.add_calls == 1


@pytest.mark.parametrize(
    ("action", "entity_type", "entity_id"),
    [
        ("project_deleted", "project", 1),
        ("project_created", "knowledge", 1),
        ("knowledge_created", "project", 1),
        ("knowledge_created", "knowledge", 0),
        ("knowledge_created", "knowledge", -1),
        ("knowledge_created", "knowledge", True),
        ("knowledge_created", "knowledge", "1"),
    ],
)
def test_record_activity_rejects_unapproved_or_invalid_values(
    action, entity_type, entity_id
):
    repository = FakeActivityRepository()
    with pytest.raises(ActivityValidationError):
        ActivityLogService(repository).record_activity(
            action, entity_type, entity_id
        )
    assert repository.add_calls == 0
