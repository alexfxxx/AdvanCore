from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from advancore.api.app import create_app
from advancore.api.dependencies import DatabaseReadModelGateway
from tests.api_operations_helpers import FakeOperationsGateway


ROOT = Path(__file__).resolve().parents[1]


def test_dated_market_snapshot_computes_pre_discount_diesel_benchmark():
    benchmark = DatabaseReadModelGateway(ROOT).fuel_market_benchmark()

    assert benchmark.basis == "gross pump price before discounts"
    assert benchmark.low == Decimal("3.89")
    assert benchmark.median == Decimal("3.95")
    assert benchmark.high == Decimal("4.05")
    assert {item.source_name for item in benchmark.official_confirmations} == {
        "SPC Singapore",
        "Shell Singapore",
    }


def test_fuel_endpoints_keep_recorded_facts_and_market_reference_separate(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("fuel", encoding="utf-8")
    with TestClient(create_app(repo_root=tmp_path, frontend_dir=frontend, read_gateway=FakeOperationsGateway())) as client:
        facts = client.get("/api/fuel/intelligence")
        market = client.get("/api/fuel/market-benchmark")

    assert facts.json()["entry_count"] == 2
    assert "market_observations" not in facts.json()
    assert market.json()["median"] == "3.95"
    assert "entry_count" not in market.json()
