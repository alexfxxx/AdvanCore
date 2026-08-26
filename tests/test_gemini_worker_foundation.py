from pathlib import Path

import pytest

from advancore.agent_runner import (
    APPROVED_PLANNER_NAMES,
    APPROVED_WORKER_NAMES,
    CANDIDATE_WORKER_NAMES,
    GeminiCandidateWorkerAdapter,
    WorkerError,
    build_candidate_worker_adapter,
    build_worker_adapter,
)


def test_gemini_is_candidate_not_approved_worker_or_planner():
    assert CANDIDATE_WORKER_NAMES == ("gemini",)
    assert "gemini" not in APPROVED_WORKER_NAMES
    assert "gemini" not in APPROVED_PLANNER_NAMES
    with pytest.raises(WorkerError, match="Unknown worker"):
        build_worker_adapter("gemini")


def test_candidate_builder_is_fixed_and_rejects_unknown_names():
    adapter = build_candidate_worker_adapter("gemini")
    assert isinstance(adapter, GeminiCandidateWorkerAdapter)
    assert adapter.name == "gemini"
    with pytest.raises(WorkerError, match="Unknown candidate"):
        build_candidate_worker_adapter("caller-command --unsafe")


def test_candidate_builds_no_command_and_launches_no_process(tmp_path, monkeypatch):
    launched = False

    def launch(*_args, **_kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("candidate must never launch")

    monkeypatch.setattr("advancore.agent_runner.worker.subprocess.Popen", launch)
    adapter = build_candidate_worker_adapter("gemini")
    with pytest.raises(WorkerError, match="not activated"):
        adapter.build_command("work", tmp_path)
    result = adapter.run("bounded work", tmp_path)
    assert not result.success
    assert result.terminal_reason == "owner_action_required"
    assert "owner" in result.message.lower()
    assert not launched


def test_candidate_blocks_credential_material_before_owner_action(tmp_path: Path):
    result = build_candidate_worker_adapter("gemini").run(
        "OPENAI_API_KEY=definitely-real-secret-value", tmp_path
    )
    assert not result.success
    assert result.terminal_reason == "credential_access_required"
    assert "definitely" not in result.message
