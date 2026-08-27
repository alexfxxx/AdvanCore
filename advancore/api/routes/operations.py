"""Read-only operational projections for the decoupled local console."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request, status

from advancore.api.dependencies import ReadModelUnavailable
from advancore.api.schemas import (
    DispatchBoardResponse,
    FleetResponse,
    FuelIntelligenceResponse,
    FuelMarketBenchmarkResponse,
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
