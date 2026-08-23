"""Deterministic tests for controller-owned usage evidence and policy."""

import json
import math
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
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return WorkerUsageService(
        repo,
        now_provider=lambda: now,
        usage_dir=tmp_path / "controller-state" / "usage",
    )


def _record(service, used=10.0, checked=NOW, reset=RESET):
    return service.record_snapshot(
        "kimi", used, checked, reset, "owner-verified"
    )


def _charge(service, seconds):
    preflight = service.preflight("kimi", math.ceil(seconds))
    return service.record_runtime("kimi", seconds, preflight)


def test_valid_snapshot_is_available_and_outside_worker_workspace(tmp_path):
    service = _service(tmp_path)
    _record(service)
    summary = service.get_summary("kimi")
    assert summary.state == UsageState.AVAILABLE
    assert summary.weekly_used_percent == 10
    assert summary.weekly_percent_limit == 20
    assert summary.runtime_seconds == 0
    assert summary.runtime_limit_seconds == 3600
    assert service.repo_root not in service.snapshot_path("kimi").parents
    assert not (service.repo_root / ".agent_runner" / "usage").exists()
    assert set(service.snapshot_path("kimi").read_text().split('"')) >= {
        "provider", "period_id", "weekly_used_percent", "checked_at", "reset_at", "source"
    }
    for prohibited in ("token", "password", "prompt", "transcript"):
        assert prohibited not in service.snapshot_path("kimi").read_text().lower()


def test_usage_directory_inside_worker_workspace_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(UsageBudgetError, match="outside the worker workspace"):
        WorkerUsageService(repo, usage_dir=repo / ".agent_runner" / "usage")


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

    fresh = _service(tmp_path / "fresh")
    _record(fresh)
    stale = WorkerUsageService(
        fresh.repo_root,
        now_provider=lambda: NOW + timedelta(minutes=16),
        usage_dir=fresh.usage_dir,
    )
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


def test_runtime_is_reserved_then_reconciled_and_timeout_is_clamped(tmp_path):
    service = _service(tmp_path)
    _record(service)
    _charge(service, 3499.2)
    preflight = service.preflight("kimi", 600)
    assert preflight.allowed_timeout_seconds == 100
    reserved = json.loads(service.runtime_path("kimi").read_text())
    assert reserved["runtime_seconds"] == KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS
    service.record_runtime("kimi", 100, preflight)
    assert service.get_summary().runtime_seconds == KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS
    with pytest.raises(UsageBudgetError, match="runtime limit reached"):
        service.preflight("kimi", 60)


def test_concurrent_preflight_is_blocked_while_reservation_is_active(tmp_path):
    service = _service(tmp_path)
    _record(service)
    competing = WorkerUsageService(
        service.repo_root, now_provider=lambda: NOW, usage_dir=service.usage_dir
    )
    preflight = service.preflight("kimi", 1800)
    with pytest.raises(UsageBudgetError, match="accounting is busy"):
        competing.preflight("kimi", 1800)
    assert json.loads(service.runtime_path("kimi").read_text())["runtime_seconds"] == 1800
    service.record_runtime("kimi", 10, preflight)
    assert competing.get_summary().runtime_seconds == 10


def test_abandoned_worker_keeps_full_reservation_fail_closed(tmp_path):
    service = _service(tmp_path)
    _record(service)
    preflight = service.preflight("kimi", 1800)
    service.abandon_reservation(preflight)
    assert service.get_summary().runtime_seconds == 1800


def test_valid_long_run_can_settle_after_snapshot_freshness_window(tmp_path):
    clock = [NOW]
    repo = tmp_path / "repo"
    repo.mkdir()
    service = WorkerUsageService(
        repo,
        now_provider=lambda: clock[0],
        usage_dir=tmp_path / "controller-state" / "usage",
    )
    _record(service)
    preflight = service.preflight("kimi", 1800)
    clock[0] = NOW + timedelta(minutes=16)
    ledger = service.record_runtime("kimi", 960, preflight)
    assert ledger.runtime_seconds == 960
    assert not service.quarantine_path("kimi").exists()


def test_small_reset_adjustment_preserves_period_and_runtime(tmp_path):
    service = _service(tmp_path)
    first = _record(service)
    _charge(service, 300)
    refreshed_service = WorkerUsageService(
        service.repo_root,
        now_provider=lambda: NOW + timedelta(minutes=1),
        usage_dir=service.usage_dir,
    )
    refreshed = _record(
        refreshed_service,
        used=11,
        checked=NOW + timedelta(minutes=1),
        reset=RESET + timedelta(seconds=1),
    )
    assert refreshed.period_id == first.period_id
    assert refreshed_service.get_summary().runtime_seconds == 300


def test_usage_cannot_decrease_inside_same_provider_period(tmp_path):
    service = _service(tmp_path)
    _record(service, used=12)
    refreshed_service = WorkerUsageService(
        service.repo_root,
        now_provider=lambda: NOW + timedelta(minutes=1),
        usage_dir=service.usage_dir,
    )
    with pytest.raises(UsageBudgetError, match="cannot decrease"):
        _record(refreshed_service, used=11, checked=NOW + timedelta(minutes=1))


def test_verified_new_provider_period_resets_local_runtime(tmp_path):
    service = _service(tmp_path)
    first = _record(service)
    _charge(service, 300)
    next_now = RESET + timedelta(minutes=1)
    next_reset = next_now + timedelta(days=7)
    next_service = WorkerUsageService(
        service.repo_root,
        now_provider=lambda: next_now,
        usage_dir=service.usage_dir,
    )
    second = next_service.record_snapshot(
        "kimi", 1, next_now, next_reset, "kimi-cli"
    )
    assert second.period_id != first.period_id
    assert next_service.get_summary().runtime_seconds == 0


def test_evidence_change_during_worker_run_quarantines_future_launches(tmp_path):
    service = _service(tmp_path)
    _record(service)
    preflight = service.preflight("kimi", 60)
    payload = json.loads(service.snapshot_path("kimi").read_text())
    payload["weekly_used_percent"] = 0
    service.snapshot_path("kimi").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(UsageBudgetError, match="changed during worker"):
        service.record_runtime("kimi", 1, preflight)
    assert service.quarantine_path("kimi").exists()
    assert service.get_summary().state == UsageState.UNAVAILABLE
    with pytest.raises(UsageBudgetError, match="quarantined"):
        service.preflight("kimi", 60)
