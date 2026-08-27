from datetime import date, datetime, timezone

from advancore.api.schemas import (
    DispatchBoardResponse,
    DispatchResourceResponse,
    DispatchRowResponse,
    FleetResponse,
    FuelDailyTotalResponse,
    FuelIntelligenceResponse,
    FuelMarketBenchmarkResponse,
    FuelPriceObservationResponse,
    LegalEntityResponse,
    SystemStatusResponse,
    VehicleResponse,
)


NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


class FakeOperationsGateway:
    def __init__(self):
        self.fleet_filters = None
        self.dispatch_date = None

    def status(self):
        return SystemStatusResponse(
            state="ready",
            database_configured=True,
            database_reachable=True,
            controller_available=True,
        )

    def list_projects(self): return []
    def list_knowledge(self): return []

    def fleet(self, registered_owner_id=None, vehicle_type=None, passenger_capacity=None):
        self.fleet_filters = (registered_owner_id, vehicle_type, passenger_capacity)
        return FleetResponse(
            companies=[LegalEntityResponse(id=7, name="Advan Transit", status="active")],
            vehicles=[VehicleResponse(
                id=11,
                registration_number="PC5234D",
                make_model="Test bus",
                status="active",
                registered_owner_id=7,
                manufacture_year=2020,
                passenger_capacity=43,
                vehicle_type="Bus",
                propellant="Diesel",
                scheme=None,
                chassis_number=None,
                engine_number=None,
                original_registration_date=None,
                lifespan_expiry=None,
                coe_expiry=None,
                primary_colour=None,
                unladen_weight_kg=None,
                maximum_laden_weight_kg=None,
                parking_provider="P-Park",
                parking_location="Workshop",
                parking_monthly_cost="327.00",
                insurance_provider=None,
                insurance_annual_amount=None,
                road_tax_amount="850.00",
                road_tax_period_months=6,
            )],
        )

    def dispatch(self, service_date):
        self.dispatch_date = service_date
        return DispatchBoardResponse(
            service_date=service_date,
            trip_count=1,
            conflict_count=0,
            rows=[DispatchRowResponse(
                trip_id=3,
                trip_reference="TRIP-001",
                trip_status="planned",
                route_label="R1: Depot → School",
                dispatch_state="Unassigned",
                vehicle_label="Not assigned",
                driver_label="Not assigned",
                conflicts=[],
            )],
            available_vehicles=[DispatchResourceResponse(id=11, label="PC5234D")],
            available_drivers=[DispatchResourceResponse(id=4, label="Driver A")],
        )

    def fuel_intelligence(self):
        return FuelIntelligenceResponse(
            entry_count=2,
            total_litres="100.50",
            cost_entry_count=1,
            total_cost="395.00",
            average_cost_per_litre="3.95",
            odometer_reading_count=0,
            observed_distance_km=None,
            observed_distance_interval_count=0,
            ignored_odometer_interval_count=0,
            daily_totals=[FuelDailyTotalResponse(recorded_on=date(2026, 8, 28), litres="100.50")],
        )

    def fuel_market_benchmark(self):
        source = FuelPriceObservationResponse(
            provider="Shell",
            grade="Diesel",
            price_per_litre="3.95",
            source_name="Motorist Singapore",
            source_url="https://www.motorist.sg/petrol-prices",
            source_updated_at="retrieved 2026-08-28",
        )
        return FuelMarketBenchmarkResponse(
            retrieved_on=date(2026, 8, 28),
            currency="SGD",
            unit="litre",
            basis="gross pump price before discounts",
            benchmark_grade="Diesel",
            low="3.89",
            median="3.95",
            high="4.05",
            market_observations=[source],
            official_confirmations=[source],
        )
