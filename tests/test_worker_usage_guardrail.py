"""Worker-boundary tests for the Kimi weekly usage guardrail."""

from datetime import datetime, timedelta, timezone
import json
import subprocess
from unittest.mock import patch

from advancore.agent_runner.auto_pipeline import (
    ProviderFailure,
    classify_provider_failure,
)
from advancore.agent_runner.worker import (
    CodexWorkerAdapter,
    KimiSwarmWorkerAdapter,
    KimiWorkerAdapter,
    WorkerResult,
    _isolate_kimi_command,
    _kimi_environment,
    run_bounded_worker_process,
)
from advancore.services.worker_usage_service import WorkerUsageService


def _usage_dir(tmp_path):
    return tmp_path.parent / f"{tmp_path.name}-controller" / "usage"


def _record(tmp_path, used=10):
    now = datetime.now(timezone.utc)
    service = WorkerUsageService(tmp_path, usage_dir=_usage_dir(tmp_path))
    service.record_snapshot(
        "kimi", used, now, now + timedelta(days=4), "owner-verified"
    )
    return service


def test_kimi_blocks_before_process_launch_at_policy_limit(tmp_path):
    service = _record(tmp_path, used=44)
    adapter = KimiWorkerAdapter()
    with patch(
        "advancore.services.worker_usage_service._default_usage_dir",
        return_value=service.usage_dir,
    ), patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=True
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process"
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result.success is False
    assert result.terminal_reason == "quota_or_capacity"
    assert classify_provider_failure(result) == ProviderFailure.QUOTA_OR_CAPACITY
    bounded.assert_not_called()


def test_kimi_swarm_blocks_when_usage_evidence_is_missing(tmp_path):
    usage_dir = _usage_dir(tmp_path)
    adapter = KimiSwarmWorkerAdapter()
    with patch(
        "advancore.services.worker_usage_service._default_usage_dir",
        return_value=usage_dir,
    ), patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=True
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process"
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result.success is False
    assert "quota/capacity paused" in result.message
    assert "automatic provider usage refresh is unavailable" in result.message
    bounded.assert_not_called()


def test_available_kimi_run_uses_remaining_timeout_and_records_runtime(tmp_path):
    service = _record(tmp_path)
    reset_at = service.get_summary().reset_at
    assert reset_at is not None
    reservation = service.preflight("kimi", 3500)
    service.record_runtime("kimi", 3500, reservation)
    adapter = KimiWorkerAdapter(timeout_seconds=600)
    expected = WorkerResult(True, message="ok")
    with patch(
        "advancore.services.worker_usage_service._default_usage_dir",
        return_value=service.usage_dir,
    ), patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=True
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process", return_value=expected
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result is expected
    assert bounded.call_args.args[2] == 100
    assert bounded.call_args.args[0][0] == "/usr/bin/sandbox-exec"
    assert str(service.protected_state_root) in bounded.call_args.args[0][2]
    assert bounded.call_args.args[0][3] == "/usr/bin/kimi"
    environment = bounded.call_args.args[4]
    assert environment["KIMI_CODE_HOME"].endswith("/.kimi-code")
    assert environment["KIMI_DISABLE_TELEMETRY"] == "1"
    assert "advancore-kimi-" in environment["TMPDIR"]
    assert service.get_summary().runtime_seconds == 3501


def test_kimi_sandbox_write_allowlist_excludes_executables_and_credentials(
    tmp_path, monkeypatch
):
    service = _record(tmp_path)
    scratch = tmp_path.parent / "reviewed-kimi-scratch"
    scratch.mkdir()

    command = _isolate_kimi_command(
        ["/Users/alex/.kimi-code/bin/kimi", "--prompt", "instruction"],
        service,
        tmp_path,
        scratch,
    )
    profile = command[2]

    assert "(require-not (require-any" in profile
    assert f'(subpath "{tmp_path.resolve()}")' in profile
    assert f'(subpath "{scratch.resolve()}")' in profile
    assert '(deny file-write* (subpath "/opt/homebrew"))' in profile
    assert '(deny file-write* (subpath "/usr/local"))' in profile
    assert '/.kimi-code/bin"))' in profile
    assert '/.kimi-code/credentials"))' in profile
    assert str(service.protected_state_root) in profile

    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-worker")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-worker")
    monkeypatch.setenv("DATABASE_URL", "must-not-reach-worker")
    monkeypatch.setenv("HTTPS_PROXY", "https://secret@example.invalid")
    monkeypatch.setenv("PYTHONPATH", "/controller/code")
    monkeypatch.setenv("NODE_OPTIONS", "--require=/controller/hook.js")
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "/controller/inject.dylib")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    environment = _kimi_environment(scratch)
    assert environment["TMPDIR"] == str(scratch)
    assert environment["XDG_CACHE_HOME"] == str(scratch / "cache")
    assert environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert environment["LANG"] == "en_US.UTF-8"
    assert "GITHUB_TOKEN" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert "DATABASE_URL" not in environment
    assert "HTTPS_PROXY" not in environment
    assert "PYTHONPATH" not in environment
    assert "NODE_OPTIONS" not in environment
    assert "DYLD_INSERT_LIBRARIES" not in environment


def test_kimi_automatically_refreshes_missing_usage_then_runs_as_primary(tmp_path):
    now = datetime.now(timezone.utc)
    usage_dir = _usage_dir(tmp_path)
    service = WorkerUsageService(tmp_path, usage_dir=usage_dir)
    probe = service.controller_probe_path("kimi")
    probe.parent.mkdir(parents=True)
    payload = json.dumps(
        {
            "schema_version": 1,
            "provider": "kimi",
            "weekly_used_percent": 5,
            "checked_at": now.isoformat(),
            "reset_at": (now + timedelta(days=4)).isoformat(),
        }
    )
    probe.write_text(f"#!/bin/sh\nprintf '%s\\n' '{payload}'\n", encoding="utf-8")
    probe.chmod(0o700)
    adapter = KimiWorkerAdapter()
    expected = WorkerResult(True, message="ok")

    with patch(
        "advancore.services.worker_usage_service._default_usage_dir",
        return_value=usage_dir,
    ), patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=True
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process", return_value=expected
    ) as bounded:
        result = adapter.run("instruction", tmp_path)

    assert result is expected
    bounded.assert_called_once()
    summary = service.get_summary()
    assert summary.state.value == "AVAILABLE"
    assert summary.weekly_used_percent == 5
    assert summary.source == "kimi-cli"


def test_invalid_probe_bytes_fail_closed_and_leave_codex_fallback_eligible(tmp_path):
    usage_dir = _usage_dir(tmp_path)
    service = WorkerUsageService(tmp_path, usage_dir=usage_dir)
    probe = service.controller_probe_path("kimi")
    probe.parent.mkdir(parents=True)
    probe.write_bytes(b"#!/bin/sh\nprintf '\\0377'\n")
    probe.chmod(0o700)
    adapter = KimiWorkerAdapter()

    with patch(
        "advancore.services.worker_usage_service._default_usage_dir",
        return_value=usage_dir,
    ), patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=True
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process"
    ) as bounded:
        result = adapter.run("instruction", tmp_path)

    assert result.success is False
    assert result.terminal_reason == "quota_or_capacity"
    assert classify_provider_failure(result) == ProviderFailure.QUOTA_OR_CAPACITY
    assert "automatic provider usage refresh is invalid" in result.message
    bounded.assert_not_called()


def test_kimi_blocks_before_reservation_without_os_isolation(tmp_path):
    service = _record(tmp_path)
    adapter = KimiWorkerAdapter()
    with patch(
        "advancore.services.worker_usage_service._default_usage_dir",
        return_value=service.usage_dir,
    ), patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=False
    ), patch("advancore.agent_runner.worker.run_bounded_worker_process") as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result.success is False
    assert result.terminal_reason == "quota_or_capacity"
    assert "OS isolation is unavailable" in result.message
    bounded.assert_not_called()
    assert service.get_summary().runtime_seconds == 0


def test_kimi_isolation_probe_requires_successful_sandbox_start():
    from advancore.agent_runner.worker import _kimi_isolation_available

    with patch("advancore.agent_runner.worker.Path.is_file", return_value=True), patch(
        "advancore.agent_runner.worker.subprocess.run",
        return_value=subprocess.CompletedProcess([], 71),
    ) as run:
        assert _kimi_isolation_available() is False
    assert run.call_args.args[0][-1] == "/usr/bin/true"

    with patch("advancore.agent_runner.worker.Path.is_file", return_value=True), patch(
        "advancore.agent_runner.worker.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0),
    ):
        assert _kimi_isolation_available() is True


def test_reset_deadline_is_rechecked_immediately_before_process_launch(tmp_path):
    with patch(
        "advancore.agent_runner.worker._git_evidence",
        return_value={"ambiguous": False},
    ), patch("advancore.agent_runner.worker.subprocess.Popen") as popen:
        result = run_bounded_worker_process(
            ["kimi", "--prompt", "instruction"],
            tmp_path,
            60,
            datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    assert result.success is False
    assert result.terminal_reason == "quota_or_capacity"
    assert "reset reached before launch" in result.message
    popen.assert_not_called()


def test_codex_does_not_depend_on_kimi_usage_evidence(tmp_path):
    adapter = CodexWorkerAdapter()
    expected = WorkerResult(True, message="ok")
    with patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/codex"), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process", return_value=expected
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result is expected
    bounded.assert_called_once()
