"""Read-only application service for existing activity records."""

from collections.abc import Sequence

from advancore.models import ActivityLog
from advancore.repositories import ActivityLogRepository


class ActivityLogService:
    """Delegate bounded activity reads to an injected repository."""

    def __init__(self, repository: ActivityLogRepository):
        self._repo = repository

    def get_activity(self, activity_id: int) -> ActivityLog | None:
        return self._repo.get_by_id(activity_id)

    def list_activities(self) -> Sequence[ActivityLog]:
        return self._repo.list()
