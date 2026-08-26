from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import Driver, Trip, TripAssignment, Vehicle


class TripAssignmentRepository:
    def __init__(self, session: Session): self._session = session
    def trip(self, identifier: int): return self._session.get(Trip, identifier)
    def vehicle(self, identifier: int): return self._session.get(Vehicle, identifier)
    def driver(self, identifier: int): return self._session.get(Driver, identifier)
    def for_trip(self, trip_id: int):
        return self._session.scalar(select(TripAssignment).where(TripAssignment.trip_id == trip_id))
    def get(self, identifier: int): return self._session.get(TripAssignment, identifier)
    def add(self, item): self._session.add(item); self._session.flush(); self._session.refresh(item); return item
    def save(self, item): self._session.flush(); self._session.refresh(item); return item
    def list(self): return self._session.scalars(select(TripAssignment).order_by(TripAssignment.id)).all()
