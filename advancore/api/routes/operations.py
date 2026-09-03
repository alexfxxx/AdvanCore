"""Read-only operational projections for the decoupled local console."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status

from advancore.api.dependencies import ReadModelUnavailable
from advancore.api.routes.orchestration import require_loopback_peer
from advancore.api.schemas import (
    ActivityLogResponse,
    CustomerResponse,
    DriverResponse,
    DriverEmploymentResponse,
    DispatchBoardResponse,
    FinancialEntryResponse,
    FleetResponse,
    FuelEntryResponse,
    FuelIntelligenceResponse,
    FuelMarketBenchmarkResponse,
    FuelAdjustmentDraftResponse,
    RecurringServiceResponse,
    RouteResponse,
    TripAssignmentResponse,
    TripResponse,
)


router = APIRouter(prefix="/api", tags=["operations"])


def _unavailable(exc: ReadModelUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


@router.get("/fleet", response_model=FleetResponse)
def fleet(
    request: Request,
    registered_owner_id: int | None = Query(default=None, gt=0),
    vehicle_type: str | None = Query(default=None, max_length=16),
    passenger_capacity: int | None = Query(default=None, gt=0),
) -> FleetResponse:
    try:
        return request.app.state.read_gateway.fleet(
            registered_owner_id,
            vehicle_type,
            passenger_capacity,
        )
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/drivers", response_model=list[DriverResponse])
def drivers(request: Request) -> list[DriverResponse]:
    try:
        return list(request.app.state.read_gateway.list_drivers())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/drivers/{driver_id}/employment-records",
    response_model=list[DriverEmploymentResponse],
    dependencies=[Depends(require_loopback_peer)],
)
def driver_employment_records(
    request: Request, response: Response, driver_id: int = Path(gt=0)
) -> list[DriverEmploymentResponse]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return list(
            request.app.state.read_gateway.list_driver_employment_records(driver_id)
        )
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/customers", response_model=list[CustomerResponse])
def customers(request: Request) -> list[CustomerResponse]:
    try:
        return list(request.app.state.read_gateway.list_customers())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/routes", response_model=list[RouteResponse])
def routes(request: Request) -> list[RouteResponse]:
    try:
        return list(request.app.state.read_gateway.list_routes())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/trips", response_model=list[TripResponse])
def trips(request: Request) -> list[TripResponse]:
    try:
        return list(request.app.state.read_gateway.list_trips())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/trip-assignments", response_model=list[TripAssignmentResponse])
def trip_assignments(request: Request) -> list[TripAssignmentResponse]:
    try:
        return list(request.app.state.read_gateway.list_trip_assignments())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/fuel-entries", response_model=list[FuelEntryResponse])
def fuel_entries(request: Request) -> list[FuelEntryResponse]:
    try:
        return list(request.app.state.read_gateway.list_fuel_entries())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/financial-entries", response_model=list[FinancialEntryResponse])
def financial_entries(request: Request) -> list[FinancialEntryResponse]:
    try:
        return list(request.app.state.read_gateway.list_financial_entries())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/activity-log", response_model=list[ActivityLogResponse])
def activity_log(request: Request) -> list[ActivityLogResponse]:
    try:
        return list(request.app.state.read_gateway.list_activities())
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/customers/{customer_id}/recurring-services",
    response_model=list[RecurringServiceResponse],
    dependencies=[Depends(require_loopback_peer)],
)
def customer_recurring_services(
    request: Request, response: Response, customer_id: int = Path(gt=0)
) -> list[RecurringServiceResponse]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return list(
            request.app.state.read_gateway.list_recurring_services_by_customer(
                customer_id
            )
        )
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/dispatch", response_model=DispatchBoardResponse)
def dispatch(request: Request, service_date: date) -> DispatchBoardResponse:
    try:
        return request.app.state.read_gateway.dispatch(service_date)
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/fuel/intelligence", response_model=FuelIntelligenceResponse)
def fuel_intelligence(request: Request) -> FuelIntelligenceResponse:
    try:
        return request.app.state.read_gateway.fuel_intelligence()
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get("/fuel/market-benchmark", response_model=FuelMarketBenchmarkResponse)
def fuel_market_benchmark(request: Request) -> FuelMarketBenchmarkResponse:
    try:
        return request.app.state.read_gateway.fuel_market_benchmark()
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/recurring-services/{recurring_service_id}/fuel-adjustment",
    response_model=FuelAdjustmentDraftResponse,
    dependencies=[Depends(require_loopback_peer)],
)
def recurring_service_fuel_adjustment(
    request: Request,
    response: Response,
    recurring_service_id: int = Path(gt=0),
) -> FuelAdjustmentDraftResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return request.app.state.read_gateway.recurring_service_fuel_adjustment(
            recurring_service_id
        )
    except ReadModelUnavailable as exc:
        raise _unavailable(exc) from exc
