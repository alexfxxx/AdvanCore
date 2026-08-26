"""Validated vehicle-register use cases."""

from collections.abc import Sequence
import re

from sqlalchemy.exc import IntegrityError

from advancore.models import Vehicle
from advancore.repositories import VehicleRepository
from advancore.services.activity_service import ActivityLogService


VEHICLE_STATUSES = ("active", "out_of_service", "retired")
_REGISTRATION = re.compile(r"[A-Z0-9][A-Z0-9 -]{0,31}")


class VehicleValidationError(ValueError):
    pass


class DuplicateVehicleError(ValueError):
    pass


class VehicleNotFoundError(ValueError):
    pass


class VehicleService:
    def __init__(
        self,
        repository: VehicleRepository,
        activity_service: ActivityLogService | None = None,
    ):
        self._repo = repository
        self._activity = activity_service

    @staticmethod
    def _registration(value: str) -> str:
        normalized = " ".join((value or "").strip().upper().split())
        if not _REGISTRATION.fullmatch(normalized):
            raise VehicleValidationError(
                "Registration number must use 1–32 letters, numbers, spaces, or hyphens."
            )
        return normalized

    @staticmethod
    def _make_model(value: str | None) -> str | None:
        normalized = (value or "").strip()
        if len(normalized) > 120:
            raise VehicleValidationError("Make/model must be 120 characters or fewer.")
        return normalized or None

    def create_vehicle(
        self, registration_number: str, make_model: str | None = None
    ) -> Vehicle:
        registration = self._registration(registration_number)
        description = self._make_model(make_model)
        if self._repo.get_by_registration(registration) is not None:
            raise DuplicateVehicleError("That registration number already exists.")
        try:
            saved = self._repo.add(
                Vehicle(
                    registration_number=registration,
                    make_model=description,
                    status="active",
                )
            )
        except IntegrityError as exc:
            raise DuplicateVehicleError(
                "That registration number already exists."
            ) from exc
        if self._activity is not None:
            self._activity.record_activity("vehicle_created", "vehicle", saved.id)
        return saved

    def set_status(self, vehicle_id: int, status: str) -> Vehicle:
        if status not in VEHICLE_STATUSES:
            raise VehicleValidationError("Vehicle status is invalid.")
        vehicle = self._repo.get_by_id(vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError("The selected vehicle could not be found.")
        vehicle.status = status
        saved = self._repo.save(vehicle)
        if self._activity is not None:
            self._activity.record_activity("vehicle_status_changed", "vehicle", saved.id)
        return saved

    def list_vehicles(self) -> Sequence[Vehicle]:
        return self._repo.list()
