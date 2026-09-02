from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from advancore.api.app import create_app
from advancore.api.schemas import DriverEmploymentResponse


NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:8000"


def _record(**values):
    return DriverEmploymentResponse(
        id=values.get("id", 41), driver_id=values.get("driver_id", 8),
        effective_month=values.get("effective_month", date(2026, 7, 1)),
        worker_category=values.get("worker_category", "local_pr"),
        basic_salary=Decimal("3000.00"), employer_cpf_amount=Decimal("510.00"),
        monthly_levy_amount=None, monthly_allowance=Decimal("100.00"),
        employment_status="active", created_at=NOW, updated_at=NOW,
    )


class FakeReadGateway:
    def __init__(self): self.calls = []
    def list_driver_employment_records(self, driver_id):
        self.calls.append(driver_id)
        return [_record(driver_id=driver_id)]


class FakeEditingGateway:
    def __init__(self): self.calls = []
    def create_driver_employment_record(self, payload):
        self.calls.append(payload)
        return _record(driver_id=payload.driver_id, effective_month=payload.effective_month)


def _client(tmp_path, read_gateway, edit_gateway, *, peer="127.0.0.1"):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return TestClient(create_app(
        repo_root=tmp_path, frontend_dir=frontend, read_gateway=read_gateway,
        edit_gateway=edit_gateway, orchestration_service=SimpleNamespace(shutdown=lambda: None),
    ), client=(peer, 50000))


def _headers(client):
    token = client.get("/api/session").json()["action_token"]
    return {"Origin": ORIGIN, "X-AdvanCore-Action-Token": token}


def _payload(**overrides):
    values = {
        "driver_id": 8, "effective_month": "2026-07-01", "worker_category": "local_pr",
        "basic_salary": "3000.00", "employer_cpf_amount": "510.00",
        "monthly_levy_amount": None, "monthly_allowance": "100.00",
        "employment_status": "active", "confirmed": True,
    }
    values.update(overrides)
    return values


def test_private_driver_profile_reads_effective_history(tmp_path):
    gateway = FakeReadGateway()
    with _client(tmp_path, gateway, FakeEditingGateway()) as client:
        response = client.get("/api/drivers/8/employment-records")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()[0]["basic_salary"] == "3000.00"
    assert gateway.calls == [8]


def test_non_loopback_peer_cannot_read_private_employment_history(tmp_path):
    gateway = FakeReadGateway()
    with _client(
        tmp_path, gateway, FakeEditingGateway(), peer="198.51.100.7"
    ) as client:
        response = client.get(
            "/api/drivers/8/employment-records", headers={"Host": "localhost"}
        )
    assert response.status_code == 403
    assert gateway.calls == []


def test_confirmed_employment_write_delegates_and_invalid_confirmation_fails(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, FakeReadGateway(), gateway) as client:
        headers = _headers(client)
        created = client.post("/api/driver-employment-records", json=_payload(), headers=headers)
        rejected = client.post("/api/driver-employment-records", json=_payload(confirmed="true"), headers=headers)
    assert created.status_code == 201
    assert rejected.status_code == 422
    assert len(gateway.calls) == 1


def test_action_token_and_origin_protect_private_payroll_write(tmp_path):
    gateway = FakeEditingGateway()
    with _client(tmp_path, FakeReadGateway(), gateway) as client:
        missing = client.post("/api/driver-employment-records", json=_payload(), headers={"Origin": ORIGIN})
        foreign = client.post("/api/driver-employment-records", json=_payload(), headers={"Origin": "https://example.invalid", "X-AdvanCore-Action-Token": "invalid"})
    assert missing.status_code == 403
    assert foreign.status_code == 403
    assert gateway.calls == []
