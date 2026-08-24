"""Worker-boundary tests for the Kimi weekly usage guardrail."""

from datetime import datetime, timedelta, timezone
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
        "advancore.agent_runner.worker.run_bounded_worker_process"
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result.success is False
    assert "quota/capacity paused" in result.message
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
        "advancore.agent_runner.worker.run_bounded_worker_process", return_value=expected
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result is expected
    assert bounded.call_args.args[2] == 100
    assert bounded.call_args.args[0][0] == "/usr/bin/sandbox-exec"
    assert str(service.protected_state_root) in bounded.call_args.args[0][2]
    assert service.get_summary().runtime_seconds == 3501


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
