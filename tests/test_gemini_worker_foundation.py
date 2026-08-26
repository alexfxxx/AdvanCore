from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner import (
    APPROVED_PLANNER_NAMES,
    APPROVED_WORKER_NAMES,
    CANDIDATE_WORKER_NAMES,
    GeminiWorkerAdapter,
    WorkerError,
    WorkerResult,
    build_candidate_worker_adapter,
    build_worker_adapter,
)


def test_gemini_is_approved_for_implementation_but_not_planning():
    assert "gemini" in APPROVED_WORKER_NAMES
    assert "gemini" not in APPROVED_PLANNER_NAMES
    assert CANDIDATE_WORKER_NAMES == ()
    assert isinstance(build_worker_adapter("gemini"), GeminiWorkerAdapter)
    with pytest.raises(WorkerError, match="Unknown candidate"):
        build_candidate_worker_adapter("gemini")


def test_gemini_command_is_fixed_sandboxed_and_non_interactive(tmp_path):
    adapter = GeminiWorkerAdapter(timeout_seconds=600)

    command = adapter.build_command("bounded work", tmp_path)

    assert command == [
        "agy",
        "--print",
        "--mode",
        "accept-edits",
        "--sandbox",
        "--disable-slash-commands",
        "--output-format",
        "json",
        "--print-timeout",
        "600s",
        "--new-project",
        "bounded work",
    ]
    for forbidden in (
        "--dangerously-skip-permissions",
        "--model",
        "--agent",
        "--continue",
        "--conversation",
    ):
        assert forbidden not in command


def test_gemini_launch_uses_minimal_environment_and_scope(tmp_path, monkeypatch):
    for name in (
        "GITHUB_TOKEN",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "HTTPS_PROXY",
        "PYTHONPATH",
        "NODE_OPTIONS",
        "DYLD_INSERT_LIBRARIES",
    ):
        monkeypatch.setenv(name, "controller-secret")
    expected = WorkerResult(True, message="ok")
    adapter = GeminiWorkerAdapter(allowed_scope=["one.py"])
    with patch(
        "advancore.agent_runner.worker.shutil.which",
        return_value="/Users/example/.local/bin/agy",
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process",
        return_value=expected,
    ) as bounded:
        result = adapter.run("work", tmp_path)

    assert result is expected
    command = bounded.call_args.args[0]
    assert command[0] == "/Users/example/.local/bin/agy"
    assert command[-1].endswith("Allowed changed-file scope:\n- one.py")
    environment = bounded.call_args.kwargs["environment"]
    assert environment["HOME"]
    assert "advancore-gemini-" in environment["TMPDIR"]
    for name in (
        "GITHUB_TOKEN",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "HTTPS_PROXY",
        "PYTHONPATH",
        "NODE_OPTIONS",
        "DYLD_INSERT_LIBRARIES",
    ):
        assert name not in environment


def test_gemini_missing_executable_and_credential_input_fail_closed(tmp_path: Path):
    adapter = GeminiWorkerAdapter()
    with patch("advancore.agent_runner.worker.shutil.which", return_value=None):
        missing = adapter.run("bounded work", tmp_path)
    assert not missing.success
    assert missing.terminal_reason == "launch_failed"
    assert "not found in PATH" in missing.message

    blocked = adapter.run("OPENAI_API_KEY=definitely-real-secret-value", tmp_path)
    assert not blocked.success
    assert blocked.terminal_reason == "credential_access_required"
    assert "definitely" not in blocked.message
