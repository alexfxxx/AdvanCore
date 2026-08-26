from sqlalchemy.exc import IntegrityError

from advancore.models import TripAssignment


class TripAssignmentValidationError(ValueError): pass
class DuplicateTripAssignmentError(ValueError): pass
class TripAssignmentNotFoundError(ValueError): pass


class TripAssignmentService:
    def __init__(self, repository): self._repo = repository

    @staticmethod
    def _identifier(value, label):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise TripAssignmentValidationError(f"Select an existing {label}.")
        return value

    def assign(self, trip_id: int, vehicle_id: int, driver_id: int):
        trip_id = self._identifier(trip_id, "trip")
        vehicle_id = self._identifier(vehicle_id, "vehicle")
        driver_id = self._identifier(driver_id, "driver")
        trip = self._repo.trip(trip_id)
        vehicle = self._repo.vehicle(vehicle_id)
        driver = self._repo.driver(driver_id)
        if trip is None or trip.status != "planned":
            raise TripAssignmentValidationError("Only an existing planned trip can be assigned.")
        if vehicle is None or vehicle.status != "active":
            raise TripAssignmentValidationError("Only an active vehicle can be assigned.")
        if driver is None or driver.status != "active":
            raise TripAssignmentValidationError("Only an active driver can be assigned.")
        if self._repo.for_trip(trip_id) is not None:
            raise DuplicateTripAssignmentError("That trip already has an assignment record.")
        try:
            return self._repo.add(TripAssignment(trip_id=trip_id, vehicle_id=vehicle_id, driver_id=driver_id, status="assigned"))
        except IntegrityError as exc:
            raise DuplicateTripAssignmentError("That trip already has an assignment record.") from exc

    def release(self, identifier: int):
        identifier = self._identifier(identifier, "assignment")
        item = self._repo.get(identifier)
        if item is None: raise TripAssignmentNotFoundError("The selected assignment could not be found.")
        if item.status == "released": raise TripAssignmentValidationError("That assignment is already released.")
        item.status = "released"
        return self._repo.save(item)

    def list_assignments(self): return self._repo.list()
