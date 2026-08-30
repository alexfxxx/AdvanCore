"""Contract tests for the decoupled local FastAPI console."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from advancore.agent_runner.goal_task import GoalTaskGenerationStatus
from advancore.agent_runner.worker import DryRunWorkerAdapter
from advancore.api import dependencies
from advancore.api.app import create_app
from advancore.api.dependencies import ControllerOwnerGoalPreviewer
from advancore.api.schemas import (
    KnowledgeResponse,
    OwnerGoalPreviewResponse,
    ProjectResponse,
    SystemStatusResponse,
)


NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


class FakeReadGateway:
    def status(self) -> SystemStatusResponse:
        return SystemStatusResponse(
            state="ready",
            database_configured=True,
            database_reachable=True,
            controller_available=True,
        )

    def list_projects(self) -> list[ProjectResponse]:
        return [
            ProjectResponse(
                id=1,
                name="Operations",
                description=None,
                status="active",
                created_at=NOW,
                updated_at=NOW,
            )
        ]

    def list_knowledge(self) -> list[KnowledgeResponse]:
        return [
            KnowledgeResponse(
                id=2,
                project_id=1,
                title="Approved operating note",
                content="Source-backed content.",
                status="approved",
                created_at=NOW,
                updated_at=NOW,
            )
        ]


class FakeGoalPreviewer:
    def preview(self, goal: str) -> OwnerGoalPreviewResponse:
        return OwnerGoalPreviewResponse(
            accepted=True,
            normalized_goal=" ".join(goal.split()),
            status="dry_run",
            candidate_task_id="TASK-127",
            next_action="controller/owner review",
            messages=["PASS: dry-run only"],
        )


def _client(tmp_path: Path) -> TestClient:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<!doctype html><title>AdvanCore test console</title>",
        encoding="utf-8",
    )
    return TestClient(
        create_app(
            repo_root=tmp_path,
            frontend_dir=frontend,
            read_gateway=FakeReadGateway(),
            goal_previewer=FakeGoalPreviewer(),
        )
    )


def test_fastapi_serves_static_console_and_bounded_status(tmp_path):
    with _client(tmp_path) as client:
        page = client.get("/")
        response = client.get("/api/status")

    assert page.status_code == 200
    assert "AdvanCore test console" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert response.status_code == 200
    assert response.json() == {
        "service": "AdvanCore local API",
        "state": "ready",
        "database_configured": True,
        "database_reachable": True,
        "controller_available": True,
        "governance_mode": "fail_closed",
        "voice_state": "disabled",
    }


def test_read_only_project_and_knowledge_contracts(tmp_path):
    with _client(tmp_path) as client:
        projects = client.get("/api/projects")
        knowledge = client.get("/api/knowledge")

    assert projects.status_code == 200
    assert projects.json()[0]["name"] == "Operations"
    assert projects.json()[0]["description"] is None
    assert knowledge.status_code == 200
    assert knowledge.json()[0]["content"] == "Source-backed content."


def test_owner_goal_endpoint_returns_preview_without_execution(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/owner-goals/preview",
            json={"goal": "  Improve   route planning  "},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["normalized_goal"] == "Improve route planning"
    assert payload["status"] == "dry_run"
    assert payload["planner_launched"] is False
    assert payload["task_written"] is False
    assert payload["execution_requested"] is False
    assert payload["publication_performed"] is False


def test_owner_goal_payload_is_bounded_before_controller_call(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/owner-goals/preview",
            json={"goal": "x" * 2001},
        )

    assert response.status_code == 422


def test_controller_adapter_hard_codes_dry_run(monkeypatch, tmp_path):
    captured = {}

    def fake_generate_goal_task(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            goal_accepted=True,
            status=GoalTaskGenerationStatus.DRY_RUN,
            task_id="TASK-127",
            task_written=False,
            no_publication_performed=True,
            next_action="controller/owner review",
            messages=["PASS: dry-run"],
        )

    monkeypatch.setattr(dependencies, "generate_goal_task", fake_generate_goal_task)

    preview = ControllerOwnerGoalPreviewer(tmp_path).preview("Review routes")

    assert captured["execute"] is False
    assert isinstance(captured["planner"], DryRunWorkerAdapter)
    assert preview.task_written is False
    assert preview.execution_requested is False
    assert preview.publication_performed is False


def test_cors_allows_only_explicit_loopback_origins(tmp_path):
    headers = {
        "Origin": "http://127.0.0.1:5500",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    blocked_headers = {**headers, "Origin": "https://untrusted.example"}

    with _client(tmp_path) as client:
        allowed = client.options("/api/owner-goals/preview", headers=headers)
        blocked = client.options(
            "/api/owner-goals/preview", headers=blocked_headers
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == headers["Origin"]
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers


def test_voice_websocket_is_disabled_and_accepts_no_audio(tmp_path):
    with _client(tmp_path) as client:
        with client.websocket_connect("/ws/transcription") as websocket:
            message = websocket.receive_json()

    assert message["state"] == "disabled"
    assert "not accepted or stored" in message["message"]


def test_authority_bearing_console_loads_no_remote_executable_script():
    root = Path(__file__).resolve().parents[1]
    page = (root / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "cdn.tailwindcss.com" not in page
    assert '<script src="http' not in page
