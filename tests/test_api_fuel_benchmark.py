from fastapi.testclient import TestClient

from advancore.api.app import create_app
from tests.api_operations_helpers import FakeOperationsGateway


def test_fuel_endpoints_keep_recorded_facts_and_market_reference_separate(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("fuel", encoding="utf-8")
    with TestClient(
        create_app(repo_root=tmp_path, frontend_dir=frontend, read_gateway=FakeOperationsGateway()),
        client=("127.0.0.1", 50000),
    ) as client:
        facts = client.get("/api/fuel/intelligence")
        market = client.get("/api/fuel/market-benchmark")

    assert facts.json()["entry_count"] == 2
    assert "market_observations" not in facts.json()
    assert market.json()["median"] == "3.95"
    assert "entry_count" not in market.json()
    assert market.headers["cache-control"] == "no-store"


def test_non_loopback_peer_cannot_read_fuel_market_benchmark(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("fuel", encoding="utf-8")
    with TestClient(
        create_app(repo_root=tmp_path, frontend_dir=frontend, read_gateway=FakeOperationsGateway()),
        client=("198.51.100.7", 50000),
    ) as client:
        response = client.get("/api/fuel/market-benchmark", headers={"Host": "localhost"})

    assert response.status_code == 403
