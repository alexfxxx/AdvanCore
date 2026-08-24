"""Knowledge item repository."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import KnowledgeItem


class KnowledgeItemRepository:
    """Persistence operations for :class:`advancore.models.KnowledgeItem`.

    The repository receives a SQLAlchemy session via constructor injection so
    callers control the unit of work (typically through
    :func:`advancore.services.database.session_scope`).
    """

    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, item_id: int) -> KnowledgeItem | None:
        """Return the item with the given primary key, or ``None``."""
        return self._session.get(KnowledgeItem, item_id)

    def list(self) -> Sequence[KnowledgeItem]:
        """Return all knowledge items ordered by creation time."""
        statement = select(KnowledgeItem).order_by(KnowledgeItem.created_at)
        return self._session.scalars(statement).all()

    def add(self, item: KnowledgeItem) -> KnowledgeItem:
        """Persist a new or updated knowledge item and return it."""
        self._session.add(item)
        self._session.flush()
        self._session.refresh(item)
        return item

    def save(self, item: KnowledgeItem) -> KnowledgeItem:
        """Persist changes to an existing knowledge item and return it."""
        self._session.add(item)
        self._session.flush()
        self._session.refresh(item)
        return item

    def list_by_project(self, project_id: int) -> Sequence[KnowledgeItem]:
        """Return knowledge items linked to the given project."""
        statement = (
            select(KnowledgeItem)
            .where(KnowledgeItem.project_id == project_id)
            .order_by(KnowledgeItem.created_at)
        )
        return self._session.scalars(statement).all()
