"""Deterministic tests for the read-only ActivityLogService."""

from advancore.models import ActivityLog
from advancore.services.activity_service import ActivityLogService


class FakeActivityRepository:
    def __init__(self, activities=None):
        self.activities = list(activities or [])
        self.requested_ids = []

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
