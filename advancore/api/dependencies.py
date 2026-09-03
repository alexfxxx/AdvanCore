"""Adapters between the local API and existing AdvanCore application layers."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol, Sequence

from advancore.agent_runner.goal_task import generate_goal_task
from advancore.agent_runner.worker import DryRunWorkerAdapter
from advancore.api.schemas import (
    ActivityLogResponse,
    CustomerResponse,
    DriverResponse,
    DriverEmploymentResponse,
    FinancialEntryResponse,
    FuelEntryResponse,
    KnowledgeResponse,
    DispatchBoardResponse,
    DispatchResourceResponse,
    DispatchRowResponse,
    FleetResponse,
    FuelDailyTotalResponse,
    FuelIntelligenceResponse,
    FuelMarketBenchmarkResponse,
    FuelMarketHistoryResponse,
    FuelAdjustmentDraftResponse,
    FuelPriceObservationResponse,
    LegalEntityResponse,
    OwnerGoalPreviewResponse,
    ProjectResponse,
    RecurringServiceResponse,
    RecurringServiceFuelRuleResponse,
    RouteResponse,
    SystemStatusResponse,
    TripAssignmentResponse,
    TripResponse,
    VehicleResponse,
)


class ReadModelUnavailable(RuntimeError):
    """Raised when a local read model cannot be reached safely."""


class ReadModelGateway(Protocol):
    def status(self) -> SystemStatusResponse: ...

    def list_projects(self) -> Sequence[ProjectResponse]: ...

    def list_knowledge(self) -> Sequence[KnowledgeResponse]: ...

    def list_drivers(self) -> Sequence[DriverResponse]: ...

    def list_driver_employment_records(
        self, driver_id: int
    ) -> Sequence[DriverEmploymentResponse]: ...

    def list_customers(self) -> Sequence[CustomerResponse]: ...

    def list_routes(self) -> Sequence[RouteResponse]: ...

    def list_trips(self) -> Sequence[TripResponse]: ...

    def list_trip_assignments(self) -> Sequence[TripAssignmentResponse]: ...

    def list_fuel_entries(self) -> Sequence[FuelEntryResponse]: ...

    def list_financial_entries(self) -> Sequence[FinancialEntryResponse]: ...

    def list_activities(self) -> Sequence[ActivityLogResponse]: ...

    def list_recurring_services_by_customer(
        self, customer_id: int
    ) -> Sequence[RecurringServiceResponse]: ...

    def fleet(
        self,
        registered_owner_id: int | None = None,
        vehicle_type: str | None = None,
        passenger_capacity: int | None = None,
    ) -> FleetResponse: ...

    def dispatch(self, service_date: date) -> DispatchBoardResponse: ...

    def fuel_intelligence(self) -> FuelIntelligenceResponse: ...

    def fuel_market_benchmark(self) -> FuelMarketBenchmarkResponse: ...

    def recurring_service_fuel_adjustment(
        self, recurring_service_id: int
    ) -> FuelAdjustmentDraftResponse: ...


class OwnerGoalPreviewer(Protocol):
    def preview(self, goal: str) -> OwnerGoalPreviewResponse: ...


class DatabaseReadModelGateway:
    """Read existing application services through rollback-only sessions."""

    def __init__(self, repo_root: Path | None = None):
        self._repo_root = (
            repo_root or Path(__file__).resolve().parents[2]
        ).resolve()

    @staticmethod
    def _database_configured() -> bool:
        return bool(os.getenv("DATABASE_URL"))

    def status(self) -> SystemStatusResponse:
        reachable = False
        if self._database_configured():
            try:
                from advancore.services.database import test_database_connection

                reachable = test_database_connection()
            except (ImportError, RuntimeError):
                reachable = False
        return SystemStatusResponse(
            state="ready" if reachable else "degraded",
            database_configured=self._database_configured(),
            database_reachable=reachable,
            controller_available=True,
        )

    @staticmethod
    def _open_session():
        try:
            from advancore.services.database import SessionLocal
        except (ImportError, RuntimeError) as exc:
            raise ReadModelUnavailable("Local database is not configured.") from exc
        return SessionLocal()

    def list_projects(self) -> Sequence[ProjectResponse]:
        from advancore.repositories import ProjectRepository
        from advancore.services.project_service import ProjectService

        session = self._open_session()
        try:
            projects = ProjectService(ProjectRepository(session)).list_projects()
            return [ProjectResponse.model_validate(project) for project in projects]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Projects are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_knowledge(self) -> Sequence[KnowledgeResponse]:
        from advancore.repositories import KnowledgeItemRepository
        from advancore.services.knowledge_service import KnowledgeService

        session = self._open_session()
        try:
            items = KnowledgeService(
                KnowledgeItemRepository(session)
            ).list_items()
            return [KnowledgeResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Knowledge is temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_drivers(self) -> Sequence[DriverResponse]:
        from advancore.repositories import DriverRepository
        from advancore.services.driver_service import DriverService

        session = self._open_session()
        try:
            items = DriverService(DriverRepository(session)).list_drivers()
            return [DriverResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable("Drivers are temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def list_driver_employment_records(
        self, driver_id: int
    ) -> Sequence[DriverEmploymentResponse]:
        from advancore.repositories import DriverEmploymentRepository
        from advancore.services.driver_employment_service import DriverEmploymentService

        session = self._open_session()
        try:
            items = DriverEmploymentService(
                DriverEmploymentRepository(session)
            ).list_by_driver(driver_id)
            return [DriverEmploymentResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Driver employment records are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_customers(self) -> Sequence[CustomerResponse]:
        from advancore.repositories import CustomerRepository
        from advancore.services.customer_service import CustomerService

        session = self._open_session()
        try:
            items = CustomerService(CustomerRepository(session)).list_customers()
            return [CustomerResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable("Customers are temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def list_routes(self) -> Sequence[RouteResponse]:
        from advancore.repositories import RouteRepository
        from advancore.services.route_service import RouteService

        session = self._open_session()
        try:
            items = RouteService(RouteRepository(session)).list_routes()
            return [RouteResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable("Routes are temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def list_trips(self) -> Sequence[TripResponse]:
        from advancore.repositories import TripRepository
        from advancore.services.trip_service import TripService

        session = self._open_session()
        try:
            items = TripService(TripRepository(session)).list_trips()
            return [TripResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable("Trips are temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def list_trip_assignments(self) -> Sequence[TripAssignmentResponse]:
        from advancore.repositories import TripAssignmentRepository
        from advancore.services.trip_assignment_service import TripAssignmentService

        session = self._open_session()
        try:
            items = TripAssignmentService(
                TripAssignmentRepository(session)
            ).list_assignments()
            return [TripAssignmentResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Trip assignments are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_fuel_entries(self) -> Sequence[FuelEntryResponse]:
        from advancore.repositories import FuelEntryRepository
        from advancore.services.fuel_entry_service import FuelEntryService

        session = self._open_session()
        try:
            items = FuelEntryService(FuelEntryRepository(session)).list_entries()
            return [FuelEntryResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Fuel entries are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_financial_entries(self) -> Sequence[FinancialEntryResponse]:
        from advancore.repositories import FinancialEntryRepository
        from advancore.services.financial_entry_service import FinancialEntryService

        session = self._open_session()
        try:
            items = FinancialEntryService(
                FinancialEntryRepository(session)
            ).list_entries()
            return [FinancialEntryResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Financial entries are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_activities(self) -> Sequence[ActivityLogResponse]:
        from advancore.repositories import ActivityLogRepository
        from advancore.services.activity_service import ActivityLogService

        session = self._open_session()
        try:
            items = ActivityLogService(ActivityLogRepository(session)).list_activities()
            return [ActivityLogResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Activity records are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def list_recurring_services_by_customer(
        self, customer_id: int
    ) -> Sequence[RecurringServiceResponse]:
        from advancore.repositories import (
            CustomerRepository,
            RecurringServiceRepository,
            RouteRepository,
        )
        from advancore.services.recurring_service_service import RecurringServiceService

        session = self._open_session()
        try:
            items = RecurringServiceService(
                RecurringServiceRepository(session),
                CustomerRepository(session),
                RouteRepository(session),
            ).list_by_customer(customer_id)
            return [RecurringServiceResponse.model_validate(item) for item in items]
        except Exception as exc:
            raise ReadModelUnavailable(
                "Recurring services are temporarily unavailable."
            ) from exc
        finally:
            session.rollback()
            session.close()

    def fleet(
        self,
        registered_owner_id: int | None = None,
        vehicle_type: str | None = None,
        passenger_capacity: int | None = None,
    ) -> FleetResponse:
        from advancore.repositories import LegalEntityRepository, VehicleRepository
        from advancore.services.legal_entity_service import LegalEntityService
        from advancore.services.vehicle_service import (
            VehicleService,
            calculate_hire_purchase_projection,
        )

        session = self._open_session()
        try:
            companies = LegalEntityService(
                LegalEntityRepository(session)
            ).list_entities()
            vehicles = VehicleService(VehicleRepository(session)).list_vehicles(
                registered_owner_id,
                vehicle_type,
                passenger_capacity,
            )
            vehicle_responses = []
            for item in vehicles:
                projection = calculate_hire_purchase_projection(
                    item.loan_start_date,
                    item.loan_term_months,
                    item.monthly_instalment,
                )
                vehicle_responses.append(
                    VehicleResponse.model_validate(item).model_copy(
                        update={
                            "remaining_scheduled_payments": projection.remaining_scheduled_payments,
                            "projected_remaining_scheduled_amount": projection.projected_remaining_scheduled_amount,
                        }
                    )
                )
            return FleetResponse(
                companies=[LegalEntityResponse.model_validate(item) for item in companies],
                vehicles=vehicle_responses,
            )
        except Exception as exc:
            raise ReadModelUnavailable("Fleet records are temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def dispatch(self, service_date: date) -> DispatchBoardResponse:
        from advancore.repositories import (
            DriverRepository,
            RouteRepository,
            TripAssignmentRepository,
            TripRepository,
            VehicleRepository,
        )
        from advancore.services.dispatch_board_service import build_dispatch_board

        session = self._open_session()
        try:
            board = build_dispatch_board(
                service_date,
                trips=TripRepository(session).list(),
                assignments=TripAssignmentRepository(session).list(),
                routes=RouteRepository(session).list(),
                vehicles=VehicleRepository(session).list(),
                drivers=DriverRepository(session).list(),
            )
            return DispatchBoardResponse(
                service_date=board.service_date,
                trip_count=len(board.rows),
                conflict_count=board.conflict_count,
                rows=[
                    DispatchRowResponse(
                        trip_id=row.trip_id,
                        trip_reference=row.trip_reference,
                        trip_status=row.trip_status,
                        route_label=row.route_label,
                        dispatch_state=row.dispatch_state,
                        vehicle_label=row.vehicle_label,
                        driver_label=row.driver_label,
                        conflicts=list(row.conflicts),
                    )
                    for row in board.rows
                ],
                available_vehicles=[
                    DispatchResourceResponse(id=item.identifier, label=item.label)
                    for item in board.available_vehicles
                ],
                available_drivers=[
                    DispatchResourceResponse(id=item.identifier, label=item.label)
                    for item in board.available_drivers
                ],
            )
        except Exception as exc:
            raise ReadModelUnavailable("Dispatch records are temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def fuel_intelligence(self) -> FuelIntelligenceResponse:
        from advancore.repositories import FuelEntryRepository
        from advancore.services.fuel_intelligence_service import FuelIntelligenceService

        session = self._open_session()
        try:
            summary = FuelIntelligenceService(FuelEntryRepository(session)).get_summary()
            return FuelIntelligenceResponse(
                entry_count=summary.entry_count,
                total_litres=summary.total_litres,
                cost_entry_count=summary.cost_entry_count,
                total_cost=summary.total_cost,
                average_cost_per_litre=summary.average_cost_per_litre,
                odometer_reading_count=summary.odometer_reading_count,
                observed_distance_km=summary.observed_distance_km,
                observed_distance_interval_count=summary.observed_distance_interval_count,
                ignored_odometer_interval_count=summary.ignored_odometer_interval_count,
                daily_totals=[
                    FuelDailyTotalResponse(
                        recorded_on=item.recorded_on,
                        litres=item.litres,
                    )
                    for item in summary.daily_totals
                ],
            )
        except Exception as exc:
            raise ReadModelUnavailable("Fuel records are temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def fuel_market_benchmark(self) -> FuelMarketBenchmarkResponse:
        from advancore.repositories import FuelMarketRepository
        from advancore.services.fuel_market_service import FuelMarketService

        session = self._open_session()
        try:
            view = FuelMarketService(FuelMarketRepository(session)).market_view()
            snapshot = view.snapshot
            observations = [] if snapshot is None else [
                FuelPriceObservationResponse(
                    provider="Shell",
                    grade="FuelSave Diesel",
                    price_per_litre=snapshot.shell_price_per_litre,
                    source_name="Shell Singapore official price board",
                    source_url="https://www.shell.com.sg/fuels-oils-and-coolants/shell-fuels/shell-station-price-board.html",
                    source_updated_at=snapshot.shell_source_updated_at,
                ),
                FuelPriceObservationResponse(
                    provider="SPC",
                    grade="Diesel",
                    price_per_litre=snapshot.spc_price_per_litre,
                    source_name="SPC official pump price",
                    source_url="https://www.spc.com.sg/",
                    source_updated_at=snapshot.spc_source_updated_at,
                ),
            ]
            prices = [item.price_per_litre for item in observations]
            return FuelMarketBenchmarkResponse(
                retrieved_on=snapshot.observed_on if snapshot else None,
                currency="SGD",
                unit="litre",
                basis="Gross pump price before discounts",
                benchmark_grade="Diesel — Shell/SPC midpoint",
                low=min(prices) if prices else None,
                median=snapshot.benchmark_price_per_litre if snapshot else None,
                high=max(prices) if prices else None,
                market_observations=observations,
                official_confirmations=[],
                status=view.status,
                stale=view.stale,
                last_attempt_at=view.last_attempt_at,
                last_success_at=view.last_success_at,
                failure_summary=view.failure_summary,
                history=[
                    FuelMarketHistoryResponse(
                        observed_on=item.observed_on,
                        shell_price_per_litre=item.shell_price_per_litre,
                        spc_price_per_litre=item.spc_price_per_litre,
                        benchmark_price_per_litre=item.benchmark_price_per_litre,
                    )
                    for item in view.history
                ],
            )
        except Exception as exc:
            raise ReadModelUnavailable("The fuel-market benchmark is unavailable.") from exc
        finally:
            session.rollback()
            session.close()

    def recurring_service_fuel_adjustment(
        self, recurring_service_id: int
    ) -> FuelAdjustmentDraftResponse:
        from advancore.repositories import FuelMarketRepository, RecurringServiceRepository
        from advancore.services.fuel_market_service import FuelMarketService

        session = self._open_session()
        try:
            recurring = RecurringServiceRepository(session).get_by_id(recurring_service_id)
            if recurring is None:
                raise ValueError("Recurring service not found.")
            draft = FuelMarketService(
                FuelMarketRepository(session), RecurringServiceRepository(session)
            ).adjustment_draft(recurring_service_id)
            return FuelAdjustmentDraftResponse(
                recurring_service_id=recurring_service_id,
                calculation_status=draft.calculation_status,
                stale=draft.stale,
                benchmark_observed_on=draft.benchmark.observed_on if draft.benchmark else None,
                benchmark_price_per_litre=draft.benchmark.benchmark_price_per_litre if draft.benchmark else None,
                monthly_contract_amount=recurring.monthly_amount,
                currency_code=recurring.currency_code,
                price_variance_percent=draft.price_variance_percent,
                draft_adjustment_amount=draft.draft_adjustment_amount,
                adjusted_monthly_amount=draft.adjusted_monthly_amount,
                current_rule=(
                    RecurringServiceFuelRuleResponse.model_validate(draft.rule)
                    if draft.rule else None
                ),
                rule_history=[
                    RecurringServiceFuelRuleResponse.model_validate(item)
                    for item in draft.rules
                ],
            )
        except ValueError as exc:
            raise ReadModelUnavailable(str(exc)) from exc
        except Exception as exc:
            raise ReadModelUnavailable("Fuel adjustment is temporarily unavailable.") from exc
        finally:
            session.rollback()
            session.close()


class ControllerOwnerGoalPreviewer:
    """Pass Owner Goal text through the governed dry-run controller path."""

    def __init__(self, repo_root: Path):
        self._repo_root = repo_root.resolve()

    def preview(self, goal: str) -> OwnerGoalPreviewResponse:
        result = generate_goal_task(
            repo_root=self._repo_root,
            tasks_dir=self._repo_root / "tasks",
            goal=goal,
            planner=DryRunWorkerAdapter(),
            execute=False,
        )
        return OwnerGoalPreviewResponse(
            accepted=result.goal_accepted,
            normalized_goal=" ".join(goal.split()),
            status=result.status.value,
            candidate_task_id=result.task_id,
            planner_launched=False,
            task_written=result.task_written,
            execution_requested=False,
            publication_performed=not result.no_publication_performed,
            next_action=result.next_action,
            messages=result.messages,
        )
