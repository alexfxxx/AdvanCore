"""Vehicle persistence operations."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import LegalEntity, Vehicle


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

    def legal_entity_exists(self, identifier: int) -> bool:
        return self._session.get(LegalEntity, identifier) is not None

    def list(self, registered_owner_id: int | None = None, vehicle_type: str | None = None, passenger_capacity: int | None = None) -> Sequence[Vehicle]:
        query = select(Vehicle)
        if registered_owner_id is not None: query = query.where(Vehicle.registered_owner_id == registered_owner_id)
        if vehicle_type is not None: query = query.where(Vehicle.vehicle_type == vehicle_type)
        if passenger_capacity is not None: query = query.where(Vehicle.passenger_capacity == passenger_capacity)
        return self._session.scalars(query.order_by(Vehicle.registration_number, Vehicle.id)).all()
