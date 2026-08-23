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
)
from advancore.services.worker_usage_service import WorkerUsageService


def _record(tmp_path, used=10):
    now = datetime.now(timezone.utc)
    service = WorkerUsageService(tmp_path)
    service.record_snapshot(
        "kimi", used, now, now + timedelta(days=4), "owner-verified"
    )
    return service


def test_kimi_blocks_before_process_launch_at_policy_limit(tmp_path):
    _record(tmp_path, used=44)
    adapter = KimiWorkerAdapter()
    with patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process"
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result.success is False
    assert result.terminal_reason == "quota_or_capacity"
    assert classify_provider_failure(result) == ProviderFailure.QUOTA_OR_CAPACITY
    bounded.assert_not_called()


def test_kimi_swarm_blocks_when_usage_evidence_is_missing(tmp_path):
    adapter = KimiSwarmWorkerAdapter()
    with patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
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
    with patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process", return_value=expected
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result is expected
    assert bounded.call_args.args[2] == 100
    assert service.get_summary().runtime_seconds == 3501


def test_codex_does_not_depend_on_kimi_usage_evidence(tmp_path):
    adapter = CodexWorkerAdapter()
    expected = WorkerResult(True, message="ok")
    with patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/codex"), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process", return_value=expected
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result is expected
    bounded.assert_called_once()
