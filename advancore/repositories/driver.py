from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import Driver


class DriverRepository:
    def __init__(self, session: Session): self._session = session
    def add(self, driver: Driver) -> Driver:
        self._session.add(driver); self._session.flush(); self._session.refresh(driver); return driver
    def save(self, driver: Driver) -> Driver:
        self._session.flush(); self._session.refresh(driver); return driver
    def get_by_id(self, driver_id: int) -> Driver | None:
        return self._session.get(Driver, driver_id)
    def get_by_reference(self, reference: str) -> Driver | None:
        return self._session.scalar(select(Driver).where(Driver.employee_reference == reference))
    def list(self) -> Sequence[Driver]:
        return self._session.scalars(select(Driver).order_by(Driver.name, Driver.id)).all()
