"""Transactional adapters for confirmed loopback-only primary-console edits."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from secrets import compare_digest
from typing import Iterator, Protocol

from advancore.api.schemas import (
    CustomerResponse,
    DriverResponse,
    KnowledgeResponse,
    LegalEntityResponse,
    ProjectResponse,
    RouteResponse,
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
