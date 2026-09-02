from collections.abc import Sequence
from datetime import date, time, timedelta
from decimal import Decimal

from advancore.models import Customer, RecurringService, RecurringServiceDay, RecurringServiceStop, Route
from advancore.repositories import CustomerRepository, RecurringServiceRepository, RouteRepository
from advancore.services.activity_service import ActivityLogService


class RecurringServiceValidationError(ValueError):
    pass


class RecurringServiceNotFoundError(ValueError):
    pass


class RecurringServiceConflictError(ValueError):
    pass


_RECURRING_SERVICE_STATUSES = ("active", "paused", "archived")


class RecurringServiceService:
    def __init__(
        self,
        repository: RecurringServiceRepository,
        customer_repository: CustomerRepository,
        route_repository: RouteRepository,
        activity_service: ActivityLogService | None = None,
    ):
        self._repo = repository
        self._customer_repo = customer_repository
        self._route_repo = route_repository
        self._activity = activity_service

    def _validate_common(
        self,
        customer_id: int,
        route_id: int,
        service_reference: str,
        vehicle_requirement: str | None,
        monthly_amount: Decimal,
        currency_code: str,
        effective_start_date: date,
        effective_end_date: date | None,
        weekdays: Sequence[int],
        stops: Sequence[dict],
    ) -> None:
        if not isinstance(customer_id, int) or customer_id <= 0:
            raise RecurringServiceValidationError("Customer identifier is invalid.")
        if not isinstance(route_id, int) or route_id <= 0:
            raise RecurringServiceValidationError("Route identifier is invalid.")
        customer = self._customer_repo.get_by_id(customer_id)
        if customer is None:
            raise RecurringServiceValidationError("The selected customer could not be found.")
        route = self._route_repo.get_by_id(route_id)
        if route is None:
            raise RecurringServiceValidationError("The selected route could not be found.")

        reference = (service_reference or "").strip()
        if not reference or len(reference) > 40:
            raise RecurringServiceValidationError("Service reference must be 1–40 characters.")

        requirement = (vehicle_requirement or "").strip()
        if len(requirement) > 200:
            raise RecurringServiceValidationError(
                "Vehicle requirement must be 200 characters or fewer."
            )

        if effective_end_date is not None and effective_end_date < effective_start_date:
            raise RecurringServiceValidationError("Effective end date cannot be before the start date.")

        try:
            amount = Decimal(monthly_amount)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise RecurringServiceValidationError("Monthly amount must be a number.") from exc
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise RecurringServiceValidationError(
                "Monthly amount must be non-negative with no more than two decimal places."
            )

        currency = (currency_code or "").strip().upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise RecurringServiceValidationError("Currency code must be three letters.")

        if not weekdays:
            raise RecurringServiceValidationError("At least one operating weekday is required.")
        if len(set(weekdays)) != len(weekdays):
            raise RecurringServiceValidationError("Each weekday may only be selected once.")
        if any(day < 0 or day > 6 for day in weekdays):
            raise RecurringServiceValidationError("Weekday must be between 0 (Monday) and 6 (Sunday).")

        if not stops:
            raise RecurringServiceValidationError("At least one stop is required.")
        seen_orders = set()
        for stop in stops:
            order = stop.get("stop_order")
            location = (stop.get("location_name") or "").strip()
            if order is None or not isinstance(order, int) or order < 0:
                raise RecurringServiceValidationError("Stop order must be a non-negative integer.")
            if not location:
                raise RecurringServiceValidationError("Stop location name is required.")
            if location and len(location) > 160:
                raise RecurringServiceValidationError("Stop location name must be 160 characters or fewer.")
            if order in seen_orders:
                raise RecurringServiceValidationError("Stop order must be unique within a service.")
            seen_orders.add(order)
            if not isinstance(stop.get("scheduled_time"), time):
                raise RecurringServiceValidationError("Each stop must have a scheduled time.")

    def create_service(
        self,
        customer_id: int,
        route_id: int,
        service_reference: str,
        vehicle_requirement: str | None,
        monthly_amount: Decimal,
        currency_code: str,
        effective_start_date: date,
        effective_end_date: date | None,
        weekdays: Sequence[int],
        stops: Sequence[dict],
    ) -> RecurringService:
        self._validate_common(
            customer_id,
            route_id,
            service_reference,
            vehicle_requirement,
            monthly_amount,
            currency_code,
            effective_start_date,
            effective_end_date,
            weekdays,
            stops,
        )
        reference = service_reference.strip()
        if self._repo.get_by_customer_and_reference(customer_id, reference):
            raise RecurringServiceConflictError(
                "This customer already has a recurring service with that reference."
            )

        service = RecurringService(
            customer_id=customer_id,
            route_id=route_id,
            service_reference=reference,
            vehicle_requirement=(vehicle_requirement or "").strip() or None,
            monthly_amount=Decimal(monthly_amount),
            currency_code=currency_code.strip().upper(),
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            status="active",
        )
        service.days = [RecurringServiceDay(weekday=day) for day in weekdays]
        service.stops = [
            RecurringServiceStop(
                stop_order=stop["stop_order"],
                location_name=stop["location_name"].strip(),
                scheduled_time=stop["scheduled_time"],
            )
            for stop in sorted(stops, key=lambda item: item["stop_order"])
        ]
        saved = self._repo.add(service)
        if self._activity:
            self._activity.record_activity(
                "recurring_service_created", "recurring_service", saved.id
            )
        return saved

    def list_by_customer(self, customer_id: int) -> Sequence[RecurringService]:
        return self._repo.list_by_customer(customer_id)

    def set_status(self, identifier: int, status: str) -> RecurringService:
        if status not in _RECURRING_SERVICE_STATUSES:
            raise RecurringServiceValidationError("Service status is invalid.")
        item = self._repo.get_by_id_with_children(identifier)
        if item is None:
            raise RecurringServiceNotFoundError("The selected recurring service could not be found.")
        if item.status == "archived":
            raise RecurringServiceConflictError("An archived service cannot be changed.")
        if item.status == status:
            raise RecurringServiceConflictError(f"Service is already {status}.")
        item.status = status
        saved = self._repo.save(item)
        if self._activity:
            self._activity.record_activity(
                "recurring_service_status_changed", "recurring_service", saved.id
            )
        return saved

    def replace_service(
        self,
        identifier: int,
        service_reference: str,
        route_id: int,
        vehicle_requirement: str | None,
        monthly_amount: Decimal,
        currency_code: str,
        effective_start_date: date,
        effective_end_date: date | None,
        weekdays: Sequence[int],
        stops: Sequence[dict],
    ) -> RecurringService:
        prior = self._repo.get_by_id_with_children(identifier)
        if prior is None:
            raise RecurringServiceNotFoundError("The selected recurring service could not be found.")
        if prior.status != "active":
            raise RecurringServiceConflictError("Only an active service can be replaced.")
        if effective_start_date <= prior.effective_start_date:
            raise RecurringServiceValidationError(
                "Replacement effective date must be after the current service start date."
            )

        self._validate_common(
            prior.customer_id,
            route_id,
            service_reference,
            vehicle_requirement,
            monthly_amount,
            currency_code,
            effective_start_date,
            effective_end_date,
            weekdays,
            stops,
        )

        reference = service_reference.strip()
        existing = self._repo.get_by_customer_and_reference(prior.customer_id, reference)
        if existing is not None and existing.id != identifier:
            raise RecurringServiceConflictError(
                "This customer already has a recurring service with that reference."
            )

        prior.status = "archived"
        prior.effective_end_date = effective_start_date - timedelta(days=1)
        self._repo.save(prior)

        replacement = RecurringService(
            customer_id=prior.customer_id,
            route_id=route_id,
            service_reference=reference,
            vehicle_requirement=(vehicle_requirement or "").strip() or None,
            monthly_amount=Decimal(monthly_amount),
            currency_code=currency_code.strip().upper(),
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            status="active",
            replaces_recurring_service_id=prior.id,
        )
        replacement.days = [RecurringServiceDay(weekday=day) for day in weekdays]
        replacement.stops = [
            RecurringServiceStop(
                stop_order=stop["stop_order"],
                location_name=stop["location_name"].strip(),
                scheduled_time=stop["scheduled_time"],
            )
            for stop in sorted(stops, key=lambda item: item["stop_order"])
        ]
        saved = self._repo.add(replacement)
        if self._activity:
            self._activity.record_activity(
                "recurring_service_replaced", "recurring_service", saved.id
            )
        return saved
