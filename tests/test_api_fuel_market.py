from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from advancore.api.app import create_app
from advancore.api.schemas import (
    FuelAdjustmentDraftResponse,
    RecurringServiceFuelRuleResponse,
)


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:8000"


def _rule():
    return RecurringServiceFuelRuleResponse(
        id=8,
        recurring_service_id=31,
        effective_from=date(2026, 9, 1),
        effective_to=None,
        baseline_price_per_litre=Decimal("3.0000"),
        fuel_cost_share_percent=Decimal("30.0000"),
        tolerance_percent=Decimal("5.0000"),
        created_at=NOW,
        updated_at=NOW,
    )


class ReadGateway:
    def __init__(self):
        self.calls = []

    def recurring_service_fuel_adjustment(self, identifier):
        self.calls.append(identifier)
        return FuelAdjustmentDraftResponse(
            recurring_service_id=identifier,
            calculation_status="draft_ready",
            stale=False,
            benchmark_observed_on=date(2026, 9, 3),
            benchmark_price_per_litre=Decimal("4.0000"),
            monthly_contract_amount=Decimal("10000.00"),
            currency_code="SGD",
            price_variance_percent=Decimal("33.3333"),
            draft_adjustment_amount=Decimal("1000.00"),
            adjusted_monthly_amount=Decimal("11000.00"),
            current_rule=_rule(),
            rule_history=[_rule()],
        )


class EditGateway:
    def __init__(self):
        self.calls = []

    def create_recurring_service_fuel_rule(self, identifier, payload):
        self.calls.append((identifier, payload))
        return _rule()


def _client(tmp_path, read_gateway, edit_gateway, peer="127.0.0.1"):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return TestClient(
        create_app(
            repo_root=tmp_path,
            frontend_dir=frontend,
            read_gateway=read_gateway,
            edit_gateway=edit_gateway,
            orchestration_service=SimpleNamespace(shutdown=lambda: None),
            fuel_refresher=SimpleNamespace(start=lambda: None, shutdown=lambda: None),
        ),
        client=(peer, 50000),
    )


def test_draft_read_is_loopback_only_and_never_writes(tmp_path):
    gateway = ReadGateway()
    with _client(tmp_path, gateway, EditGateway()) as client:
        response = client.get("/api/recurring-services/31/fuel-adjustment")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["draft_adjustment_amount"] == "1000.00"
    assert gateway.calls == [31]


def test_contract_rule_write_keeps_action_token_and_confirmation_gate(tmp_path):
    gateway = EditGateway()
    payload = {
        "effective_from": "2026-09-01",
        "baseline_price_per_litre": "3.0000",
        "fuel_cost_share_percent": "30",
        "tolerance_percent": "5",
        "confirmed": True,
    }
    with _client(tmp_path, ReadGateway(), gateway) as client:
        rejected = client.post(
            "/api/recurring-services/31/fuel-rules",
            json=payload,
            headers={"Origin": ORIGIN},
        )
        token = client.get("/api/session").json()["action_token"]
        accepted = client.post(
            "/api/recurring-services/31/fuel-rules",
            json=payload,
            headers={"Origin": ORIGIN, "X-AdvanCore-Action-Token": token},
        )
    assert rejected.status_code == 403
    assert accepted.status_code == 201
    assert gateway.calls[0][0] == 31


def test_non_loopback_peer_cannot_read_contract_fuel_values(tmp_path):
    gateway = ReadGateway()
    with _client(tmp_path, gateway, EditGateway(), peer="198.51.100.10") as client:
        response = client.get(
            "/api/recurring-services/31/fuel-adjustment",
            headers={"Host": "localhost"},
        )
    assert response.status_code == 403
    assert gateway.calls == []
