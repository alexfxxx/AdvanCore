"""Validated vehicle-register use cases."""

from collections.abc import Sequence
import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from sqlalchemy.exc import IntegrityError

from advancore.models import Vehicle
from advancore.repositories import VehicleRepository
from advancore.services.activity_service import ActivityLogService


VEHICLE_STATUSES = ("active", "out_of_service", "retired")
VEHICLE_TYPES = ("Bus", "lorry", "car")
_REGISTRATION = re.compile(r"[A-Z0-9][A-Z0-9 -]{0,31}")
_CURRENCY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class HirePurchaseProjection:
    remaining_scheduled_payments: int | None
    projected_remaining_scheduled_amount: Decimal | None


def _monthly_payment_date(start: date, payment_number: int) -> date:
    """Return one approved monthly payment date without external dependencies."""
    month_index = start.month - 1 + payment_number
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_hire_purchase_projection(
    loan_start_date: date | None,
    loan_term_months: int | None,
    monthly_instalment: Decimal | None,
    *,
    as_of: date | None = None,
) -> HirePurchaseProjection:
    """Calculate approved read-time values; never infer missing source inputs."""
    if loan_start_date is None or loan_term_months is None:
        return HirePurchaseProjection(None, None)
    if not isinstance(loan_start_date, date):
        raise VehicleValidationError("Loan start date is invalid.")
    if (
        isinstance(loan_term_months, bool)
        or not isinstance(loan_term_months, int)
        or loan_term_months <= 0
    ):
        raise VehicleValidationError("Loan term months must be a positive whole number.")

    calculation_date = as_of or date.today()
    if not isinstance(calculation_date, date):
        raise VehicleValidationError("Calculation date is invalid.")
    month_distance = (
        (calculation_date.year - loan_start_date.year) * 12
        + calculation_date.month
        - loan_start_date.month
    )
    elapsed = max(0, min(month_distance, loan_term_months))
    if elapsed > 0 and _monthly_payment_date(loan_start_date, elapsed) > calculation_date:
        elapsed -= 1
    remaining = loan_term_months - elapsed

    if monthly_instalment is None:
        projected = None
    else:
        try:
            instalment = Decimal(str(monthly_instalment))
        except (InvalidOperation, ValueError) as exc:
            raise VehicleValidationError("Monthly instalment must be a valid amount.") from exc
        if not instalment.is_finite() or instalment < 0:
            raise VehicleValidationError("Monthly instalment must be non-negative.")
        projected = (instalment * remaining).quantize(
            _CURRENCY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    return HirePurchaseProjection(remaining, projected)


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

    @staticmethod
    def _optional_text(value: str | None, label: str, maximum: int) -> str | None:
        normalized = " ".join((value or "").strip().split())
        if len(normalized) > maximum or any(character in normalized for character in "\r\n\t"):
            raise VehicleValidationError(f"{label} must be {maximum} characters or fewer.")
        return normalized or None

    @staticmethod
    def _positive_integer(value: int | None, label: str) -> int | None:
        if value is None: return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise VehicleValidationError(f"{label} must be a positive whole number.")
        return value

    @staticmethod
    def _amount(
        value, label: str, maximum: Decimal = Decimal("9999999999.99")
    ) -> Decimal | None:
        if value is None or value == "": return None
        try: amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc: raise VehicleValidationError(f"{label} must be a valid amount.") from exc
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2 or amount > maximum:
            raise VehicleValidationError(f"{label} must be a non-negative amount with at most 2 decimal places.")
        return amount

    def update_details(self, vehicle_id: int, **values) -> Vehicle:
        vehicle = self._repo.get_by_id(vehicle_id)
        if vehicle is None: raise VehicleNotFoundError("The selected vehicle could not be found.")
        owner_id = values.get("registered_owner_id")
        if owner_id is not None and (isinstance(owner_id, bool) or not isinstance(owner_id, int) or owner_id <= 0):
            raise VehicleValidationError("Registered owner is invalid.")
        if owner_id is not None and not self._repo.legal_entity_exists(owner_id):
            raise VehicleValidationError("Registered owner is invalid.")
        vehicle_type = values.get("vehicle_type") or None
        if vehicle_type is not None and vehicle_type not in VEHICLE_TYPES: raise VehicleValidationError("Vehicle type is invalid.")
        manufacture_year = values.get("manufacture_year")
        if manufacture_year is not None and (isinstance(manufacture_year, bool) or not isinstance(manufacture_year, int) or not 1886 <= manufacture_year <= 9999):
            raise VehicleValidationError("Manufacture year must be between 1886 and 9999.")
        capacity = self._positive_integer(values.get("passenger_capacity"), "Passenger capacity")
        road_tax = self._amount(values.get("road_tax_amount"), "Road-tax amount")
        period = values.get("road_tax_period_months")
        if (road_tax is None and period is not None) or (road_tax is not None and period not in (6, 12)):
            raise VehicleValidationError("Road-tax period must be 6 or 12 months when an amount is recorded.")
        vehicle.registered_owner_id = owner_id
        vehicle.manufacture_year = manufacture_year
        vehicle.passenger_capacity = capacity
        vehicle.vehicle_type = vehicle_type
        for field, label, maximum in (
            ("propellant", "Propellant", 40), ("scheme", "Scheme", 80),
            ("chassis_number", "Chassis number", 80), ("engine_number", "Engine number", 80),
            ("primary_colour", "Primary colour", 40), ("parking_provider", "Parking provider", 120),
            ("parking_location", "Parking location", 200), ("insurance_provider", "Insurance provider", 120),
            ("finance_company", "Finance company", 120),
        ):
            setattr(vehicle, field, self._optional_text(values.get(field), label, maximum))
        for field in ("original_registration_date", "lifespan_expiry", "coe_expiry", "loan_start_date"):
            value = values.get(field)
            if value is not None and not isinstance(value, date): raise VehicleValidationError(f"{field.replace('_', ' ').title()} is invalid.")
            setattr(vehicle, field, value)
        maximum_weight = Decimal("99999999.99")
        vehicle.unladen_weight_kg = self._amount(
            values.get("unladen_weight_kg"), "Unladen weight", maximum_weight
        )
        vehicle.maximum_laden_weight_kg = self._amount(
            values.get("maximum_laden_weight_kg"),
            "Maximum laden weight",
            maximum_weight,
        )
        vehicle.parking_monthly_cost = self._amount(values.get("parking_monthly_cost"), "Monthly parking cost")
        vehicle.insurance_annual_amount = self._amount(values.get("insurance_annual_amount"), "Annual insurance amount")
        vehicle.road_tax_amount = road_tax
        vehicle.road_tax_period_months = period
        vehicle.original_loan_amount = self._amount(
            values.get("original_loan_amount"),
            "Original loan amount",
        )
        vehicle.monthly_instalment = self._amount(
            values.get("monthly_instalment"),
            "Monthly instalment",
        )
        vehicle.loan_term_months = self._positive_integer(
            values.get("loan_term_months"),
            "Loan term months",
        )
        saved = self._repo.save(vehicle)
        if self._activity is not None: self._activity.record_activity("vehicle_details_updated", "vehicle", saved.id)
        return saved

    def list_vehicles(self, registered_owner_id: int | None = None, vehicle_type: str | None = None, passenger_capacity: int | None = None) -> Sequence[Vehicle]:
        if vehicle_type is not None and vehicle_type not in VEHICLE_TYPES: raise VehicleValidationError("Vehicle type is invalid.")
        if passenger_capacity is not None: self._positive_integer(passenger_capacity, "Passenger capacity")
        return self._repo.list(registered_owner_id, vehicle_type, passenger_capacity)
