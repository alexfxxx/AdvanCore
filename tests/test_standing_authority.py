"""Tests for bounded routine standing authority (TASK-045)."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from advancore.agent_runner.standing_authority import (
    RoutineAction,
    StandingAuthorityError,
    StandingAuthorityService,
)


NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


def _service(tmp_path, now=NOW):
    repo = tmp_path / "repo"
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "fixture"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/example/advancore.git"],
            cwd=repo,
            check=True,
        )
    return StandingAuthorityService(
        repo, tmp_path / "controller-authority", lambda: now
    )


def _record(service, **overrides):
    values = {
        "task_ids": [f"TASK-{number:03d}" for number in range(45, 55)],
        "branch": "unattended-controller-orchestration",
        "allowed_actions": list(RoutineAction),
        "expires_at": NOW + timedelta(hours=3),
        "max_uses": 100,
        "owner_confirmed": True,
    }
    values.update(overrides)
    return service.record(**values)


def test_exact_routine_grant_is_recorded_outside_worker_content(tmp_path):
    service = _service(tmp_path)
    authority = _record(service)

    assert authority.uses == 0
    assert len(authority.task_ids) == 10
    assert service.authority_path.stat().st_mode & 0o077 == 0
    text = service.authority_path.read_text(encoding="utf-8").lower()
    for prohibited in ("token", "password", "prompt", "transcript", "environment"):
        assert prohibited not in text


def test_routine_action_is_atomically_consumed(tmp_path):
    service = _service(tmp_path)
    _record(service)

    updated = service.consume(
        "TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS
    )

    assert updated.uses == 1
    assert json.loads(service.authority_path.read_text())["uses"] == 1


@pytest.mark.parametrize(
    ("task_id", "branch", "action"),
    [
        ("TASK-999", "unattended-controller-orchestration", RoutineAction.RUN_TESTS),
        ("TASK-045", "main", RoutineAction.RUN_TESTS),
        ("TASK-045", "unattended-controller-orchestration", "approve-implementation"),
        ("TASK-045", "unattended-controller-orchestration", "credential-access"),
        ("TASK-045", "unattended-controller-orchestration", "deploy"),
    ],
)
def test_wrong_scope_and_prohibited_authority_fail_closed(tmp_path, task_id, branch, action):
    service = _service(tmp_path)
    _record(service)

    with pytest.raises(StandingAuthorityError):
        service.consume(task_id, branch, action)


def test_expired_exhausted_and_unconfirmed_grants_fail_closed(tmp_path):
    with pytest.raises(StandingAuthorityError, match="confirmation"):
        _record(_service(tmp_path), owner_confirmed=False)

    service = _service(tmp_path)
    _record(service, max_uses=1)
    service.consume("TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS)
    with pytest.raises(StandingAuthorityError, match="exhausted"):
        service.consume("TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS)

    expired = _service(tmp_path / "expired", now=NOW + timedelta(hours=4))
    writer = StandingAuthorityService(expired.repo_root, expired.state_dir, lambda: NOW)
    _record(writer)
    with pytest.raises(StandingAuthorityError, match="expired"):
        expired.consume("TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS)


def test_unsafe_or_malformed_authority_fails_closed(tmp_path):
    service = _service(tmp_path)
    _record(service)
    os.chmod(service.authority_path, 0o644)
    with pytest.raises(StandingAuthorityError, match="unsafe"):
        service.consume("TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS)

    os.chmod(service.authority_path, 0o600)
    service.authority_path.write_text("[" * 1100 + "]" * 1100, encoding="utf-8")
    with pytest.raises(StandingAuthorityError, match="invalid"):
        service.consume("TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS)


def test_same_names_and_remote_in_another_clone_cannot_consume_grant(tmp_path):
    first = _service(tmp_path / "first")
    _record(first)
    second = _service(tmp_path / "second")
    second.state_dir = first.state_dir

    with pytest.raises(StandingAuthorityError, match="repository"):
        second.consume(
            "TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("branch", 7),
        ("task_ids", ["TASK-045", 7]),
        ("allowed_actions", [["run-tests"]]),
        ("max_uses", "100"),
        ("uses", False),
    ],
)
def test_malformed_field_types_are_normalized(tmp_path, field, value):
    service = _service(tmp_path)
    _record(service)
    payload = json.loads(service.authority_path.read_text(encoding="utf-8"))
    payload[field] = value
    service.authority_path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(service.authority_path, 0o600)

    with pytest.raises(StandingAuthorityError, match="invalid"):
        service.consume(
            "TASK-045", "unattended-controller-orchestration", RoutineAction.RUN_TESTS
        )
