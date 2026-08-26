"""Vehicle persistence operations."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import Vehicle


class VehicleRepository:
    def __init__(self, session: Session):
        self._session = session

    def add(self, vehicle: Vehicle) -> Vehicle:
        self._session.add(vehicle)
        self._session.flush()
        self._session.refresh(vehicle)
        return vehicle

    def save(self, vehicle: Vehicle) -> Vehicle:
        self._session.flush()
        self._session.refresh(vehicle)
        return vehicle

    def get_by_id(self, vehicle_id: int) -> Vehicle | None:
        return self._session.get(Vehicle, vehicle_id)

    def get_by_registration(self, registration_number: str) -> Vehicle | None:
        return self._session.scalar(
            select(Vehicle).where(Vehicle.registration_number == registration_number)
        )

    def list(self) -> Sequence[Vehicle]:
        return self._session.scalars(
            select(Vehicle).order_by(Vehicle.registration_number, Vehicle.id)
        ).all()
