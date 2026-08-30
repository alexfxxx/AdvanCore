"""Bounded request and response contracts for the local AdvanCore API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from advancore.agent_runner.goal_task import MAX_GOAL_LENGTH


class SystemStatusResponse(BaseModel):
    service: str = "AdvanCore local API"
    state: str
    database_configured: bool
    database_reachable: bool
    controller_available: bool
    governance_mode: str = "fail_closed"
    voice_state: str = "disabled"


class ModuleResponse(BaseModel):
    module_id: str
    label: str
    area: str
    maturity: str
    presentation_surfaces: list[str]
    api_prefixes: list[str]


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    title: str
    content: str
    status: str
    created_at: datetime
    updated_at: datetime


class LegalEntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    registration_number: str
    make_model: str | None
    status: str
    registered_owner_id: int | None
    manufacture_year: int | None
    passenger_capacity: int | None
    vehicle_type: str | None
    propellant: str | None
    scheme: str | None
    chassis_number: str | None
    engine_number: str | None
    original_registration_date: date | None
    lifespan_expiry: date | None
    coe_expiry: date | None
    primary_colour: str | None
    unladen_weight_kg: Decimal | None
    maximum_laden_weight_kg: Decimal | None
    parking_provider: str | None
    parking_location: str | None
    parking_monthly_cost: Decimal | None
    insurance_provider: str | None
    insurance_annual_amount: Decimal | None
    road_tax_amount: Decimal | None
    road_tax_period_months: int | None
    finance_company: str | None
    original_loan_amount: Decimal | None
    monthly_instalment: Decimal | None
    loan_start_date: date | None
    loan_term_months: int | None
    remaining_scheduled_payments: int | None = None
    projected_remaining_scheduled_amount: Decimal | None = None


class FleetResponse(BaseModel):
    companies: list[LegalEntityResponse]
    vehicles: list[VehicleResponse]


class DispatchResourceResponse(BaseModel):
    id: int
    label: str


class DispatchRowResponse(BaseModel):
    trip_id: int
    trip_reference: str
    trip_status: str
    route_label: str
    dispatch_state: str
    vehicle_label: str
    driver_label: str
    conflicts: list[str]


class DispatchBoardResponse(BaseModel):
    service_date: date
    trip_count: int
    conflict_count: int
    rows: list[DispatchRowResponse]
    available_vehicles: list[DispatchResourceResponse]
    available_drivers: list[DispatchResourceResponse]


class FuelDailyTotalResponse(BaseModel):
    recorded_on: date
    litres: Decimal


class FuelIntelligenceResponse(BaseModel):
    entry_count: int
    total_litres: Decimal
    cost_entry_count: int
    total_cost: Decimal | None
    average_cost_per_litre: Decimal | None
    odometer_reading_count: int
    observed_distance_km: Decimal | None
    observed_distance_interval_count: int
    ignored_odometer_interval_count: int
    daily_totals: list[FuelDailyTotalResponse]


class FuelPriceObservationResponse(BaseModel):
    provider: str
    grade: str
    price_per_litre: Decimal
    source_name: str
    source_url: str
    source_updated_at: str


class FuelMarketBenchmarkResponse(BaseModel):
    retrieved_on: date
    currency: str
    unit: str
    basis: str
    benchmark_grade: str
    low: Decimal
    median: Decimal
    high: Decimal
    market_observations: list[FuelPriceObservationResponse]
    official_confirmations: list[FuelPriceObservationResponse]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnerGoalRequest(StrictRequest):
    goal: str = Field(min_length=1, max_length=MAX_GOAL_LENGTH)


class OwnerGoalPreviewResponse(BaseModel):
    accepted: bool
    normalized_goal: str
    status: str
    candidate_task_id: str | None
    planner_launched: bool = False
    task_written: bool = False
    execution_requested: bool = False
    publication_performed: bool = False
    next_action: str
    messages: list[str]


class ApiErrorResponse(BaseModel):
    detail: str


class LocalActionSessionResponse(BaseModel):
    action_token: str
    lifetime: str = "process"


class OrchestrationLaunchRequest(StrictRequest):
    goal: str = Field(min_length=1, max_length=MAX_GOAL_LENGTH)
    confirmed: StrictBool


class OrchestrationResumeRequest(StrictRequest):
    confirmed: StrictBool


class OrchestrationActionRequest(StrictRequest):
    action: Literal[
        "APPROVE_TASK",
        "BLOCK_TASK",
        "APPROVE_IMPLEMENTATION",
        "REWORK_IMPLEMENTATION",
        "BLOCK_IMPLEMENTATION",
    ]
    confirmed: StrictBool
    owner_note: str | None = Field(default=None, max_length=400)


class OrchestrationPreviewResponse(BaseModel):
    run_id: str
    task_id: str | None
    phase: str
    status: str
    owner_decision_required: bool
    next_action: str
    planner_launched: bool = False
    worker_launched: bool = False
    mutations_performed: list[str]


class OrchestrationJobResponse(BaseModel):
    job_id: str
    operation: str
    state: str
    terminal: bool
    run_id: str | None
    task_id: str | None
    phase: str | None
    status: str | None
    owner_decision_required: bool
    message: str
    next_action: str | None
    events_url: str
    updated_at: datetime


class OrchestrationRunResponse(BaseModel):
    run_id: str
    task_id: str | None
    phase: str
    status: str
    branch: str | None
    completed_phases: list[str]
    owner_decision_count: int
    push_verified: bool
    updated_at: datetime
    messages: list[str]
