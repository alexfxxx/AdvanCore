"""Transactional adapters for confirmed loopback-only primary-console edits."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from secrets import compare_digest
from typing import Iterator, Protocol

from advancore.api.schemas import (
    CustomerResponse,
    DriverResponse,
    DriverEmploymentCreateRequest,
    DriverEmploymentResponse,
    FinancialEntryResponse,
    FuelEntryResponse,
    RecurringServiceFuelRuleCreateRequest,
    RecurringServiceFuelRuleResponse,
    KnowledgeResponse,
    LegalEntityResponse,
    ProjectResponse,
    RecurringServiceCreateRequest,
    RecurringServiceReplaceRequest,
    RecurringServiceResponse,
    RecurringServiceStatusRequest,
    RouteResponse,
    TripAssignmentResponse,
    TripResponse,
    VehicleDetailsRequest,
    VehicleResponse,
)


class EditingValidationError(ValueError):
    """Submitted fields do not satisfy the existing application service rules."""


class EditingConflictError(ValueError):
    """The confirmed action conflicts with the current saved lifecycle state."""


class EditingNotFoundError(ValueError):
    """The selected saved record no longer exists."""


class EditingUnavailableError(RuntimeError):
    """The local transactional editing boundary could not complete safely."""


class EditingGateway(Protocol):
    def create_project(self, name: str, description: str | None) -> ProjectResponse: ...

    def edit_project(
        self, identifier: int, name: str, description: str | None
    ) -> ProjectResponse: ...

    def archive_project(self, identifier: int) -> ProjectResponse: ...

    def create_knowledge(self, title: str, content: str) -> KnowledgeResponse: ...

    def edit_knowledge(
        self, identifier: int, title: str, content: str
    ) -> KnowledgeResponse: ...

    def approve_knowledge(
        self,
        identifier: int,
        expected_updated_at: datetime,
        expected_content_sha256: str,
    ) -> KnowledgeResponse: ...

    def archive_knowledge(self, identifier: int) -> KnowledgeResponse: ...

    def replace_knowledge(self, identifier: int) -> KnowledgeResponse: ...

    def create_legal_entity(self, name: str) -> LegalEntityResponse: ...

    def create_vehicle(
        self, registration_number: str, make_model: str | None
    ) -> VehicleResponse: ...

    def set_vehicle_status(self, identifier: int, value: str) -> VehicleResponse: ...

    def update_vehicle_details(
        self, identifier: int, payload: VehicleDetailsRequest
    ) -> VehicleResponse: ...

    def create_driver(
        self, name: str, employee_reference: str | None
    ) -> DriverResponse: ...

    def set_driver_status(self, identifier: int, value: str) -> DriverResponse: ...

    def create_driver_employment_record(
        self, payload: DriverEmploymentCreateRequest
    ) -> DriverEmploymentResponse: ...

    def create_customer(
        self, name: str, customer_reference: str | None
    ) -> CustomerResponse: ...

    def set_customer_status(
        self, identifier: int, value: str
    ) -> CustomerResponse: ...

    def create_route(
        self, route_code: str, origin: str, destination: str
    ) -> RouteResponse: ...

    def set_route_status(self, identifier: int, value: str) -> RouteResponse: ...

    def create_trip(
        self, trip_reference: str, route_id: int, service_date: date
    ) -> TripResponse: ...

    def set_trip_status(self, identifier: int, value: str) -> TripResponse: ...

    def create_trip_assignment(
        self, trip_id: int, vehicle_id: int, driver_id: int
    ) -> TripAssignmentResponse: ...

    def release_trip_assignment(self, identifier: int) -> TripAssignmentResponse: ...

    def create_fuel_entry(
        self,
        vehicle_id: int,
        recorded_on: date,
        litres: Decimal,
        total_cost: Decimal | None,
        odometer_km: Decimal | None,
    ) -> FuelEntryResponse: ...

    def create_financial_entry(
        self,
        entry_date: date,
        entry_type: str,
        amount: Decimal,
        currency_code: str,
        description: str | None,
        trip_id: int | None,
        customer_id: int | None,
        vehicle_id: int | None = None,
        accounting_month: date | None = None,
        expected_payment_date: date | None = None,
        payment_status: str = "unpaid",
        payment_date: date | None = None,
        category: str | None = None,
    ) -> FinancialEntryResponse: ...

    def create_recurring_service(
        self, payload: RecurringServiceCreateRequest
    ) -> RecurringServiceResponse: ...

    def set_recurring_service_status(
        self, identifier: int, payload: RecurringServiceStatusRequest
    ) -> RecurringServiceResponse: ...

    def replace_recurring_service(
        self, identifier: int, payload: RecurringServiceReplaceRequest
    ) -> RecurringServiceResponse: ...

    def create_recurring_service_fuel_rule(
        self,
        identifier: int,
        payload: RecurringServiceFuelRuleCreateRequest,
    ) -> RecurringServiceFuelRuleResponse: ...


class DatabaseEditingGateway:
    """Reuse established services inside one commit-or-rollback unit of work."""

    @staticmethod
    @contextmanager
    def _session() -> Iterator[object]:
        try:
            from advancore.services.database import session_scope
        except (ImportError, RuntimeError) as exc:
            raise EditingUnavailableError(
                "Local editing is unavailable because the database is not configured."
            ) from exc
        with session_scope() as session:
            yield session

    @staticmethod
    def _activity(session):
        from advancore.repositories import ActivityLogRepository
        from advancore.services.activity_service import ActivityLogService

        return ActivityLogService(ActivityLogRepository(session))

    @staticmethod
    def _vehicle_response(item) -> VehicleResponse:
        from advancore.services.vehicle_service import calculate_hire_purchase_projection

        projection = calculate_hire_purchase_projection(
            item.loan_start_date,
            item.loan_term_months,
            item.monthly_instalment,
        )
        return VehicleResponse.model_validate(item).model_copy(
            update={
                "remaining_scheduled_payments": projection.remaining_scheduled_payments,
                "projected_remaining_scheduled_amount": projection.projected_remaining_scheduled_amount,
            }
        )

    def create_project(self, name: str, description: str | None) -> ProjectResponse:
        from advancore.repositories import ProjectRepository
        from advancore.services.project_service import (
            DuplicateProjectNameError,
            ProjectService,
            ProjectValidationError,
        )

        try:
            with self._session() as session:
                item = ProjectService(
                    ProjectRepository(session), self._activity(session)
                ).create_project(name, description)
                return ProjectResponse.model_validate(item)
        except ProjectValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateProjectNameError as exc:
            raise EditingConflictError(str(exc)) from exc

    def edit_project(
        self, identifier: int, name: str, description: str | None
    ) -> ProjectResponse:
        from advancore.repositories import ProjectRepository
        from advancore.services.project_service import (
            DuplicateProjectNameError,
            ProjectNotFoundError,
            ProjectReadOnlyError,
            ProjectService,
            ProjectValidationError,
        )

        try:
            with self._session() as session:
                item = ProjectService(
                    ProjectRepository(session), self._activity(session)
                ).edit_project(identifier, name, description)
                return ProjectResponse.model_validate(item)
        except ProjectValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc
        except (DuplicateProjectNameError, ProjectReadOnlyError) as exc:
            raise EditingConflictError(str(exc)) from exc

    def archive_project(self, identifier: int) -> ProjectResponse:
        from advancore.repositories import ProjectRepository
        from advancore.services.project_service import (
            ProjectAlreadyArchivedError,
            ProjectNotFoundError,
            ProjectReadOnlyError,
            ProjectService,
        )

        try:
            with self._session() as session:
                item = ProjectService(
                    ProjectRepository(session), self._activity(session)
                ).archive_project(identifier)
                return ProjectResponse.model_validate(item)
        except ProjectNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc
        except (ProjectAlreadyArchivedError, ProjectReadOnlyError) as exc:
            raise EditingConflictError(str(exc)) from exc

    @staticmethod
    def _knowledge_service(session):
        from advancore.repositories import KnowledgeItemRepository
        from advancore.services.knowledge_service import KnowledgeService

        return KnowledgeService(
            KnowledgeItemRepository(session), DatabaseEditingGateway._activity(session)
        )

    @staticmethod
    def _translate_knowledge(exc: ValueError) -> None:
        from advancore.services.knowledge_service import (
            KnowledgeNotFoundError,
            KnowledgeValidationError,
        )

        if isinstance(exc, KnowledgeValidationError):
            raise EditingValidationError(str(exc)) from exc
        if isinstance(exc, KnowledgeNotFoundError):
            raise EditingNotFoundError(str(exc)) from exc
        raise EditingConflictError(str(exc)) from exc

    def create_knowledge(self, title: str, content: str) -> KnowledgeResponse:
        try:
            with self._session() as session:
                item = self._knowledge_service(session).create_draft(title, content)
                return KnowledgeResponse.model_validate(item)
        except ValueError as exc:
            self._translate_knowledge(exc)

    def edit_knowledge(
        self, identifier: int, title: str, content: str
    ) -> KnowledgeResponse:
        try:
            with self._session() as session:
                item = self._knowledge_service(session).edit_draft(
                    identifier, title, content
                )
                return KnowledgeResponse.model_validate(item)
        except ValueError as exc:
            self._translate_knowledge(exc)

    def approve_knowledge(
        self,
        identifier: int,
        expected_updated_at: datetime,
        expected_content_sha256: str,
    ) -> KnowledgeResponse:
        from advancore.models import KnowledgeItem

        try:
            with self._session() as session:
                item = session.get(KnowledgeItem, identifier, with_for_update=True)
                if item is None:
                    from advancore.services.knowledge_service import KnowledgeNotFoundError

                    raise KnowledgeNotFoundError(
                        "The selected knowledge item could not be found."
                    )
                saved_updated_at = item.updated_at
                if saved_updated_at.tzinfo is None:
                    saved_updated_at = saved_updated_at.replace(tzinfo=timezone.utc)
                expected = expected_updated_at.astimezone(timezone.utc)
                digest = sha256(item.content.encode("utf-8")).hexdigest()
                if saved_updated_at.astimezone(timezone.utc) != expected or not compare_digest(
                    digest, expected_content_sha256
                ):
                    raise EditingConflictError(
                        "This draft changed after it was reviewed. Refresh and review it again."
                    )
                item = self._knowledge_service(session).approve_draft(identifier)
                return KnowledgeResponse.model_validate(item)
        except EditingConflictError:
            raise
        except ValueError as exc:
            self._translate_knowledge(exc)

    def archive_knowledge(self, identifier: int) -> KnowledgeResponse:
        try:
            with self._session() as session:
                item = self._knowledge_service(session).archive_draft(identifier)
                return KnowledgeResponse.model_validate(item)
        except ValueError as exc:
            self._translate_knowledge(exc)

    def replace_knowledge(self, identifier: int) -> KnowledgeResponse:
        try:
            with self._session() as session:
                item = self._knowledge_service(session).create_replacement_draft(
                    identifier
                )
                return KnowledgeResponse.model_validate(item)
        except ValueError as exc:
            self._translate_knowledge(exc)

    def create_legal_entity(self, name: str) -> LegalEntityResponse:
        from advancore.repositories import LegalEntityRepository
        from advancore.services.legal_entity_service import (
            DuplicateLegalEntityError,
            LegalEntityService,
            LegalEntityValidationError,
        )

        try:
            with self._session() as session:
                item = LegalEntityService(LegalEntityRepository(session)).create(name)
                return LegalEntityResponse.model_validate(item)
        except LegalEntityValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateLegalEntityError as exc:
            raise EditingConflictError(str(exc)) from exc

    def create_vehicle(
        self, registration_number: str, make_model: str | None
    ) -> VehicleResponse:
        from advancore.repositories import VehicleRepository
        from advancore.services.vehicle_service import (
            DuplicateVehicleError,
            VehicleService,
            VehicleValidationError,
        )

        try:
            with self._session() as session:
                item = VehicleService(
                    VehicleRepository(session), self._activity(session)
                ).create_vehicle(registration_number, make_model)
                return self._vehicle_response(item)
        except VehicleValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateVehicleError as exc:
            raise EditingConflictError(str(exc)) from exc

    def set_vehicle_status(self, identifier: int, value: str) -> VehicleResponse:
        from advancore.repositories import VehicleRepository
        from advancore.services.vehicle_service import (
            VehicleNotFoundError,
            VehicleService,
            VehicleValidationError,
        )

        try:
            with self._session() as session:
                item = VehicleService(
                    VehicleRepository(session), self._activity(session)
                ).set_status(identifier, value)
                return self._vehicle_response(item)
        except VehicleValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except VehicleNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc

    def update_vehicle_details(
        self, identifier: int, payload: VehicleDetailsRequest
    ) -> VehicleResponse:
        from advancore.repositories import VehicleRepository
        from advancore.services.vehicle_service import (
            VehicleNotFoundError,
            VehicleService,
            VehicleValidationError,
        )

        values = payload.model_dump(exclude={"confirmed"})
        try:
            with self._session() as session:
                item = VehicleService(
                    VehicleRepository(session), self._activity(session)
                ).update_details(identifier, **values)
                return self._vehicle_response(item)
        except VehicleValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except VehicleNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc

    def create_driver(
        self, name: str, employee_reference: str | None
    ) -> DriverResponse:
        from advancore.repositories import DriverRepository
        from advancore.services.driver_service import (
            DriverService,
            DriverValidationError,
            DuplicateDriverReferenceError,
        )

        try:
            with self._session() as session:
                item = DriverService(
                    DriverRepository(session), self._activity(session)
                ).create_driver(name, employee_reference)
                return DriverResponse.model_validate(item)
        except DriverValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateDriverReferenceError as exc:
            raise EditingConflictError(str(exc)) from exc

    def set_driver_status(self, identifier: int, value: str) -> DriverResponse:
        from advancore.repositories import DriverRepository
        from advancore.services.driver_service import (
            DriverNotFoundError,
            DriverService,
            DriverValidationError,
        )

        try:
            with self._session() as session:
                item = DriverService(
                    DriverRepository(session), self._activity(session)
                ).set_status(identifier, value)
                return DriverResponse.model_validate(item)
        except DriverValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DriverNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc

    def create_driver_employment_record(
        self, payload: DriverEmploymentCreateRequest
    ) -> DriverEmploymentResponse:
        from advancore.repositories import DriverEmploymentRepository
        from advancore.services.driver_employment_service import (
            DriverEmploymentConflictError,
            DriverEmploymentNotFoundError,
            DriverEmploymentService,
            DriverEmploymentValidationError,
        )

        values = payload.model_dump(exclude={"confirmed"})
        try:
            with self._session() as session:
                item = DriverEmploymentService(
                    DriverEmploymentRepository(session), self._activity(session)
                ).create_record(**values)
                return DriverEmploymentResponse.model_validate(item)
        except DriverEmploymentValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DriverEmploymentNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc
        except DriverEmploymentConflictError as exc:
            raise EditingConflictError(str(exc)) from exc

    def create_customer(
        self, name: str, customer_reference: str | None
    ) -> CustomerResponse:
        from advancore.repositories import CustomerRepository
        from advancore.services.customer_service import (
            CustomerService,
            CustomerValidationError,
            DuplicateCustomerReferenceError,
        )

        try:
            with self._session() as session:
                item = CustomerService(
                    CustomerRepository(session), self._activity(session)
                ).create_customer(name, customer_reference)
                return CustomerResponse.model_validate(item)
        except CustomerValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateCustomerReferenceError as exc:
            raise EditingConflictError(str(exc)) from exc

    def set_customer_status(
        self, identifier: int, value: str
    ) -> CustomerResponse:
        from advancore.repositories import CustomerRepository
        from advancore.services.customer_service import (
            CustomerNotFoundError,
            CustomerService,
            CustomerValidationError,
        )

        try:
            with self._session() as session:
                item = CustomerService(
                    CustomerRepository(session), self._activity(session)
                ).set_status(identifier, value)
                return CustomerResponse.model_validate(item)
        except CustomerValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except CustomerNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc

    def create_route(
        self, route_code: str, origin: str, destination: str
    ) -> RouteResponse:
        from advancore.repositories import RouteRepository
        from advancore.services.route_service import (
            DuplicateRouteError,
            RouteService,
            RouteValidationError,
        )

        try:
            with self._session() as session:
                item = RouteService(RouteRepository(session)).create_route(
                    route_code, origin, destination
                )
                return RouteResponse.model_validate(item)
        except RouteValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateRouteError as exc:
            raise EditingConflictError(str(exc)) from exc

    def set_route_status(self, identifier: int, value: str) -> RouteResponse:
        from advancore.repositories import RouteRepository
        from advancore.services.route_service import (
            RouteNotFoundError,
            RouteService,
            RouteValidationError,
        )

        try:
            with self._session() as session:
                item = RouteService(RouteRepository(session)).set_status(
                    identifier, value
                )
                return RouteResponse.model_validate(item)
        except RouteValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except RouteNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc

    def create_trip(
        self, trip_reference: str, route_id: int, service_date: date
    ) -> TripResponse:
        from advancore.repositories import TripRepository
        from advancore.services.trip_service import (
            DuplicateTripError,
            TripService,
            TripValidationError,
        )

        try:
            with self._session() as session:
                item = TripService(TripRepository(session)).create_trip(
                    trip_reference, route_id, service_date
                )
                return TripResponse.model_validate(item)
        except TripValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateTripError as exc:
            raise EditingConflictError(str(exc)) from exc

    def set_trip_status(self, identifier: int, value: str) -> TripResponse:
        from advancore.repositories import TripRepository
        from advancore.services.trip_service import (
            TripNotFoundError,
            TripService,
            TripValidationError,
        )

        try:
            with self._session() as session:
                item = TripService(TripRepository(session)).set_status(
                    identifier, value
                )
                return TripResponse.model_validate(item)
        except TripValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except TripNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc

    def create_trip_assignment(
        self, trip_id: int, vehicle_id: int, driver_id: int
    ) -> TripAssignmentResponse:
        from advancore.repositories import TripAssignmentRepository
        from advancore.services.trip_assignment_service import (
            DuplicateTripAssignmentError,
            TripAssignmentService,
            TripAssignmentValidationError,
        )

        try:
            with self._session() as session:
                item = TripAssignmentService(
                    TripAssignmentRepository(session)
                ).assign(trip_id, vehicle_id, driver_id)
                return TripAssignmentResponse.model_validate(item)
        except TripAssignmentValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except DuplicateTripAssignmentError as exc:
            raise EditingConflictError(str(exc)) from exc

    def release_trip_assignment(self, identifier: int) -> TripAssignmentResponse:
        from advancore.repositories import TripAssignmentRepository
        from advancore.services.trip_assignment_service import (
            TripAssignmentNotFoundError,
            TripAssignmentService,
            TripAssignmentValidationError,
        )

        try:
            with self._session() as session:
                item = TripAssignmentService(
                    TripAssignmentRepository(session)
                ).release(identifier)
                return TripAssignmentResponse.model_validate(item)
        except TripAssignmentValidationError as exc:
            raise EditingConflictError(str(exc)) from exc
        except TripAssignmentNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc

    def create_fuel_entry(
        self,
        vehicle_id: int,
        recorded_on: date,
        litres: Decimal,
        total_cost: Decimal | None,
        odometer_km: Decimal | None,
    ) -> FuelEntryResponse:
        from advancore.repositories import FuelEntryRepository
        from advancore.services.fuel_entry_service import (
            FuelEntryService,
            FuelEntryValidationError,
        )

        try:
            with self._session() as session:
                item = FuelEntryService(FuelEntryRepository(session)).record(
                    vehicle_id, recorded_on, litres, total_cost, odometer_km
                )
                return FuelEntryResponse.model_validate(item)
        except FuelEntryValidationError as exc:
            raise EditingValidationError(str(exc)) from exc

    def create_financial_entry(
        self,
        entry_date: date,
        entry_type: str,
        amount: Decimal,
        currency_code: str,
        description: str | None,
        trip_id: int | None,
        customer_id: int | None,
        vehicle_id: int | None = None,
        accounting_month: date | None = None,
        expected_payment_date: date | None = None,
        payment_status: str = "unpaid",
        payment_date: date | None = None,
        category: str | None = None,
    ) -> FinancialEntryResponse:
        from advancore.repositories import FinancialEntryRepository
        from advancore.services.financial_entry_service import (
            FinancialEntryService,
            FinancialEntryValidationError,
        )

        try:
            with self._session() as session:
                item = FinancialEntryService(
                    FinancialEntryRepository(session)
                ).record(
                    entry_date,
                    entry_type,
                    amount,
                    currency_code,
                    description,
                    trip_id,
                    customer_id,
                    vehicle_id,
                    accounting_month,
                    expected_payment_date,
                    payment_status,
                    payment_date,
                    category,
                )
                return FinancialEntryResponse.model_validate(item)
        except FinancialEntryValidationError as exc:
            raise EditingValidationError(str(exc)) from exc

    def create_recurring_service(
        self, payload: RecurringServiceCreateRequest
    ) -> RecurringServiceResponse:
        from advancore.repositories import (
            CustomerRepository,
            RecurringServiceRepository,
            RouteRepository,
        )
        from advancore.services.recurring_service_service import (
            RecurringServiceConflictError,
            RecurringServiceService,
            RecurringServiceValidationError,
        )

        values = payload.model_dump(exclude={"confirmed"})
        try:
            with self._session() as session:
                item = RecurringServiceService(
                    RecurringServiceRepository(session),
                    CustomerRepository(session),
                    RouteRepository(session),
                    self._activity(session),
                ).create_service(
                    customer_id=values["customer_id"],
                    route_id=values["route_id"],
                    service_reference=values["service_reference"],
                    vehicle_requirement=values.get("vehicle_requirement"),
                    monthly_amount=values["monthly_amount"],
                    currency_code=values["currency_code"],
                    effective_start_date=values["effective_start_date"],
                    effective_end_date=values.get("effective_end_date"),
                    weekdays=values["weekdays"],
                    stops=values["stops"],
                )
                return RecurringServiceResponse.model_validate(item)
        except RecurringServiceValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except RecurringServiceConflictError as exc:
            raise EditingConflictError(str(exc)) from exc

    def set_recurring_service_status(
        self, identifier: int, payload: RecurringServiceStatusRequest
    ) -> RecurringServiceResponse:
        from advancore.repositories import (
            CustomerRepository,
            RecurringServiceRepository,
            RouteRepository,
        )
        from advancore.services.recurring_service_service import (
            RecurringServiceConflictError,
            RecurringServiceNotFoundError,
            RecurringServiceService,
            RecurringServiceValidationError,
        )

        try:
            with self._session() as session:
                item = RecurringServiceService(
                    RecurringServiceRepository(session),
                    CustomerRepository(session),
                    RouteRepository(session),
                    self._activity(session),
                ).set_status(identifier, payload.status)
                return RecurringServiceResponse.model_validate(item)
        except RecurringServiceValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except RecurringServiceNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc
        except RecurringServiceConflictError as exc:
            raise EditingConflictError(str(exc)) from exc

    def replace_recurring_service(
        self, identifier: int, payload: RecurringServiceReplaceRequest
    ) -> RecurringServiceResponse:
        from advancore.repositories import (
            CustomerRepository,
            RecurringServiceRepository,
            RouteRepository,
        )
        from advancore.services.recurring_service_service import (
            RecurringServiceConflictError,
            RecurringServiceNotFoundError,
            RecurringServiceService,
            RecurringServiceValidationError,
        )

        values = payload.model_dump(exclude={"confirmed"})
        try:
            with self._session() as session:
                item = RecurringServiceService(
                    RecurringServiceRepository(session),
                    CustomerRepository(session),
                    RouteRepository(session),
                    self._activity(session),
                ).replace_service(
                    identifier,
                    service_reference=values["service_reference"],
                    route_id=values["route_id"],
                    vehicle_requirement=values.get("vehicle_requirement"),
                    monthly_amount=values["monthly_amount"],
                    currency_code=values["currency_code"],
                    effective_start_date=values["effective_start_date"],
                    effective_end_date=values.get("effective_end_date"),
                    weekdays=values["weekdays"],
                    stops=values["stops"],
                )
                return RecurringServiceResponse.model_validate(item)
        except RecurringServiceValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except RecurringServiceNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc
        except RecurringServiceConflictError as exc:
            raise EditingConflictError(str(exc)) from exc

    def create_recurring_service_fuel_rule(
        self,
        identifier: int,
        payload: RecurringServiceFuelRuleCreateRequest,
    ) -> RecurringServiceFuelRuleResponse:
        from advancore.repositories import FuelMarketRepository, RecurringServiceRepository
        from advancore.services.fuel_market_service import (
            FuelMarketNotFoundError,
            FuelMarketService,
            FuelMarketValidationError,
        )

        values = payload.model_dump(exclude={"confirmed"})
        try:
            with self._session() as session:
                item = FuelMarketService(
                    FuelMarketRepository(session), RecurringServiceRepository(session)
                ).configure_rule(identifier, **values)
                self._activity(session).record_activity(
                    "recurring_service_fuel_rule_created",
                    "recurring_service_fuel_rule",
                    item.id,
                )
                return RecurringServiceFuelRuleResponse.model_validate(item)
        except FuelMarketValidationError as exc:
            raise EditingValidationError(str(exc)) from exc
        except FuelMarketNotFoundError as exc:
            raise EditingNotFoundError(str(exc)) from exc
