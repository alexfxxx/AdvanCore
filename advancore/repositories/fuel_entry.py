from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import FuelEntry, Vehicle


class FuelEntryRepository:
    def __init__(self, session: Session): self._session = session
    def vehicle(self, identifier: int): return self._session.get(Vehicle, identifier)
    def add(self, item): self._session.add(item); self._session.flush(); self._session.refresh(item); return item
    def list(self):
        return self._session.scalars(
            select(FuelEntry).order_by(FuelEntry.recorded_on.desc(), FuelEntry.id.desc())
        ).all()
