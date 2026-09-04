"""Bounded request and response contracts for the local AdvanCore API."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from advancore.agent_runner.goal_task import MAX_GOAL_LENGTH


class SystemStatusResponse(BaseModel):
    service: str = "AdvanCore local API"
    primary_surface: Literal["fastapi_console"] = "fastapi_console"
    streamlit_role: Literal["temporary_admin_editing"] = "temporary_admin_editing"
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
    approved_at: datetime | None = None
    approved_by: str | None = None
    replaces_knowledge_item_id: int | None = None


class LegalEntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str


class DriverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    employee_reference: str | None
    status: str


class DriverEmploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    driver_id: int
    effective_month: date
    worker_category: Literal["local_pr", "foreign_levy"]
    basic_salary: Decimal
    employer_cpf_amount: Decimal | None
    monthly_levy_amount: Decimal | None
    monthly_allowance: Decimal | None
    employment_status: Literal["active", "inactive"]
    created_at: datetime
    updated_at: datetime


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    customer_reference: str | None
    status: str


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_code: str
    origin: str
    destination: str
    status: str


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_reference: str
    route_id: int
    service_date: date
    status: str
    created_at: datetime
    updated_at: datetime


class TripAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    vehicle_id: int
    driver_id: int
    status: str
    created_at: datetime
    updated_at: datetime


class FuelEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    recorded_on: date
    litres: Decimal
    total_cost: Decimal | None
    odometer_km: Decimal | None
    created_at: datetime
    updated_at: datetime


class FinancialEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_date: date
    entry_type: str
    amount: Decimal
    currency_code: str
    description: str | None
    trip_id: int | None
    customer_id: int | None
    vehicle_id: int | None = None
    accounting_month: date | None = None
    expected_payment_date: date | None = None
    payment_status: str = "unpaid"
    payment_date: date | None = None
    category: str | None = None
    created_at: datetime
    updated_at: datetime


class RecurringServiceDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: int


class RecurringServiceStopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stop_order: int
    location_name: str
    scheduled_time: time


class RecurringServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    route_id: int
    service_reference: str
    vehicle_requirement: str | None
    monthly_amount: Decimal
    currency_code: str
    effective_start_date: date
    effective_end_date: date | None
    status: str
    replaces_recurring_service_id: int | None
    days: list[RecurringServiceDayResponse]
    stops: list[RecurringServiceStopResponse]
    created_at: datetime
    updated_at: datetime


class ActivityLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    entity_type: str | None
    entity_id: str | None
    details: str | None
    created_at: datetime
    updated_at: datetime


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
    retrieved_on: date | None
    currency: str
    unit: str
    basis: str
    benchmark_grade: str
    low: Decimal | None
    median: Decimal | None
    high: Decimal | None
    market_observations: list[FuelPriceObservationResponse]
    official_confirmations: list[FuelPriceObservationResponse]
    status: Literal["current", "stale", "unavailable"] = "current"
    stale: bool = False
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    failure_summary: str | None = None
    history: list["FuelMarketHistoryResponse"] = Field(default_factory=list)


class FuelMarketHistoryResponse(BaseModel):
    observed_on: date
    shell_price_per_litre: Decimal
    spc_price_per_litre: Decimal
    benchmark_price_per_litre: Decimal


class RecurringServiceFuelRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recurring_service_id: int
    effective_from: date
    effective_to: date | None
    baseline_price_per_litre: Decimal
    fuel_cost_share_percent: Decimal
    tolerance_percent: Decimal
    created_at: datetime
    updated_at: datetime


class FuelAdjustmentDraftResponse(BaseModel):
    recurring_service_id: int
    calculation_status: str
    stale: bool
    benchmark_observed_on: date | None
    benchmark_price_per_litre: Decimal | None
    monthly_contract_amount: Decimal
    currency_code: str
    price_variance_percent: Decimal | None
    draft_adjustment_amount: Decimal | None
    adjusted_monthly_amount: Decimal | None
    current_rule: RecurringServiceFuelRuleResponse | None
    rule_history: list[RecurringServiceFuelRuleResponse]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfirmedRequest(StrictRequest):
    confirmed: StrictBool


class ProjectCreateRequest(ConfirmedRequest):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)


class ProjectEditRequest(ProjectCreateRequest):
    pass


class KnowledgeDraftRequest(ConfirmedRequest):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100_000)


class KnowledgeApproveRequest(ConfirmedRequest):
    expected_updated_at: datetime
    expected_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("expected_updated_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Expected update timestamp must include a timezone.")
        return value


class LegalEntityCreateRequest(ConfirmedRequest):
    name: str = Field(min_length=1, max_length=160)


class VehicleCreateRequest(ConfirmedRequest):
    registration_number: str = Field(min_length=1, max_length=32)
    make_model: str | None = Field(default=None, max_length=120)


class VehicleStatusRequest(ConfirmedRequest):
    status: Literal["active", "out_of_service", "retired"]


class VehicleDetailsRequest(ConfirmedRequest):
    registered_owner_id: StrictInt | None = None
    manufacture_year: StrictInt | None = None
    passenger_capacity: StrictInt | None = None
    vehicle_type: Literal["Bus", "lorry", "car"] | None = None
    propellant: str | None = Field(default=None, max_length=40)
    scheme: str | None = Field(default=None, max_length=80)
    chassis_number: str | None = Field(default=None, max_length=80)
    engine_number: str | None = Field(default=None, max_length=80)
    original_registration_date: date | None = None
    lifespan_expiry: date | None = None
    coe_expiry: date | None = None
    primary_colour: str | None = Field(default=None, max_length=40)
    unladen_weight_kg: Decimal | None = None
    maximum_laden_weight_kg: Decimal | None = None
    parking_provider: str | None = Field(default=None, max_length=120)
    parking_location: str | None = Field(default=None, max_length=200)
    parking_monthly_cost: Decimal | None = None
    insurance_provider: str | None = Field(default=None, max_length=120)
    insurance_annual_amount: Decimal | None = None
    road_tax_amount: Decimal | None = None
    road_tax_period_months: Literal[6, 12] | None = None
    finance_company: str | None = Field(default=None, max_length=120)
    original_loan_amount: Decimal | None = None
    monthly_instalment: Decimal | None = None
    loan_start_date: date | None = None
    loan_term_months: StrictInt | None = None


class DriverCreateRequest(ConfirmedRequest):
    name: str = Field(min_length=1, max_length=120)
    employee_reference: str | None = Field(default=None, max_length=40)


class DriverStatusRequest(ConfirmedRequest):
    status: Literal["active", "unavailable", "retired"]


class DriverEmploymentCreateRequest(ConfirmedRequest):
    driver_id: StrictInt
    effective_month: date
    worker_category: Literal["local_pr", "foreign_levy"]
    basic_salary: Decimal = Field(ge=0, decimal_places=2)
    employer_cpf_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    monthly_levy_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    monthly_allowance: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    employment_status: Literal["active", "inactive"]


class CustomerCreateRequest(ConfirmedRequest):
    name: str = Field(min_length=1, max_length=160)
    customer_reference: str | None = Field(default=None, max_length=40)


class CustomerStatusRequest(ConfirmedRequest):
    status: Literal["active", "inactive"]


class RouteCreateRequest(ConfirmedRequest):
    route_code: str = Field(min_length=1, max_length=40)
    origin: str = Field(min_length=1, max_length=160)
    destination: str = Field(min_length=1, max_length=160)


class RouteStatusRequest(ConfirmedRequest):
    status: Literal["active", "inactive"]


class TripCreateRequest(ConfirmedRequest):
    trip_reference: str = Field(min_length=1, max_length=40)
    route_id: StrictInt
    service_date: date


class TripStatusRequest(ConfirmedRequest):
    status: Literal["planned", "completed", "cancelled"]


class TripAssignmentCreateRequest(ConfirmedRequest):
    trip_id: StrictInt
    vehicle_id: StrictInt
    driver_id: StrictInt


class FuelEntryCreateRequest(ConfirmedRequest):
    vehicle_id: StrictInt
    recorded_on: date
    litres: Decimal
    total_cost: Decimal | None = None
    odometer_km: Decimal | None = None


class FinancialEntryCreateRequest(ConfirmedRequest):
    entry_date: date
    entry_type: Literal["income", "expense"]
    amount: Decimal
    currency_code: str = Field(min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=200)
    trip_id: StrictInt | None = None
    customer_id: StrictInt | None = None
    vehicle_id: StrictInt | None = None
    accounting_month: date | None = None
    expected_payment_date: date | None = None
    payment_status: Literal["unpaid", "paid"] = "unpaid"
    payment_date: date | None = None
    category: str | None = Field(default=None, max_length=40)


class RecurringServiceStopRequest(StrictRequest):
    stop_order: StrictInt
    location_name: str = Field(min_length=1, max_length=160)
    scheduled_time: time


class RecurringServiceCreateRequest(ConfirmedRequest):
    customer_id: StrictInt
    route_id: StrictInt
    service_reference: str = Field(min_length=1, max_length=40)
    vehicle_requirement: str | None = Field(default=None, max_length=200)
    monthly_amount: Decimal = Field(ge=0, decimal_places=2)
    currency_code: str = Field(min_length=3, max_length=3)
    effective_start_date: date
    effective_end_date: date | None = None
    weekdays: list[StrictInt] = Field(min_length=1)
    stops: list[RecurringServiceStopRequest] = Field(min_length=1)

    @field_validator("weekdays")
    @classmethod
    def _weekdays_in_range(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Weekday must be between 0 (Monday) and 6 (Sunday).")
        return value

    @field_validator("stops")
    @classmethod
    def _stop_orders_unique(cls, value: list[RecurringServiceStopRequest]) -> list[RecurringServiceStopRequest]:
        orders = [stop.stop_order for stop in value]
        if len(set(orders)) != len(orders):
            raise ValueError("Stop order must be unique within a service.")
        return value


class RecurringServiceStatusRequest(ConfirmedRequest):
    status: Literal["active", "paused", "archived"]


class RecurringServiceFuelRuleCreateRequest(ConfirmedRequest):
    effective_from: date
    baseline_price_per_litre: Decimal = Field(gt=0, decimal_places=4)
    fuel_cost_share_percent: Decimal = Field(ge=0, le=100, decimal_places=4)
    tolerance_percent: Decimal = Field(ge=0, le=100, decimal_places=4)


class RecurringServiceReplaceRequest(ConfirmedRequest):
    route_id: StrictInt
    service_reference: str = Field(min_length=1, max_length=40)
    vehicle_requirement: str | None = Field(default=None, max_length=200)
    monthly_amount: Decimal = Field(ge=0, decimal_places=2)
    currency_code: str = Field(min_length=3, max_length=3)
    effective_start_date: date
    effective_end_date: date | None = None
    weekdays: list[StrictInt] = Field(min_length=1)
    stops: list[RecurringServiceStopRequest] = Field(min_length=1)

    @field_validator("weekdays")
    @classmethod
    def _weekdays_in_range(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("Weekdays must be unique values from 0 (Monday) to 6 (Sunday).")
        return value

    @field_validator("stops")
    @classmethod
    def _stop_orders_unique(
        cls, value: list[RecurringServiceStopRequest]
    ) -> list[RecurringServiceStopRequest]:
        orders = [stop.stop_order for stop in value]
        if len(set(orders)) != len(orders):
            raise ValueError("Stop order must be unique within a service.")
        return value


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
