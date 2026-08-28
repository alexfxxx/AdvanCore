from datetime import date

from fastapi.testclient import TestClient

from advancore.api.app import create_app
from tests.api_operations_helpers import FakeOperationsGateway


def test_dispatch_endpoint_projects_one_recorded_day(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("dispatch", encoding="utf-8")
    gateway = FakeOperationsGateway()
    with TestClient(create_app(repo_root=tmp_path, frontend_dir=frontend, read_gateway=gateway)) as client:
        response = client.get("/api/dispatch?service_date=2026-08-28")

    assert response.status_code == 200
    assert gateway.dispatch_date == date(2026, 8, 28)
    assert response.json()["rows"][0]["dispatch_state"] == "Unassigned"
    assert response.json()["available_vehicles"][0]["label"] == "PC5234D"


def test_dispatch_rejects_missing_or_invalid_date(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("dispatch", encoding="utf-8")
    with TestClient(create_app(repo_root=tmp_path, frontend_dir=frontend, read_gateway=FakeOperationsGateway())) as client:
        missing = client.get("/api/dispatch")
        invalid = client.get("/api/dispatch?service_date=tomorrow")

    assert missing.status_code == 422
    assert invalid.status_code == 422
