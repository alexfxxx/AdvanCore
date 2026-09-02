from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from advancore.api.app import create_app
from advancore.api.schemas import RecurringServiceResponse


NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:8000"


def _record(**values):
    return RecurringServiceResponse(
        id=values.get("id", 31), customer_id=values.get("customer_id", 7),
        route_id=values.get("route_id", 9), service_reference="SYN-ROUTE",
        vehicle_requirement="Synthetic vehicle", monthly_amount=Decimal("1000.00"),
        currency_code="SGD", effective_start_date=values.get("effective_start_date", date(2026, 1, 1)),
        effective_end_date=None, status=values.get("status", "active"),
        replaces_recurring_service_id=values.get("replaces_recurring_service_id"),
        days=[{"weekday": 0}, {"weekday": 2}],
        stops=[{"stop_order": 0, "location_name": "Synthetic stop", "scheduled_time": time(7, 0)}],
        created_at=NOW, updated_at=NOW,
    )


class FakeReadGateway:
    def __init__(self): self.calls = []
    def list_recurring_services_by_customer(self, customer_id):
        self.calls.append(customer_id)
        return [_record(customer_id=customer_id)]


class FakeEditingGateway:
    def __init__(self): self.calls = []
    def create_recurring_service(self, payload):
        self.calls.append(("create", payload))
        return _record(customer_id=payload.customer_id, route_id=payload.route_id)
    def set_recurring_service_status(self, identifier, payload):
        self.calls.append(("status", identifier, payload.status))
        return _record(id=identifier, status=payload.status)
    def replace_recurring_service(self, identifier, payload):
        self.calls.append(("replace", identifier, payload))
        return _record(id=32, replaces_recurring_service_id=identifier, effective_start_date=payload.effective_start_date)


def _client(tmp_path, read_gateway, edit_gateway):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return TestClient(create_app(
        repo_root=tmp_path, frontend_dir=frontend, read_gateway=read_gateway,
        edit_gateway=edit_gateway, orchestration_service=SimpleNamespace(shutdown=lambda: None),
    ), client=("127.0.0.1", 50000))


def _headers(client):
    token = client.get("/api/session").json()["action_token"]
    return {"Origin": ORIGIN, "X-AdvanCore-Action-Token": token}


def _payload(**overrides):
    values = {
        "customer_id": 7, "route_id": 9, "service_reference": "SYN-ROUTE",
        "vehicle_requirement": "Synthetic vehicle", "monthly_amount": "1000.00",
        "currency_code": "SGD", "effective_start_date": "2026-01-01",
        "effective_end_date": None, "weekdays": [0, 2],
        "stops": [{"stop_order": 0, "location_name": "Synthetic stop", "scheduled_time": "07:00:00"}],
        "confirmed": True,
    }
    values.update(overrides)
    return values


def test_customer_profile_reads_nested_recurring_services(tmp_path):
    read_gateway = FakeReadGateway()
    with _client(tmp_path, read_gateway, FakeEditingGateway()) as client:
        response = client.get("/api/customers/7/recurring-services")
    assert response.status_code == 200
    assert response.json()[0]["monthly_amount"] == "1000.00"
    assert read_gateway.calls == [7]


def test_confirmed_create_status_and_replacement_delegate_exact_payloads(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, FakeReadGateway(), gateway) as client:
        headers = _headers(client)
        created = client.post("/api/recurring-services", json=_payload(), headers=headers)
        status = client.post("/api/recurring-services/31/status", json={"status": "paused", "confirmed": True}, headers=headers)
        replacement_payload = _payload(effective_start_date="2026-07-01")
        replacement_payload.pop("customer_id")
        replaced = client.post("/api/recurring-services/31/replacement", json=replacement_payload, headers=headers)
        rejected = client.post("/api/recurring-services", json=_payload(confirmed="true"), headers=headers)
    assert [created.status_code, status.status_code, replaced.status_code] == [201, 200, 201]
    assert rejected.status_code == 422
    assert [call[0] for call in gateway.calls] == ["create", "status", "replace"]


def test_non_loopback_or_missing_action_token_cannot_write(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, FakeReadGateway(), gateway) as client:
        missing = client.post("/api/recurring-services", json=_payload(), headers={"Origin": ORIGIN})
        foreign = client.post("/api/recurring-services", json=_payload(), headers={"Origin": "https://example.invalid", "X-AdvanCore-Action-Token": "invalid"})
    assert missing.status_code == 403
    assert foreign.status_code == 403
    assert gateway.calls == []
