from datetime import date
from decimal import Decimal, InvalidOperation

from advancore.models import FuelEntry


class FuelEntryValidationError(ValueError): pass


class FuelEntryService:
    def __init__(self, repository): self._repo = repository

    @staticmethod
    def _decimal(value, label, places, *, allow_zero):
        if isinstance(value, bool): raise FuelEntryValidationError(f"{label} is invalid.")
        quantum = Decimal(1).scaleb(-places)
        try:
            number = Decimal(str(value))
            stored = number.quantize(quantum)
        except (InvalidOperation, ValueError): raise FuelEntryValidationError(f"{label} is invalid.") from None
        if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
            raise FuelEntryValidationError(f"{label} is invalid.")
        if number != stored:
            raise FuelEntryValidationError(
                f"{label} must have no more than {places} decimal places."
            )
        return stored

    def record(self, vehicle_id, recorded_on, litres, total_cost=None, odometer_km=None):
        if isinstance(vehicle_id, bool) or not isinstance(vehicle_id, int) or self._repo.vehicle(vehicle_id) is None:
            raise FuelEntryValidationError("Select an existing vehicle.")
        if type(recorded_on) is not date: raise FuelEntryValidationError("Recorded date is required.")
        amount = self._decimal(litres, "Litres", 2, allow_zero=False)
        cost = None if total_cost in (None, "") else self._decimal(total_cost, "Total cost", 2, allow_zero=True)
        odometer = None if odometer_km in (None, "") else self._decimal(odometer_km, "Odometer", 1, allow_zero=True)
        if amount > Decimal("99999999.99") or (cost is not None and cost > Decimal("9999999999.99")) or (odometer is not None and odometer > Decimal("99999999999.9")):
            raise FuelEntryValidationError("Fuel entry value exceeds the supported limit.")
        return self._repo.add(FuelEntry(vehicle_id=vehicle_id, recorded_on=recorded_on, litres=amount, total_cost=cost, odometer_km=odometer))

    def list_entries(self): return self._repo.list()
