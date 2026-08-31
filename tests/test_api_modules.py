from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from advancore.api.app import create_app


def test_read_only_module_catalog_endpoint_requires_no_database(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    service = SimpleNamespace(shutdown=lambda: None)
    app = create_app(
        repo_root=tmp_path,
        frontend_dir=frontend,
        read_gateway=SimpleNamespace(),
        goal_previewer=SimpleNamespace(),
        orchestration_service=service,
    )

    with TestClient(app) as client:
        response = client.get("/api/modules")

    assert response.status_code == 200
    payload = response.json()
    assert [item["module_id"] for item in payload] == [
        "dashboard",
        "knowledge_hub",
        "projects",
        "transport_operations",
        "ai_center",
        "activity_log",
        "settings",
    ]
    transport = next(item for item in payload if item["module_id"] == "transport_operations")
    assert transport["maturity"] == "transitional"
    assert transport["presentation_surfaces"] == [
        "primary_console",
        "temporary_streamlit_admin",
    ]
    assert "/api/fleet" in transport["api_prefixes"]
    activity = next(item for item in payload if item["module_id"] == "activity_log")
    assert activity["presentation_surfaces"] == ["temporary_streamlit_admin"]


def test_module_endpoint_is_get_only(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    app = create_app(
        repo_root=tmp_path,
        frontend_dir=frontend,
        read_gateway=SimpleNamespace(),
        goal_previewer=SimpleNamespace(),
        orchestration_service=SimpleNamespace(shutdown=lambda: None),
    )
    with TestClient(app) as client:
        response = client.post("/api/modules", json={})
    assert response.status_code == 405
