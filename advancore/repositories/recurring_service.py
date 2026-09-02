from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from advancore.models import RecurringService


class RecurringServiceRepository:
    def __init__(self, session: Session):
        self._session = session

    def add(self, item: RecurringService) -> RecurringService:
        self._session.add(item)
        self._session.flush()
        self._session.refresh(item)
        return item

    def save(self, item: RecurringService) -> RecurringService:
        self._session.flush()
        self._session.refresh(item)
        return item

    def get_by_id(self, identifier: int) -> RecurringService | None:
        return self._session.get(RecurringService, identifier)

    def get_by_id_with_children(self, identifier: int) -> RecurringService | None:
        return self._session.execute(
            select(RecurringService)
            .where(RecurringService.id == identifier)
            .options(joinedload(RecurringService.days), joinedload(RecurringService.stops))
        ).unique().scalar_one_or_none()

    def get_by_id_for_update(self, identifier: int) -> RecurringService | None:
        return self._session.execute(
            select(RecurringService)
            .where(RecurringService.id == identifier)
            .with_for_update()
        ).scalar_one_or_none()

    def list_by_customer(self, customer_id: int) -> Sequence[RecurringService]:
        return self._session.execute(
            select(RecurringService)
            .where(RecurringService.customer_id == customer_id)
            .order_by(RecurringService.status, RecurringService.service_reference, RecurringService.id)
            .options(joinedload(RecurringService.days), joinedload(RecurringService.stops))
        ).unique().scalars().all()

    def get_by_customer_and_reference(
        self, customer_id: int, service_reference: str
    ) -> RecurringService | None:
        return self._session.scalars(
            select(RecurringService)
            .where(
                RecurringService.customer_id == customer_id,
                RecurringService.service_reference == service_reference,
                RecurringService.status.in_(("active", "paused")),
            )
            .order_by(RecurringService.effective_start_date.desc(), RecurringService.id.desc())
        ).first()
