"""Regression coverage for TASK-138 worker execution telemetry."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import patch

from advancore.agent_runner.audit import build_audit_payload
from advancore.agent_runner.auto_pipeline import (
    ProviderFailure,
    classify_provider_failure,
)
from advancore.agent_runner.worker import (
    EXECUTABLE_NOT_FOUND,
    RUNTIME_ERROR,
    SPAWN_ERROR,
    GeminiWorkerAdapter,
    KimiWorkerAdapter,
    WorkerResult,
    run_bounded_worker_process,
)


def test_missing_kimi_executable_has_explicit_preflight_classification(tmp_path):
    with patch(
        "advancore.agent_runner.worker._resolve_kimi_executable", return_value=None
    ):
        result = KimiWorkerAdapter().run("bounded work", tmp_path)

    assert result.success is False
    assert result.failure_classification == EXECUTABLE_NOT_FOUND
    assert result.terminal_reason == "launch_failed"
    assert result.executable_resolution == "unavailable"
    assert result.elapsed_seconds == 0.0
    assert classify_provider_failure(result) == ProviderFailure.EXECUTABLE_UNAVAILABLE


def test_spawn_exception_is_distinct_from_runtime_failure(tmp_path):
    result = run_bounded_worker_process(
        [str(tmp_path / "does-not-exist")], tmp_path, 5
    )

    assert result.success is False
    assert result.failure_classification == SPAWN_ERROR
    assert result.terminal_reason == "launch_failed"
    assert result.started_at is not None
    assert result.finished_at is not None
    assert result.elapsed_seconds is not None and result.elapsed_seconds >= 0


def test_runtime_failure_preserves_streams_in_memory_and_timing(tmp_path):
    result = run_bounded_worker_process(
        [
            sys.executable,
            "-c",
            "import sys; print('safe-out'); print('safe-err', file=sys.stderr); sys.exit(3)",
        ],
        tmp_path,
        5,
    )

    assert result.success is False
    assert result.returncode == 3
    assert result.stdout == "safe-out\n"
    assert result.stderr == "safe-err\n"
    assert result.failure_classification == RUNTIME_ERROR
    assert result.terminal_reason == "runtime_error"
    assert result.elapsed_seconds is not None and result.elapsed_seconds >= 0


def test_shell_style_executable_exit_is_spawn_error(tmp_path):
    result = run_bounded_worker_process(
        [sys.executable, "-c", "raise SystemExit(127)"], tmp_path, 5
    )

    assert result.returncode == 127
    assert result.failure_classification == SPAWN_ERROR
    assert result.terminal_reason == "launch_failed"


def test_gemini_command_uses_one_unambiguous_print_argument(tmp_path):
    instruction = "repair only target.py --mode must remain literal here"
    command = GeminiWorkerAdapter().build_command(instruction, tmp_path)

    print_arguments = [argument for argument in command if argument.startswith("--print=")]
    assert print_arguments == [f"--print={instruction}"]
    assert instruction not in command
    assert command[command.index("--mode") + 1] == "accept-edits"


def test_expired_launch_deadline_preserves_quota_classification(tmp_path):
    result = run_bounded_worker_process(
        [sys.executable, "-c", "raise AssertionError('must not launch')"],
        tmp_path,
        5,
        launch_deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert result.success is False
    assert result.terminal_reason == "quota_or_capacity"
    assert result.failure_classification == SPAWN_ERROR
    assert classify_provider_failure(result) == ProviderFailure.QUOTA_OR_CAPACITY


def test_audit_projects_only_bounded_worker_metadata():
    started = datetime(2026, 8, 28, 1, 2, 3, tzinfo=timezone.utc)
    finished = datetime(2026, 8, 28, 1, 2, 5, tzinfo=timezone.utc)
    payload = build_audit_payload(
        task_id="TASK-138",
        task_filename="TASK-138.md",
        mode="execute",
        worker_type="kimi-swarm",
        branch="task-138-worker-adapter-telemetry",
        pre_head="a" * 40,
        post_head="a" * 40,
        pre_validation_ok=True,
        worker_success=False,
        post_verification_ok=True,
        final_status="worker_failed",
        worker_started_at=started,
        worker_finished_at=finished,
        worker_elapsed_seconds=2.0,
        worker_returncode=3,
        worker_terminal_reason="runtime_error",
        worker_failure_classification=RUNTIME_ERROR,
        worker_resolved_executable="/Users/example/.kimi-code/bin/kimi",
        worker_executable_resolution="owner_home_fallback",
        worker_cli_version="0.38.0",
        worker_runtime_path_profile="kimi_minimal",
    )

    assert payload["worker_elapsed_seconds"] == 2.0
    assert payload["worker_failure_classification"] == RUNTIME_ERROR
    assert payload["worker_cli_version"] == "0.38.0"
    assert payload["worker_executable_resolution"] == "owner_home_fallback"
    for forbidden in ("command", "stdout", "stderr", "environment", "runtime_path"):
        assert forbidden not in payload


def test_adapter_annotation_keeps_full_prompt_out_of_audit_contract():
    result = WorkerResult(
        success=False,
        command=["agy", "--print=private owner goal"],
        stdout="private output",
        stderr="private failure",
        failure_classification=RUNTIME_ERROR,
    )

    assert "private owner goal" in result.command[1]
    # The audit builder accepts only explicit bounded metadata; WorkerResult is
    # never serialized wholesale.
    assert "worker_result" not in build_audit_payload(
        task_id="TASK-138",
        task_filename="TASK-138.md",
        mode="execute",
        worker_type="gemini",
        branch="feature",
        pre_head="a",
        post_head="a",
        pre_validation_ok=True,
        worker_success=False,
        post_verification_ok=True,
        final_status="worker_failed",
    )
