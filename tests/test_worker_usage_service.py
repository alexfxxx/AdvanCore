"""Deterministic tests for local worker usage evidence and policy."""

from datetime import datetime, timedelta, timezone

import pytest

from advancore.services.worker_usage_service import (
    KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS,
    UsageBudgetError,
    UsageState,
    WorkerUsageService,
)


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
RESET = NOW + timedelta(days=4)


def _service(tmp_path, now=NOW):
    return WorkerUsageService(tmp_path, now_provider=lambda: now)


def _record(service, used=10.0, checked=NOW, reset=RESET):
    return service.record_snapshot(
        "kimi", used, checked, reset, "owner-verified"
    )


def test_valid_snapshot_is_available_and_contains_no_vendor_content(tmp_path):
    service = _service(tmp_path)
    _record(service)
    summary = service.get_summary("kimi")
    assert summary.state == UsageState.AVAILABLE
    assert summary.weekly_used_percent == 10
    assert summary.weekly_percent_limit == 20
    assert summary.runtime_seconds == 0
    assert summary.runtime_limit_seconds == 3600
    assert set(service.snapshot_path("kimi").read_text().split('"')) >= {
        "provider", "weekly_used_percent", "checked_at", "reset_at", "source"
    }
    for prohibited in ("token", "password", "prompt", "transcript"):
        assert prohibited not in service.snapshot_path("kimi").read_text().lower()


@pytest.mark.parametrize("used", [20, 44, 100])
def test_at_or_over_twenty_percent_is_paused(tmp_path, used):
    service = _service(tmp_path)
    _record(service, used=used)
    summary = service.get_summary("kimi")
    assert summary.state == UsageState.PAUSED
    with pytest.raises(UsageBudgetError, match="quota/capacity paused"):
        service.preflight("kimi", 1800)


def test_missing_malformed_and_stale_evidence_fail_closed(tmp_path):
    service = _service(tmp_path)
    assert service.get_summary().state == UsageState.UNAVAILABLE
    _record(service)
    service.snapshot_path("kimi").write_text("{not-json", encoding="utf-8")
    assert service.get_summary().state == UsageState.UNAVAILABLE

    fresh = _service(tmp_path)
    _record(fresh)
    stale = _service(tmp_path, NOW + timedelta(minutes=16))
    stale_summary = stale.get_summary()
    assert stale_summary.state == UsageState.UNAVAILABLE
    assert stale_summary.weekly_used_percent == 10
    assert stale_summary.checked_at == NOW
    with pytest.raises(UsageBudgetError, match="quota/capacity paused"):
        stale.preflight("kimi", 60)


def test_malformed_existing_runtime_cannot_be_reset_by_new_snapshot(tmp_path):
    service = _service(tmp_path)
    _record(service)
    service.runtime_path("kimi").write_text("{not-json", encoding="utf-8")
    with pytest.raises(UsageBudgetError, match="evidence is invalid"):
        _record(service, used=11)


def test_future_and_reset_expired_snapshots_are_rejected(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(UsageBudgetError, match="future-dated"):
        _record(service, checked=NOW + timedelta(minutes=1))
    with pytest.raises(UsageBudgetError, match="reset window"):
        _record(service, reset=NOW)


def test_runtime_is_recorded_and_timeout_is_clamped_to_remaining_budget(tmp_path):
    service = _service(tmp_path)
    _record(service)
    service.record_runtime("kimi", 3499.2, RESET)
    preflight = service.preflight("kimi", 600)
    assert preflight.allowed_timeout_seconds == 100
    service.record_runtime("kimi", 100, RESET)
    assert service.get_summary().runtime_seconds == KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS
    with pytest.raises(UsageBudgetError, match="runtime limit reached"):
        service.preflight("kimi", 60)


def test_new_provider_period_resets_local_runtime(tmp_path):
    service = _service(tmp_path)
    _record(service)
    service.record_runtime("kimi", 300, RESET)
    next_now = RESET + timedelta(minutes=1)
    next_reset = next_now + timedelta(days=7)
    next_service = _service(tmp_path, next_now)
    next_service.record_snapshot(
        "kimi", 1, next_now, next_reset, "kimi-cli"
    )
    assert next_service.get_summary().runtime_seconds == 0


def test_period_change_during_worker_run_fails_accounting(tmp_path):
    service = _service(tmp_path)
    _record(service)
    next_now = RESET + timedelta(minutes=1)
    next_service = _service(tmp_path, next_now)
    next_service.record_snapshot(
        "kimi", 1, next_now, next_now + timedelta(days=7), "kimi-cli"
    )
    with pytest.raises(UsageBudgetError, match="period changed"):
        next_service.record_runtime("kimi", 1, RESET)
