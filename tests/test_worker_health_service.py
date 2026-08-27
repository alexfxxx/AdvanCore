from advancore.agent_runner.worker_registry import WorkerApprovalState
from advancore.services.worker_health_service import (
    WorkerHealthService,
    WorkerHealthState,
)


class Usage:
    def get_summary(self, provider):
        raise AssertionError(f"health must not read legacy {provider} usage evidence")


def test_kimi_health_is_checked_at_launch_without_usage_evidence():
    result = WorkerHealthService(Usage()).get_status("kimi-swarm")
    assert result.state == WorkerHealthState.CHECKED_AT_LAUNCH
    assert result.weekly_used_percent is None
    assert result.weekly_percent_limit is None
    assert result.runtime_seconds is None
    assert result.runtime_limit_seconds is None
    assert result.checked_at is None
    assert result.reset_at is None


def test_codex_and_gemini_are_checked_at_launch_without_inferred_usage():
    service = WorkerHealthService(Usage())
    codex = service.get_status("codex")
    gemini = service.get_status("gemini")
    assert codex.state == WorkerHealthState.CHECKED_AT_LAUNCH
    assert codex.weekly_used_percent is None
    assert gemini.state == WorkerHealthState.CHECKED_AT_LAUNCH
    assert gemini.approval_state == WorkerApprovalState.APPROVED
    assert gemini.weekly_used_percent is None
