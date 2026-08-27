"""Contract tests for controller-mediated local orchestration."""

from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from advancore.agent_runner.orchestration import OrchestrationError, OwnerAction
from advancore.api.app import create_app
from advancore.api import orchestration_service as orchestration_service_module
from advancore.api.orchestration_service import (
    GovernedOrchestrationService,
    OrchestrationJobBusy,
)
from advancore.agent_runner.orchestration import default_orchestration_dir
from advancore.api.schemas import (
    OrchestrationJobResponse,
    OrchestrationPreviewResponse,
    OrchestrationRunResponse,
)


NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:8000"


def _result(**overrides):
    values = {
        "run_id": "ORCH-test",
        "task_id": "TASK-127",
        "phase": "AWAITING_TASK_APPROVAL",
        "status": "AWAITING_TASK_APPROVAL",
        "owner_decision_required": True,
        "next_action": "Review the governed task.",
        "mutations_performed": [],
        "blocking_reason": None,
        "messages": ["Controller stopped at the task approval gate."],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _job(**overrides) -> OrchestrationJobResponse:
    values = {
        "job_id": "JOB-test",
        "operation": "start",
        "state": "completed",
        "terminal": True,
        "run_id": "ORCH-test",
        "task_id": "TASK-127",
        "phase": "AWAITING_TASK_APPROVAL",
        "status": "AWAITING_TASK_APPROVAL",
        "owner_decision_required": True,
        "message": "Controller stopped at the approval gate.",
        "next_action": "Review the governed task.",
        "events_url": "/api/orchestration-jobs/JOB-test/events",
        "updated_at": NOW,
    }
    values.update(overrides)
    return OrchestrationJobResponse(**values)


class FakeOrchestrationService:
    def __init__(self):
        self.calls = []

    def preview(self, goal: str) -> OrchestrationPreviewResponse:
        self.calls.append(("preview", goal))
        return OrchestrationPreviewResponse(
            run_id="ORCH-preview",
            task_id="TASK-127",
            phase="AWAITING_TASK_APPROVAL",
            status="AWAITING_TASK_APPROVAL",
            owner_decision_required=True,
            next_action="Review the governed task.",
            mutations_performed=[],
        )

    def start(self, goal: str) -> OrchestrationJobResponse:
        self.calls.append(("start", goal))
        return _job()

    def resume(self, run_id: str) -> OrchestrationJobResponse:
        self.calls.append(("resume", run_id))
        return _job(operation="resume", run_id=run_id)

    def owner_action(
        self, run_id: str, action: str, owner_note: str | None
    ) -> OrchestrationJobResponse:
        self.calls.append(("action", run_id, action, owner_note))
        return _job(operation="owner_action", run_id=run_id)

    def get_job(self, job_id: str) -> OrchestrationJobResponse:
        self.calls.append(("get_job", job_id))
        return _job(job_id=job_id, events_url=f"/api/orchestration-jobs/{job_id}/events")

    def get_current_job(self) -> OrchestrationJobResponse:
        self.calls.append(("get_current_job",))
        return _job()

    def get_run(self, run_id: str) -> OrchestrationRunResponse:
        self.calls.append(("get_run", run_id))
        return OrchestrationRunResponse(
            run_id=run_id,
            task_id="TASK-127",
            phase="AWAITING_TASK_APPROVAL",
            status="AWAITING_TASK_APPROVAL",
            branch="task-127-controller-mediated-launch-progress",
            completed_phases=["GOAL_VALIDATION"],
            owner_decision_count=0,
            push_verified=False,
            updated_at=NOW,
            messages=["Awaiting owner review."],
        )


def _client(tmp_path: Path, service: FakeOrchestrationService):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return TestClient(
        create_app(
            repo_root=tmp_path,
            frontend_dir=frontend,
            orchestration_service=service,
        )
    )


def _action_headers(client: TestClient) -> dict[str, str]:
    token_response = client.get("/api/session")
    assert token_response.headers["cache-control"] == "no-store"
    return {
        "Origin": ORIGIN,
        "X-AdvanCore-Action-Token": token_response.json()["action_token"],
    }


def test_preview_is_read_only_and_requires_no_action_token(tmp_path):
    service = FakeOrchestrationService()
    with _client(tmp_path, service) as client:
        response = client.post(
            "/api/orchestrations/preview", json={"goal": "Improve dispatch"}
        )

    assert response.status_code == 200
    assert response.json()["mutations_performed"] == []
    assert service.calls == [("preview", "Improve dispatch")]


def test_start_requires_allowed_origin_token_and_confirmation(tmp_path):
    service = FakeOrchestrationService()
    with _client(tmp_path, service) as client:
        token = client.get("/api/session").json()["action_token"]
        missing_origin = client.post(
            "/api/orchestrations",
            json={"goal": "Improve dispatch", "confirmed": True},
            headers={"X-AdvanCore-Action-Token": token},
        )
        wrong_token = client.post(
            "/api/orchestrations",
            json={"goal": "Improve dispatch", "confirmed": True},
            headers={"Origin": ORIGIN, "X-AdvanCore-Action-Token": "wrong"},
        )
        unconfirmed = client.post(
            "/api/orchestrations",
            json={"goal": "Improve dispatch", "confirmed": False},
            headers={"Origin": ORIGIN, "X-AdvanCore-Action-Token": token},
        )

    assert missing_origin.status_code == 403
    assert wrong_token.status_code == 403
    assert unconfirmed.status_code == 400
    assert service.calls == []


def test_start_rejects_coerced_boolean_and_policy_injection(tmp_path):
    service = FakeOrchestrationService()
    with _client(tmp_path, service) as client:
        headers = _action_headers(client)
        coerced = client.post(
            "/api/orchestrations",
            json={"goal": "Improve dispatch", "confirmed": "true"},
            headers=headers,
        )
        injected = client.post(
            "/api/orchestrations",
            json={
                "goal": "Improve dispatch",
                "confirmed": True,
                "worker": "codex",
                "branch": "main",
                "apply": True,
            },
            headers=headers,
        )

    assert coerced.status_code == 422
    assert injected.status_code == 422
    assert service.calls == []


def test_confirmed_start_and_exact_owner_action_delegate_only_to_service(tmp_path):
    service = FakeOrchestrationService()
    with _client(tmp_path, service) as client:
        headers = _action_headers(client)
        started = client.post(
            "/api/orchestrations",
            json={"goal": "Improve dispatch", "confirmed": True},
            headers=headers,
        )
        action = client.post(
            "/api/orchestrations/ORCH-test/actions",
            json={"action": "APPROVE_TASK", "confirmed": True},
            headers=headers,
        )

    assert started.status_code == 202
    assert action.status_code == 202
    assert service.calls == [
        ("start", "Improve dispatch"),
        ("action", "ORCH-test", "APPROVE_TASK", None),
    ]


def test_invalid_action_and_run_identifier_fail_closed(tmp_path):
    service = FakeOrchestrationService()
    with _client(tmp_path, service) as client:
        headers = _action_headers(client)
        invalid_action = client.post(
            "/api/orchestrations/ORCH-test/actions",
            json={"action": "APPROVE_ALL", "confirmed": True},
            headers=headers,
        )
        invalid_run = client.post(
            "/api/orchestrations/not-a-governed-run/resume",
            json={"confirmed": True},
            headers=headers,
        )

    assert invalid_action.status_code == 422
    assert invalid_run.status_code == 400
    assert service.calls == []


def test_terminal_sse_stream_emits_bounded_job_snapshot(tmp_path):
    service = FakeOrchestrationService()
    with _client(tmp_path, service) as client:
        response = client.get("/api/orchestration-jobs/JOB-test/events")

    assert response.status_code == 200
    assert "event: progress" in response.text
    assert '"terminal":true' in response.text
    assert "goal" not in response.text.lower()


def test_current_job_endpoint_restores_progress_after_page_refresh(tmp_path):
    service = FakeOrchestrationService()
    with _client(tmp_path, service) as client:
        response = client.get("/api/orchestration-jobs/current")

    assert response.status_code == 200
    assert response.json()["job_id"] == "JOB-test"
    assert service.calls == [("get_current_job",)]


def test_service_uses_fixed_governed_policy_for_preview_and_start(tmp_path):
    captured = []

    def runner(config, repo_root):
        captured.append((config, repo_root))
        return _result()

    service = GovernedOrchestrationService(tmp_path, runner=runner)
    preview = service.preview("Improve dispatch")
    job = service.start("Improve dispatch")
    deadline = time.monotonic() + 2
    while not service.get_job(job.job_id).terminal and time.monotonic() < deadline:
        time.sleep(0.01)

    preview_config, preview_root = captured[0]
    start_config, start_root = captured[1]
    for config in (preview_config, start_config):
        assert config.planner == "kimi-swarm"
        assert config.fallback_planner == "codex"
        assert config.worker == "kimi-swarm"
        assert config.fallback_worker == "codex"
        assert config.controller == "manual"
        assert config.unattended is True
        assert config.repair_attempts == 2
        assert config.max_rework == 1
    assert preview_config.apply is False
    assert start_config.apply is True
    assert preview_root == start_root == tmp_path.resolve()
    assert preview.mutations_performed == []


def test_service_delegates_exact_owner_action_without_goal_text(tmp_path):
    captured = []

    def runner(config, repo_root):
        captured.append(config)
        return _result(status="PUBLISHED", phase="PUBLISHED")

    service = GovernedOrchestrationService(tmp_path, runner=runner)
    job = service.owner_action("ORCH-test", "APPROVE_IMPLEMENTATION")
    deadline = time.monotonic() + 2
    snapshot = service.get_job(job.job_id)
    while not snapshot.terminal and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = service.get_job(job.job_id)

    config = captured[0]
    assert config.resume_run_id == "ORCH-test"
    assert config.apply is True
    assert config.owner_action is OwnerAction.APPROVE_IMPLEMENTATION
    assert not hasattr(snapshot, "goal")
    assert "Improve" not in snapshot.model_dump_json()


def test_service_allows_only_one_active_repository_job(tmp_path):
    release = Event()

    def runner(config, repo_root):
        release.wait(timeout=2)
        return _result()

    service = GovernedOrchestrationService(tmp_path, runner=runner)
    first = service.start("First governed goal")
    try:
        try:
            service.start("Second governed goal")
            raised = False
        except OrchestrationJobBusy:
            raised = True
        assert raised is True
    finally:
        release.set()

    deadline = time.monotonic() + 2
    while not service.get_job(first.job_id).terminal and time.monotonic() < deadline:
        time.sleep(0.01)


def test_repository_lock_blocks_a_second_server_instance(tmp_path):
    entered = Event()
    release = Event()
    lock_path = tmp_path / "controller-state" / "repository.lock"

    def blocked_runner(config, repo_root):
        entered.set()
        release.wait(timeout=2)
        return _result()

    first_service = GovernedOrchestrationService(
        tmp_path, runner=blocked_runner, repository_lock_path=lock_path
    )
    second_service = GovernedOrchestrationService(
        tmp_path, runner=lambda *_args: _result(), repository_lock_path=lock_path
    )
    first = first_service.start("First governed goal")
    assert entered.wait(timeout=1)
    try:
        with pytest.raises(OrchestrationJobBusy, match="active or requires recovery"):
            second_service.start("Second governed goal")
    finally:
        release.set()

    deadline = time.monotonic() + 2
    while not first_service.get_job(first.job_id).terminal and time.monotonic() < deadline:
        time.sleep(0.01)
    while lock_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not lock_path.exists()


def test_shutdown_waits_for_active_governed_work_and_stops_new_intake(tmp_path):
    entered = Event()
    release = Event()
    shutdown_done = Event()
    lock_path = tmp_path / "controller-state" / "repository.lock"

    def runner(config, repo_root):
        entered.set()
        release.wait(timeout=2)
        return _result()

    service = GovernedOrchestrationService(
        tmp_path, runner=runner, repository_lock_path=lock_path
    )
    job = service.start("Governed goal")
    assert entered.wait(timeout=1)

    def stop_service():
        service.shutdown()
        shutdown_done.set()

    shutdown_thread = Thread(target=stop_service)
    shutdown_thread.start()
    time.sleep(0.05)
    assert not shutdown_done.is_set()
    with pytest.raises(OrchestrationJobBusy, match="shutting down"):
        service.start("New goal during shutdown")
    release.set()
    shutdown_thread.join(timeout=2)

    assert shutdown_done.is_set()
    assert service.get_job(job.job_id).terminal
    assert not lock_path.exists()


def test_new_job_discovers_checkpoint_and_exposes_live_phase(monkeypatch, tmp_path):
    checkpoint_ready = Event()
    release = Event()
    run_id = "ORCH-live-progress"
    checkpoint_times = {}

    def runner(config, repo_root):
        checkpoint_times["created_at"] = datetime.now(timezone.utc).isoformat()
        directory = default_orchestration_dir(repo_root)
        directory.mkdir(parents=True)
        (directory / f"{run_id}.json").write_text("{}", encoding="utf-8")
        checkpoint_ready.set()
        release.wait(timeout=2)
        return _result(run_id=run_id, phase="AWAITING_TASK_APPROVAL")

    def fake_load_checkpoint(candidate, repo_root):
        assert candidate == run_id
        return SimpleNamespace(
            run_id=run_id,
            task_id="TASK-live",
            phase="TASK_DRAFT_GENERATION",
            status="TASK_EXECUTION",
            created_at=checkpoint_times["created_at"],
            updated_at=checkpoint_times["created_at"],
            messages=["Planner is preparing the governed draft."],
        )

    monkeypatch.setattr(
        orchestration_service_module, "load_checkpoint", fake_load_checkpoint
    )
    service = GovernedOrchestrationService(
        tmp_path,
        runner=runner,
        repository_lock_path=tmp_path / "controller-state" / "repository.lock",
    )
    job = service.start("Governed goal")
    assert checkpoint_ready.wait(timeout=1)
    snapshot = service.get_job(job.job_id)
    release.set()

    assert snapshot.run_id == run_id
    assert snapshot.phase == "TASK_DRAFT_GENERATION"
    assert snapshot.task_id == "TASK-live"
    assert "preparing" in snapshot.message


def test_background_error_does_not_expose_exception_details(tmp_path):
    def runner(config, repo_root):
        raise OrchestrationError("secret-token-value must never reach the browser")

    service = GovernedOrchestrationService(tmp_path, runner=runner)
    job = service.start("Governed goal")
    deadline = time.monotonic() + 2
    snapshot = service.get_job(job.job_id)
    while not snapshot.terminal and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = service.get_job(job.job_id)

    assert snapshot.state == "failed"
    assert "secret-token-value" not in snapshot.message
    assert "OrchestrationError" in snapshot.message


def test_frontend_exposes_mediated_controls_without_policy_inputs():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "app.js").read_text(encoding="utf-8")

    assert "Start through controller" in html
    assert "LIVE GOVERNED PROGRESS" in html
    assert "APPROVE_TASK" in html
    assert "APPROVE_IMPLEMENTATION" in html
    assert "X-AdvanCore-Action-Token" in script
    assert "EventSource" in script
    assert "/api/orchestration-jobs/current" in script
    assert "window.confirm" in script
    assert 'name="worker"' not in html
    assert 'name="branch"' not in html
    assert "subprocess" not in script
    assert "shell" not in script
