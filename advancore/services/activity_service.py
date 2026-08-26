"""Application service for bounded activity recording and viewing."""

from collections.abc import Sequence

from advancore.models import ActivityLog
from advancore.repositories import ActivityLogRepository


class ActivityValidationError(ValueError):
    """Raised when an activity is outside the owner-approved policy."""


_APPROVED_ACTION_ENTITIES = {
    "project_created": "project",
    "project_updated": "project",
    "project_archived": "project",
    "knowledge_created": "knowledge",
    "knowledge_updated": "knowledge",
    "knowledge_approved": "knowledge",
    "knowledge_replacement_created": "knowledge",
    "knowledge_superseded": "knowledge",
    "knowledge_archived": "knowledge",
    "vehicle_created": "vehicle",
    "vehicle_status_changed": "vehicle",
}


class ActivityLogService:
    """Validate bounded writes and delegate reads to an injected repository."""

    def __init__(self, repository: ActivityLogRepository):
        self._repo = repository

    def get_activity(self, activity_id: int) -> ActivityLog | None:
        return self._repo.get_by_id(activity_id)

    def record_activity(
        self, action: str, entity_type: str, entity_id: int
    ) -> ActivityLog:
        """Record one exact approved action without free-text details."""
        expected_entity_type = _APPROVED_ACTION_ENTITIES.get(action)
        if expected_entity_type is None or entity_type != expected_entity_type:
            raise ActivityValidationError("Activity action or entity is not approved.")
        if isinstance(entity_id, bool) or not isinstance(entity_id, int) or entity_id <= 0:
            raise ActivityValidationError(
                "Activity entity identifier must be a positive integer."
            )
        return self._repo.add(
            ActivityLog(
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
                details=None,
            )
        )

    def list_activities(self) -> Sequence[ActivityLog]:
        return self._repo.list()
