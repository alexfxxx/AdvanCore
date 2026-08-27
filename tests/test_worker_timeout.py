"""Deterministic coverage for bounded worker termination and recovery."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from unittest.mock import patch

from advancore.agent_runner.auto_pipeline import ProviderFailure, classify_provider_failure
from advancore.agent_runner.worker import (
    CodexWorkerAdapter,
    DEFAULT_WORKER_TIMEOUT_SECONDS,
    MAX_WORKER_TIMEOUT_SECONDS,
    WORKER_RECOVERY_ACTION,
    WorkerError,
    WorkerResult,
    KimiSwarmWorkerAdapter,
    KimiWorkerAdapter,
    parse_worker_timeout,
    run_bounded_worker_process,
    validate_worker_timeout,
)
from advancore.agent_runner.orchestration import OrchestrationConfig, _new_checkpoint


def _repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=path, check=True)
    return path


def _alive(pid: int) -> bool:
    try:
        state = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
            text=True, check=False,
        ).stdout.strip()
        return bool(state) and not state.startswith("Z")
    except Exception:
        return False


def test_timeout_policy_is_code_owned_and_strict() -> None:
    assert validate_worker_timeout(DEFAULT_WORKER_TIMEOUT_SECONDS) == 1800
    assert validate_worker_timeout(MAX_WORKER_TIMEOUT_SECONDS) == 7200
    assert parse_worker_timeout("1") == 1
    for value in (0, -1, MAX_WORKER_TIMEOUT_SECONDS + 1, 1.5, True, "1"):
        with pytest.raises(WorkerError):
            validate_worker_timeout(value)  # type: ignore[arg-type]
    for value in ("0", "-1", "+1", "01", "1.0", " 1", "7201", "abc"):
        with pytest.raises(WorkerError):
            parse_worker_timeout(value)


def test_timeout_kills_parent_and_child_without_transcript(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    pid_path = repo / "child.pid"
    script = (
        "import pathlib,signal,subprocess,sys,time;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "p=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)']);"
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid));"
        "print('SENSITIVE TRANSCRIPT',flush=True);time.sleep(60)"
    )
    result = run_bounded_worker_process(
        [sys.executable, "-c", script, str(pid_path)], repo, 1
    )
    child_pid = int(pid_path.read_text())
    deadline = time.monotonic() + 2
    while _alive(child_pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert result.terminal_reason == "timeout"
    assert result.stdout is None and result.stderr is None
    assert result.repository_state == {
        "unchanged": False,
        "ambiguous": False,
        "branch": result.repository_state["branch"],
        "head": result.repository_state["head"],
        "index_changed": False,
        "worktree_changed": True,
        "remotes_changed": False,
    }
    assert result.recovery_action is None
    assert not _alive(child_pid)


def test_clean_timeout_has_one_recovery_action(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = run_bounded_worker_process(
        [sys.executable, "-c", "import time;time.sleep(60)"], repo, 1
    )
    assert result.terminal_reason == "timeout"
    assert result.repository_state and result.repository_state["unchanged"] is True
    assert result.recovery_action == WORKER_RECOVERY_ACTION
    assert classify_provider_failure(result) == ProviderFailure.UNKNOWN


def test_keyboard_interrupt_cleans_group_and_returns_governed_result(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    timer = threading.Timer(0.2, lambda: os.kill(os.getpid(), signal.SIGINT))
    timer.start()
    try:
        result = run_bounded_worker_process(
            [sys.executable, "-c", "import time;time.sleep(60)"], repo, 30
        )
    finally:
        timer.cancel()
    assert result.terminal_reason == "cancelled"
    assert result.success is False
    assert result.recovery_action == WORKER_RECOVERY_ACTION


def test_terminal_result_cannot_be_availability_fallback() -> None:
    for reason in ("timeout", "cancelled"):
        result = WorkerResult(False, terminal_reason=reason, message=reason)
        assert classify_provider_failure(result) == ProviderFailure.UNKNOWN


def test_all_production_adapters_use_shared_runner(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    expected = WorkerResult(True)
    adapters = (
        KimiWorkerAdapter(executable=sys.executable),
        KimiSwarmWorkerAdapter(executable=sys.executable),
        CodexWorkerAdapter(),
    )
    with patch("advancore.agent_runner.worker.shutil.which", return_value=sys.executable), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process", return_value=expected
    ) as bounded:
        for adapter in adapters:
            assert adapter.run("instruction", repo) is expected
    assert bounded.call_count == 3


@pytest.mark.parametrize("adapter_type", [KimiWorkerAdapter, KimiSwarmWorkerAdapter])
def test_custom_kimi_executable_uses_portable_shared_runner(
    tmp_path: Path, adapter_type
) -> None:
    repo = _repo(tmp_path)
    expected = WorkerResult(True)
    adapter = adapter_type(executable=sys.executable, timeout_seconds=123)
    with patch(
        "advancore.agent_runner.worker._kimi_isolation_preflight",
        side_effect=AssertionError("custom executable must not require macOS isolation"),
    ), patch(
        "advancore.agent_runner.worker._isolate_kimi_command",
        side_effect=AssertionError("custom executable must not be sandbox-wrapped"),
    ), patch(
        "advancore.agent_runner.worker._kimi_environment",
        side_effect=AssertionError("custom executable must not receive Kimi environment"),
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process",
        return_value=expected,
    ) as bounded:
        assert adapter.run("instruction", repo) is expected
    bounded.assert_called_once()
    assert bounded.call_args.args[0][0] == sys.executable
    assert bounded.call_args.args[2] == 123
    assert len(bounded.call_args.args) == 3


def test_orchestration_checkpoint_persists_timeout_policy(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    config = OrchestrationConfig(goal="bounded goal", worker_timeout_seconds=321)
    checkpoint = _new_checkpoint(config, repo)
    assert checkpoint.worker_timeout_seconds == 321
    checkpoint.worker_terminal_reason = "timeout"
    checkpoint.worker_recovery_action = WORKER_RECOVERY_ACTION
    assert checkpoint.worker_terminal_reason == "timeout"
    assert checkpoint.worker_recovery_action == WORKER_RECOVERY_ACTION
