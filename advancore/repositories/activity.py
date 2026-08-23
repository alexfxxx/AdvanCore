"""Read-only activity-log repository."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import ActivityLog


class ActivityLogRepository:
    """Read existing ActivityLog rows within a caller-owned session."""

    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, activity_id: int) -> ActivityLog | None:
        return self._session.get(ActivityLog, activity_id)

    def list(self) -> Sequence[ActivityLog]:
        statement = select(ActivityLog).order_by(
            ActivityLog.created_at.desc(), ActivityLog.id.desc()
        )
        return self._session.scalars(statement).all()
