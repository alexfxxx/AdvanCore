"""Tests for the bounded worker operations timeline."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from advancore.services.worker_operations_service import (
    WorkerOperationEvent,
    WorkerOperationsError,
    WorkerOperationsService,
)


NOW = datetime(2026, 8, 28, 2, tzinfo=timezone.utc)


def _service(tmp_path: Path) -> tuple[WorkerOperationsService, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    path = tmp_path / "controller" / "events.jsonl"
    return WorkerOperationsService(repo, path), path


def _event(task_id: str = "TASK-139", worker: str = "kimi-swarm"):
    return WorkerOperationEvent(
        occurred_at=NOW,
        task_id=task_id,
        worker=worker,
        success=False,
        started_at=NOW - timedelta(seconds=2),
        finished_at=NOW,
        elapsed_seconds=2.0,
        returncode=1,
        terminal_reason="runtime_error",
        failure_classification="RUNTIME_ERROR",
        executable_resolution="owner_home_fallback",
        runtime_path_profile="kimi_minimal",
    )


def test_record_read_permissions_and_safe_shape(tmp_path):
    service, path = _service(tmp_path)
    service.record(_event(), now=NOW)
    assert service.list_events(now=NOW) == [_event()]
    assert path.stat().st_mode & 0o077 == 0
    assert path.parent.stat().st_mode & 0o077 == 0
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {
        "elapsed_seconds", "executable_resolution", "failure_classification",
        "finished_at", "occurred_at", "returncode", "runtime_path_profile",
        "started_at", "success", "task_id", "terminal_reason", "worker",
    }
    for forbidden in ("prompt", "command", "stdout", "stderr", "environment", "path"):
        assert forbidden not in raw


def test_compacts_old_malformed_and_future_records(tmp_path):
    service, path = _service(tmp_path)
    path.parent.mkdir(mode=0o700)
    payload = service._payload(_event())
    old = dict(payload, occurred_at=(NOW - timedelta(days=8)).isoformat())
    future = dict(payload, occurred_at=(NOW + timedelta(hours=1)).isoformat())
    path.write_text(
        json.dumps(old) + "\nnot-json\n" + json.dumps(future) + "\n" + json.dumps(payload) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    assert service.list_events(now=NOW) == [_event()]


@pytest.mark.parametrize(
    "event",
    [
        _event("task-139"),
        _event("TASK-139", "shell"),
        WorkerOperationEvent(NOW, "TASK-139", "kimi", True, elapsed_seconds=-1),
        WorkerOperationEvent(NOW, "TASK-139", "kimi", True, terminal_reason="bad value"),
        WorkerOperationEvent(NOW + timedelta(hours=1), "TASK-139", "kimi", True),
    ],
)
def test_invalid_events_fail_closed(tmp_path, event):
    service, _ = _service(tmp_path)
    with pytest.raises(WorkerOperationsError):
        service.record(event, now=NOW)


def test_rejects_in_workspace_symlink_oversized_and_open_permissions(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(WorkerOperationsError):
        WorkerOperationsService(repo, repo / "events.jsonl")

    service, path = _service(tmp_path / "safe")
    path.parent.mkdir(mode=0o700)
    path.write_text("x" * (513 * 1024), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(WorkerOperationsError):
        service.list_events(now=NOW)

    path.write_text("", encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(WorkerOperationsError):
        service.list_events(now=NOW)
