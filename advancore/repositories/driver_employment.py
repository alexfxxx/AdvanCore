from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import Driver, DriverEmploymentRecord


class DriverEmploymentRepository:
    def __init__(self, session: Session):
        self._session = session

    def add(self, item: DriverEmploymentRecord) -> DriverEmploymentRecord:
        self._session.add(item)
        self._session.flush()
        self._session.refresh(item)
        return item

    def driver(self, identifier: int) -> Driver | None:
        return self._session.get(Driver, identifier)

    def get_by_driver_and_month(
        self, driver_id: int, effective_month: date
    ) -> DriverEmploymentRecord | None:
        return self._session.scalar(
            select(DriverEmploymentRecord).where(
                DriverEmploymentRecord.driver_id == driver_id,
                DriverEmploymentRecord.effective_month == effective_month,
            )
        )

    def list_by_driver(self, driver_id: int) -> Sequence[DriverEmploymentRecord]:
        return self._session.scalars(
            select(DriverEmploymentRecord)
            .where(DriverEmploymentRecord.driver_id == driver_id)
            .order_by(
                DriverEmploymentRecord.effective_month.desc(),
                DriverEmploymentRecord.id.desc(),
            )
        ).all()
