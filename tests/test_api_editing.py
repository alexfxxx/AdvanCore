"""Contracts for the loopback-only primary-console editing boundary."""

import asyncio
from datetime import date, datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

from fastapi.testclient import TestClient

from advancore.api.app import BoundedLocalEditBodyMiddleware, create_app
from advancore.api.editing_gateway import (
    EditingConflictError,
    EditingNotFoundError,
    EditingValidationError,
)
from advancore.api.schemas import (
    CustomerResponse,
    DriverResponse,
    KnowledgeResponse,
    LegalEntityResponse,
    ProjectResponse,
    RouteResponse,
    VehicleResponse,
)


NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:8000"


def _project(**values) -> ProjectResponse:
    return ProjectResponse(
        id=values.get("id", 1),
        name=values.get("name", "Operations"),
        description=values.get("description"),
        status=values.get("status", "active"),
        created_at=NOW,
        updated_at=NOW,
    )


def _knowledge(**values) -> KnowledgeResponse:
    return KnowledgeResponse(
        id=values.get("id", 2),
        project_id=None,
        title=values.get("title", "Operating note"),
        content=values.get("content", "Saved content"),
        status=values.get("status", "draft"),
        created_at=NOW,
        updated_at=NOW,
    )


def _vehicle(**values) -> VehicleResponse:
    return VehicleResponse(
        id=values.get("id", 3),
        registration_number=values.get("registration_number", "PC5234D"),
        make_model=values.get("make_model"),
        status=values.get("status", "active"),
        registered_owner_id=None,
        manufacture_year=None,
        passenger_capacity=None,
        vehicle_type=None,
        propellant=None,
        scheme=None,
        chassis_number=None,
        engine_number=None,
        original_registration_date=None,
        lifespan_expiry=None,
        coe_expiry=None,
        primary_colour=None,
        unladen_weight_kg=None,
        maximum_laden_weight_kg=None,
        parking_provider=None,
        parking_location=None,
        parking_monthly_cost=None,
        insurance_provider=None,
        insurance_annual_amount=None,
        road_tax_amount=None,
        road_tax_period_months=None,
        finance_company=None,
        original_loan_amount=None,
        monthly_instalment=None,
        loan_start_date=None,
        loan_term_months=None,
    )


class FakeEditingGateway:
    def __init__(self):
        self.calls = []
        self.failure = None

    def _return(self, call, response):
        self.calls.append(call)
        if self.failure is not None:
            raise self.failure
        return response

    def create_project(self, name, description):
        return self._return(("create_project", name, description), _project(name=name))

    def edit_project(self, identifier, name, description):
        return self._return(("edit_project", identifier, name, description), _project(name=name))

    def archive_project(self, identifier):
        return self._return(("archive_project", identifier), _project(status="archived"))

    def create_knowledge(self, title, content):
        return self._return(("create_knowledge", title, content), _knowledge(title=title, content=content))

    def edit_knowledge(self, identifier, title, content):
        return self._return(("edit_knowledge", identifier, title, content), _knowledge(title=title, content=content))

    def approve_knowledge(self, identifier, expected_updated_at, expected_digest):
        return self._return(
            ("approve_knowledge", identifier, expected_updated_at, expected_digest),
            _knowledge(status="approved"),
        )

    def archive_knowledge(self, identifier):
        return self._return(("archive_knowledge", identifier), _knowledge(status="archived"))

    def replace_knowledge(self, identifier):
        return self._return(("replace_knowledge", identifier), _knowledge(id=4))

    def create_legal_entity(self, name):
        return self._return(("create_legal_entity", name), LegalEntityResponse(id=5, name=name, status="active"))

    def create_vehicle(self, registration_number, make_model):
        return self._return(("create_vehicle", registration_number, make_model), _vehicle(registration_number=registration_number, make_model=make_model))

    def set_vehicle_status(self, identifier, value):
        return self._return(("set_vehicle_status", identifier, value), _vehicle(status=value))

    def update_vehicle_details(self, identifier, payload):
        return self._return(("update_vehicle_details", identifier, payload.model_dump()), _vehicle())

    def create_driver(self, name, reference):
        return self._return(("create_driver", name, reference), DriverResponse(id=6, name=name, employee_reference=reference, status="active"))

    def set_driver_status(self, identifier, value):
        return self._return(("set_driver_status", identifier, value), DriverResponse(id=identifier, name="Driver", employee_reference=None, status=value))

    def create_customer(self, name, reference):
        return self._return(("create_customer", name, reference), CustomerResponse(id=7, name=name, customer_reference=reference, status="active"))

    def set_customer_status(self, identifier, value):
        return self._return(("set_customer_status", identifier, value), CustomerResponse(id=identifier, name="Customer", customer_reference=None, status=value))

    def create_route(self, code, origin, destination):
        return self._return(("create_route", code, origin, destination), RouteResponse(id=8, route_code=code, origin=origin, destination=destination, status="active"))

    def set_route_status(self, identifier, value):
        return self._return(("set_route_status", identifier, value), RouteResponse(id=identifier, route_code="R1", origin="A", destination="B", status=value))


class FakeReadGateway:
    def list_drivers(self):
        return [DriverResponse(id=1, name="Driver A", employee_reference="D1", status="active")]

    def list_customers(self):
        return [CustomerResponse(id=2, name="School A", customer_reference="C1", status="active")]

    def list_routes(self):
        return [RouteResponse(id=3, route_code="R1", origin="Depot", destination="School", status="active")]


def _client(tmp_path, gateway=None, read_gateway=None, *, peer="127.0.0.1"):
    frontend = tmp_path / "frontend"
    frontend.mkdir(exist_ok=True)
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return TestClient(
        create_app(
            repo_root=tmp_path,
            frontend_dir=frontend,
            read_gateway=read_gateway or SimpleNamespace(),
            edit_gateway=gateway or FakeEditingGateway(),
            orchestration_service=SimpleNamespace(shutdown=lambda: None),
        ),
        client=(peer, 50000),
    )


def _headers(client):
    token = client.get("/api/session").json()["action_token"]
    return {"Origin": ORIGIN, "X-AdvanCore-Action-Token": token}


def test_every_edit_requires_loopback_origin_token_and_strict_confirmation(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, gateway) as client:
        token = client.get("/api/session").json()["action_token"]
        missing_origin = client.post(
            "/api/projects",
            json={"name": "Test", "confirmed": True},
            headers={"X-AdvanCore-Action-Token": token},
        )
        wrong_token = client.post(
            "/api/projects",
            json={"name": "Test", "confirmed": True},
            headers={"Origin": ORIGIN, "X-AdvanCore-Action-Token": "wrong"},
        )
        unconfirmed = client.post(
            "/api/projects",
            json={"name": "Test", "confirmed": False},
            headers={"Origin": ORIGIN, "X-AdvanCore-Action-Token": token},
        )
        coerced = client.post(
            "/api/projects",
            json={"name": "Test", "confirmed": "true"},
            headers={"Origin": ORIGIN, "X-AdvanCore-Action-Token": token},
        )

    assert [item.status_code for item in (missing_origin, wrong_token)] == [403, 403]
    assert unconfirmed.status_code == 400
    assert coerced.status_code == 422
    assert gateway.calls == []


def test_remote_peer_cannot_get_token_or_mutate(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, gateway, peer="203.0.113.10") as client:
        session = client.get("/api/session")
        mutation = client.post(
            "/api/projects",
            json={"name": "Test", "confirmed": True},
            headers={"Origin": ORIGIN, "X-AdvanCore-Action-Token": "unavailable"},
        )
    assert session.status_code == 403
    assert mutation.status_code == 403
    assert gateway.calls == []


def test_oversized_or_invalid_edit_never_reflects_submitted_content(tmp_path):
    marker = "DO_NOT_REFLECT_" + ("x" * 200_000)
    with _client(tmp_path) as client:
        headers = _headers(client)
        oversized = client.post(
            "/api/knowledge",
            json={"title": "Oversized", "content": marker, "confirmed": True},
            headers=headers,
        )
        invalid = client.post(
            "/api/projects",
            json={"name": marker[:500], "confirmed": "true"},
            headers=headers,
        )

    assert oversized.status_code == 413
    assert len(oversized.content) < 200
    assert marker[:30] not in oversized.text
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "Request validation failed."}
    assert marker[:30] not in invalid.text


def test_chunked_edit_body_stops_before_unbounded_buffering():
    downstream_called = False
    sent = []
    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 40_000, "more_body": True},
            {"type": "http.request", "body": b"x" * 40_000, "more_body": True},
            {"type": "http.request", "body": b"x" * 40_000, "more_body": True},
            {"type": "http.request", "body": b"x" * 40_000, "more_body": True},
            {"type": "http.request", "body": b"never-read", "more_body": False},
        ]
    )
    receive_calls = 0

    async def downstream(_scope, _receive, _send):
        nonlocal downstream_called
        downstream_called = True

    async def receive():
        nonlocal receive_calls
        receive_calls += 1
        return next(messages)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/knowledge",
        "raw_path": b"/api/knowledge",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
    }
    middleware = BoundedLocalEditBodyMiddleware(downstream)
    asyncio.run(middleware(scope, receive, send))

    assert downstream_called is False
    assert receive_calls == 4
    assert sent[0]["status"] == 413
    assert b"Local edit request is too large" in sent[1]["body"]


def test_project_and_knowledge_actions_delegate_exactly(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, gateway) as client:
        headers = _headers(client)
        responses = [
            client.post("/api/projects", json={"name": "P", "description": "D", "confirmed": True}, headers=headers),
            client.post("/api/projects/1/edit", json={"name": "P2", "description": None, "confirmed": True}, headers=headers),
            client.post("/api/projects/1/archive", json={"confirmed": True}, headers=headers),
            client.post("/api/knowledge", json={"title": "K", "content": "C", "confirmed": True}, headers=headers),
            client.post("/api/knowledge/2/edit", json={"title": "K2", "content": "C2", "confirmed": True}, headers=headers),
            client.post(
                "/api/knowledge/2/approve",
                json={
                    "expected_updated_at": NOW.isoformat(),
                    "expected_content_sha256": sha256(b"Saved content").hexdigest(),
                    "confirmed": True,
                },
                headers=headers,
            ),
            client.post("/api/knowledge/2/archive", json={"confirmed": True}, headers=headers),
            client.post("/api/knowledge/2/replacement", json={"confirmed": True}, headers=headers),
        ]
    assert [response.status_code for response in responses] == [201, 200, 200, 201, 200, 200, 200, 201]
    assert [call[0] for call in gateway.calls] == [
        "create_project", "edit_project", "archive_project", "create_knowledge",
        "edit_knowledge", "approve_knowledge", "archive_knowledge", "replace_knowledge",
    ]


def test_fleet_and_register_actions_delegate_existing_fields_only(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, gateway) as client:
        headers = _headers(client)
        responses = [
            client.post("/api/legal-entities", json={"name": "Advan", "confirmed": True}, headers=headers),
            client.post("/api/vehicles", json={"registration_number": "PC1A", "make_model": "Bus", "confirmed": True}, headers=headers),
            client.post("/api/vehicles/3/status", json={"status": "out_of_service", "confirmed": True}, headers=headers),
            client.post("/api/vehicles/3/details", json={"registered_owner_id": 5, "vehicle_type": "Bus", "passenger_capacity": 43, "road_tax_amount": "850.00", "road_tax_period_months": 6, "confirmed": True}, headers=headers),
            client.post("/api/drivers", json={"name": "Driver", "employee_reference": "D1", "confirmed": True}, headers=headers),
            client.post("/api/drivers/6/status", json={"status": "unavailable", "confirmed": True}, headers=headers),
            client.post("/api/customers", json={"name": "School", "customer_reference": "C1", "confirmed": True}, headers=headers),
            client.post("/api/customers/7/status", json={"status": "inactive", "confirmed": True}, headers=headers),
            client.post("/api/routes", json={"route_code": "R1", "origin": "Depot", "destination": "School", "confirmed": True}, headers=headers),
            client.post("/api/routes/8/status", json={"status": "inactive", "confirmed": True}, headers=headers),
        ]
    assert all(response.status_code in {200, 201} for response in responses)
    assert [call[0] for call in gateway.calls] == [
        "create_legal_entity", "create_vehicle", "set_vehicle_status",
        "update_vehicle_details", "create_driver", "set_driver_status",
        "create_customer", "set_customer_status", "create_route", "set_route_status",
    ]
    vehicle_payload = gateway.calls[3][2]
    assert vehicle_payload["passenger_capacity"] == 43
    assert vehicle_payload["road_tax_period_months"] == 6
    assert "worker" not in vehicle_payload


def test_extra_fields_and_coerced_integer_fields_fail_before_gateway(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, gateway) as client:
        headers = _headers(client)
        injected = client.post(
            "/api/drivers",
            json={"name": "Driver", "licence_number": "invented", "confirmed": True},
            headers=headers,
        )
        coerced = client.post(
            "/api/vehicles/3/details",
            json={"passenger_capacity": True, "confirmed": True},
            headers=headers,
        )
    assert injected.status_code == 422
    assert coerced.status_code == 422
    assert gateway.calls == []


def test_bounded_gateway_errors_map_without_internal_details(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, gateway) as client:
        headers = _headers(client)
        outcomes = []
        for failure in (
            EditingValidationError("Name is invalid."),
            EditingConflictError("Record is read-only."),
            EditingNotFoundError("Record was not found."),
            RuntimeError("password=must-not-leak"),
        ):
            gateway.failure = failure
            outcomes.append(client.post(
                "/api/projects",
                json={"name": "Test", "confirmed": True},
                headers=headers,
            ))
    assert [item.status_code for item in outcomes] == [400, 409, 404, 503]
    assert "must-not-leak" not in outcomes[-1].text


def test_minimal_register_reads_are_get_only_and_use_existing_fields(tmp_path):
    with _client(tmp_path, read_gateway=FakeReadGateway()) as client:
        drivers = client.get("/api/drivers")
        customers = client.get("/api/customers")
        routes = client.get("/api/routes")
    assert drivers.json() == [{"id": 1, "name": "Driver A", "employee_reference": "D1", "status": "active"}]
    assert customers.json()[0]["customer_reference"] == "C1"
    assert routes.json()[0] == {"id": 3, "route_code": "R1", "origin": "Depot", "destination": "School", "status": "active"}
