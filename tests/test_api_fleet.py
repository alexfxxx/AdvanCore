from fastapi.testclient import TestClient

from advancore.api.app import create_app
from tests.api_operations_helpers import FakeOperationsGateway


def test_fleet_endpoint_is_filtered_and_read_only(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("fleet", encoding="utf-8")
    gateway = FakeOperationsGateway()
    with TestClient(create_app(repo_root=tmp_path, frontend_dir=frontend, read_gateway=gateway)) as client:
        response = client.get("/api/fleet?registered_owner_id=7&vehicle_type=Bus&passenger_capacity=43")
        write_attempt = client.post("/api/fleet", json={"registration_number": "NEW"})

    assert response.status_code == 200
    assert gateway.fleet_filters == (7, "Bus", 43)
    assert response.json()["vehicles"][0]["registration_number"] == "PC5234D"
    assert response.json()["vehicles"][0]["road_tax_amount"] == "850.00"
    assert response.json()["vehicles"][0]["finance_company"] == "Example Finance"
    assert response.json()["vehicles"][0]["remaining_scheduled_payments"] == 41
    assert response.json()["vehicles"][0]["projected_remaining_scheduled_amount"] == "102500.00"
    assert write_attempt.status_code == 405
