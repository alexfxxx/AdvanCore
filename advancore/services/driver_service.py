from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from advancore.models import Driver
from advancore.repositories import DriverRepository
from advancore.services.activity_service import ActivityLogService


DRIVER_STATUSES = ("active", "unavailable", "retired")


class DriverValidationError(ValueError): pass
class DuplicateDriverReferenceError(ValueError): pass
class DriverNotFoundError(ValueError): pass


class DriverService:
    def __init__(self, repository: DriverRepository, activity_service: ActivityLogService | None = None):
        self._repo = repository; self._activity = activity_service

    def create_driver(self, name: str, employee_reference: str | None = None) -> Driver:
        normalized_name = " ".join((name or "").strip().split())
        if not normalized_name or len(normalized_name) > 120:
            raise DriverValidationError("Driver name must be 1–120 characters.")
        reference = (employee_reference or "").strip().upper() or None
        if reference is not None and (len(reference) > 40 or any(ch in reference for ch in "\r\n\t")):
            raise DriverValidationError("Employee reference must be 40 characters or fewer.")
        if reference and self._repo.get_by_reference(reference) is not None:
            raise DuplicateDriverReferenceError("That employee reference already exists.")
        try:
            saved = self._repo.add(Driver(name=normalized_name, employee_reference=reference, status="active"))
        except IntegrityError as exc:
            raise DuplicateDriverReferenceError("That employee reference already exists.") from exc
        if self._activity: self._activity.record_activity("driver_created", "driver", saved.id)
        return saved

    def set_status(self, driver_id: int, status: str) -> Driver:
        if status not in DRIVER_STATUSES: raise DriverValidationError("Driver status is invalid.")
        driver = self._repo.get_by_id(driver_id)
        if driver is None: raise DriverNotFoundError("The selected driver could not be found.")
        driver.status = status; saved = self._repo.save(driver)
        if self._activity: self._activity.record_activity("driver_status_changed", "driver", saved.id)
        return saved

    def list_drivers(self) -> Sequence[Driver]: return self._repo.list()
