from datetime import datetime, timedelta, timezone

from advancore.agent_runner.worker_registry import WorkerApprovalState
from advancore.services.worker_health_service import (
    WorkerHealthService,
    WorkerHealthState,
)
from advancore.services.worker_usage_service import UsageState, UsageSummary


class Usage:
    def __init__(self, summary=None, error=None):
        self.summary = summary
        self.error = error

    def get_summary(self, provider):
        assert provider == "kimi"
        if self.error:
            raise self.error
        return self.summary


def summary(state, checked=True):
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    return UsageSummary(
        provider="kimi",
        state=state,
        weekly_used_percent=12,
        weekly_percent_limit=20,
        runtime_seconds=120,
        runtime_limit_seconds=3600,
        checked_at=now if checked else None,
        reset_at=now + timedelta(days=4) if checked else None,
        source="owner-verified" if checked else None,
        message="bounded",
    )


def test_kimi_health_maps_only_validated_usage_states():
    for usage_state, expected in (
        (UsageState.AVAILABLE, WorkerHealthState.AVAILABLE),
        (UsageState.PAUSED, WorkerHealthState.PAUSED),
        (UsageState.UNAVAILABLE, WorkerHealthState.STALE),
    ):
        result = WorkerHealthService(Usage(summary(usage_state))).get_status(
            "kimi-swarm"
        )
        assert result.state == expected
        assert result.weekly_used_percent == 12
        assert result.runtime_seconds == 120


def test_missing_or_failed_kimi_evidence_is_unavailable():
    result = WorkerHealthService(Usage(error=RuntimeError("secret"))).get_status(
        "kimi-swarm"
    )
    assert result.state == WorkerHealthState.UNAVAILABLE
    assert result.weekly_used_percent is None


def test_codex_and_gemini_are_checked_at_launch_without_inferred_usage():
    service = WorkerHealthService(Usage(error=AssertionError("must not probe")))
    codex = service.get_status("codex")
    gemini = service.get_status("gemini")
    assert codex.state == WorkerHealthState.CHECKED_AT_LAUNCH
    assert codex.weekly_used_percent is None
    assert gemini.state == WorkerHealthState.CHECKED_AT_LAUNCH
    assert gemini.approval_state == WorkerApprovalState.APPROVED
    assert gemini.weekly_used_percent is None
