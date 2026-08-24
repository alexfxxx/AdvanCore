"""Activity-log persistence inside a caller-owned database session."""

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

    def add(self, activity: ActivityLog) -> ActivityLog:
        """Persist one validated activity record and return it."""
        self._session.add(activity)
        self._session.flush()
        self._session.refresh(activity)
        return activity

    def list(self) -> Sequence[ActivityLog]:
        statement = select(ActivityLog).order_by(
            ActivityLog.created_at.desc(), ActivityLog.id.desc()
        )
        return self._session.scalars(statement).all()
