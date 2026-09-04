"""Primary-console contracts for TASK-175 through TASK-179."""

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from advancore.api.app import create_app
from advancore.api.schemas import (
    ActivityLogResponse,
    FinancialEntryResponse,
    FuelEntryResponse,
    TripAssignmentResponse,
    TripResponse,
)


NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:8000"


def _trip(**values):
    return TripResponse(
        id=values.get("id", 10),
        trip_reference=values.get("trip_reference", "TRIP-175"),
        route_id=values.get("route_id", 3),
        service_date=values.get("service_date", date(2026, 9, 2)),
        status=values.get("status", "planned"),
        created_at=NOW,
        updated_at=NOW,
    )


def _assignment(**values):
    return TripAssignmentResponse(
        id=values.get("id", 11),
        trip_id=values.get("trip_id", 10),
        vehicle_id=values.get("vehicle_id", 4),
        driver_id=values.get("driver_id", 5),
        status=values.get("status", "assigned"),
        created_at=NOW,
        updated_at=NOW,
    )


def _fuel_entry():
    return FuelEntryResponse(
        id=12,
        vehicle_id=4,
        recorded_on=date(2026, 9, 2),
        litres="45.25",
        total_cost="120.00",
        odometer_km="12345.6",
        created_at=NOW,
        updated_at=NOW,
    )


def _financial_entry():
    return FinancialEntryResponse(
        id=13,
        entry_date=date(2026, 9, 2),
        entry_type="expense",
        amount="120.00",
        currency_code="SGD",
        description="Test fuel fact",
        trip_id=10,
        customer_id=6,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeDailyEditingGateway:
    def __init__(self):
        self.calls = []

    def create_trip(self, reference, route_id, service_date):
        self.calls.append(("create_trip", reference, route_id, service_date))
        return _trip(trip_reference=reference, route_id=route_id, service_date=service_date)

    def set_trip_status(self, identifier, value):
        self.calls.append(("set_trip_status", identifier, value))
        return _trip(id=identifier, status=value)

    def create_trip_assignment(self, trip_id, vehicle_id, driver_id):
        self.calls.append(("create_trip_assignment", trip_id, vehicle_id, driver_id))
        return _assignment(trip_id=trip_id, vehicle_id=vehicle_id, driver_id=driver_id)

    def release_trip_assignment(self, identifier):
        self.calls.append(("release_trip_assignment", identifier))
        return _assignment(id=identifier, status="released")

    def create_fuel_entry(self, vehicle_id, recorded_on, litres, total_cost, odometer_km):
        self.calls.append(("create_fuel_entry", vehicle_id, recorded_on, litres, total_cost, odometer_km))
        return _fuel_entry()

    def create_financial_entry(self, entry_date, entry_type, amount, currency_code, description, trip_id, customer_id):
        self.calls.append(("create_financial_entry", entry_date, entry_type, amount, currency_code, description, trip_id, customer_id))
        return _financial_entry()


class FakeDailyReadGateway:
    def list_trips(self):
        return [_trip()]

    def list_trip_assignments(self):
        return [_assignment()]

    def list_fuel_entries(self):
        return [_fuel_entry()]

    def list_financial_entries(self):
        return [_financial_entry()]

    def list_activities(self):
        return [ActivityLogResponse(id=14, action="trip_reviewed", entity_type="trip", entity_id="10", details=None, created_at=NOW, updated_at=NOW)]


def _client(tmp_path, editing_gateway):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return TestClient(
        create_app(
            repo_root=tmp_path,
            frontend_dir=frontend,
            read_gateway=FakeDailyReadGateway(),
            edit_gateway=editing_gateway,
            orchestration_service=SimpleNamespace(shutdown=lambda: None),
        ),
        client=("127.0.0.1", 50000),
    )


def _headers(client):
    token = client.get("/api/session").json()["action_token"]
    return {"Origin": ORIGIN, "X-AdvanCore-Action-Token": token}


def test_daily_operation_reads_are_local_service_projections(tmp_path):
    with _client(tmp_path, FakeDailyEditingGateway()) as client:
        responses = [
            client.get("/api/trips"),
            client.get("/api/trip-assignments"),
            client.get("/api/fuel-entries"),
            client.get("/api/financial-entries"),
            client.get("/api/activity-log"),
        ]

    assert [response.status_code for response in responses] == [200] * 5
    assert responses[0].json()[0]["trip_reference"] == "TRIP-175"
    assert responses[4].json()[0]["action"] == "trip_reviewed"


def test_daily_operation_writes_require_confirmation_and_delegate_exact_fields(tmp_path):
    gateway = FakeDailyEditingGateway()
    with _client(tmp_path, gateway) as client:
        headers = _headers(client)
        responses = [
            client.post("/api/trips", json={"trip_reference": "TRIP-176", "route_id": 3, "service_date": "2026-09-03", "confirmed": True}, headers=headers),
            client.post("/api/trips/10/status", json={"status": "completed", "confirmed": True}, headers=headers),
            client.post("/api/trip-assignments", json={"trip_id": 10, "vehicle_id": 4, "driver_id": 5, "confirmed": True}, headers=headers),
            client.post("/api/trip-assignments/11/release", json={"confirmed": True}, headers=headers),
            client.post("/api/fuel-entries", json={"vehicle_id": 4, "recorded_on": "2026-09-02", "litres": "45.25", "total_cost": "120.00", "odometer_km": "12345.6", "confirmed": True}, headers=headers),
            client.post("/api/financial-entries", json={"entry_date": "2026-09-02", "entry_type": "expense", "amount": "120.00", "currency_code": "SGD", "description": "Test fuel fact", "trip_id": 10, "customer_id": 6, "confirmed": True}, headers=headers),
        ]
        rejected = client.post("/api/trips", json={"trip_reference": "NOPE", "route_id": 3, "service_date": "2026-09-03", "confirmed": "true"}, headers=headers)

    assert [response.status_code for response in responses] == [201, 200, 201, 200, 201, 201]
    assert rejected.status_code == 422
    assert [call[0] for call in gateway.calls] == [
        "create_trip", "set_trip_status", "create_trip_assignment",
        "release_trip_assignment", "create_fuel_entry", "create_financial_entry",
    ]


def test_activity_log_has_no_browser_mutation_route(tmp_path):
    gateway = FakeDailyEditingGateway()
    with _client(tmp_path, gateway) as client:
        response = client.post("/api/activity-log", json={"confirmed": True}, headers=_headers(client))

    assert response.status_code == 405
    assert gateway.calls == []


def test_daily_operations_frontend_uses_existing_fields_and_review_actions():
    source = (Path(__file__).parents[1] / "frontend" / "editing.js").read_text(encoding="utf-8")
    html = (Path(__file__).parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")

    for endpoint in ("/api/trips", "/api/trip-assignments", "/api/fuel-entries", "/api/financial-entries", "/api/activity-log"):
        assert endpoint in source
    for tab in ("dashboard", "customers", "routes", "drivers", "fleet", "subcontractors", "maintenance", "finance"):
        assert f'data-manager-tab="{tab}"' in html
    assert "Recurring customer schedules are not inferred" in source
    assert 'url: "/api/activity-log"' not in source
