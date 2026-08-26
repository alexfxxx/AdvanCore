"""Deterministic tests for truthful multi-provider usage display evidence."""

from datetime import datetime, timedelta, timezone
import json
import stat

import pytest

from advancore.services.ai_usage_dashboard_service import (
    AiUsageDashboardService,
    AiUsageEvidenceError,
    BalanceState,
    ProviderUsageObservationStore,
)
from advancore.services.worker_usage_service import UsageState, UsageSummary


NOW = datetime(2026, 8, 26, 13, 0, tzinfo=timezone.utc)


class Usage:
    def __init__(self, summary):
        self.summary = summary

    def get_summary(self, provider):
        assert provider == "kimi"
        return self.summary


def kimi_summary(state=UsageState.AVAILABLE, used=12.0):
    return UsageSummary(
        provider="kimi",
        state=state,
        weekly_used_percent=used,
        weekly_percent_limit=20.0,
        runtime_seconds=600,
        runtime_limit_seconds=3600,
        checked_at=NOW,
        reset_at=NOW + timedelta(days=4),
        source="owner-verified",
        message="usage budget available",
    )


def store(tmp_path, now=NOW):
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo, ProviderUsageObservationStore(
        repo,
        tmp_path / "controller-state" / "provider-usage",
        now_provider=lambda: now,
    )


def test_cards_separate_real_balance_observation_and_unavailable(tmp_path):
    repo, observations = store(tmp_path)
    observations.record(
        "gemini",
        observed_at=NOW,
        source="antigravity-cli-json",
        last_run_tokens=31_142,
    )

    cards = AiUsageDashboardService(
        Usage(kimi_summary()), observations, now_provider=lambda: NOW
    ).get_cards()

    kimi, codex, gemini = cards
    assert kimi.balance_state == BalanceState.CURRENT
    assert kimi.weekly_used_percent == 12
    assert kimi.remaining_percent == 88
    assert kimi.automation_remaining_percent == 8
    assert kimi.runtime_seconds == 600
    assert codex.balance_state == BalanceState.UNAVAILABLE
    assert codex.remaining_percent is None
    assert gemini.balance_state == BalanceState.OBSERVED_ONLY
    assert gemini.last_run_tokens == 31_142
    assert gemini.remaining_percent is None
    assert gemini.authentication_verified
    assert "exact balance is unavailable" in gemini.message
    assert repo not in observations.path("gemini").parents


def test_owner_verified_percentage_produces_a_current_balance(tmp_path):
    _, observations = store(tmp_path)
    observations.record(
        "codex",
        observed_at=NOW,
        source="codex-approved-export",
        weekly_used_percent=25,
        reset_at=NOW + timedelta(days=5),
    )

    codex = AiUsageDashboardService(
        Usage(kimi_summary()), observations, now_provider=lambda: NOW
    ).get_cards()[1]

    assert codex.balance_state == BalanceState.CURRENT
    assert codex.weekly_used_percent == 25
    assert codex.remaining_percent == 75


def test_observation_receipt_is_strict_owner_only_and_non_secret(tmp_path):
    _, observations = store(tmp_path)
    observations.record(
        "gemini",
        observed_at=NOW,
        source="antigravity-cli-json",
        last_run_tokens=31_142,
    )
    path = observations.path("gemini")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload) == {
        "authentication_verified",
        "last_run_tokens",
        "observed_at",
        "provider",
        "reset_at",
        "schema_version",
        "source",
        "weekly_used_percent",
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    "changes",
    [
        {"unexpected": True},
        {"authentication_verified": False},
        {"last_run_tokens": -1},
        {"weekly_used_percent": 50},
        {"observed_at": "not-a-time"},
    ],
)
def test_malformed_or_incomplete_observation_fails_closed(tmp_path, changes):
    _, observations = store(tmp_path)
    observations.record(
        "gemini",
        observed_at=NOW,
        source="antigravity-cli-json",
        last_run_tokens=100,
    )
    path = observations.path("gemini")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(changes)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AiUsageEvidenceError):
        observations.load("gemini")

    gemini = AiUsageDashboardService(
        Usage(kimi_summary()), observations, now_provider=lambda: NOW
    ).get_cards()[2]
    assert gemini.balance_state == BalanceState.UNAVAILABLE
    assert gemini.remaining_percent is None


def test_old_observation_is_labelled_stale_without_losing_history(tmp_path):
    observed = NOW - timedelta(days=2)
    _, observations = store(tmp_path, now=NOW)
    observations.record(
        "gemini",
        observed_at=observed,
        source="antigravity-cli-json",
        last_run_tokens=500,
    )

    gemini = AiUsageDashboardService(
        Usage(kimi_summary()), observations, now_provider=lambda: NOW
    ).get_cards()[2]

    assert gemini.balance_state == BalanceState.STALE
    assert gemini.last_run_tokens == 500


def test_evidence_inside_worker_workspace_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(AiUsageEvidenceError, match="outside"):
        ProviderUsageObservationStore(repo, repo / "state")


def test_symlinked_or_readable_evidence_location_fails_closed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = tmp_path / "real-state"
    target.mkdir()
    link = tmp_path / "linked-state"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(AiUsageEvidenceError, match="unsafe"):
        ProviderUsageObservationStore(repo, link)

    separate = tmp_path / "separate"
    separate.mkdir()
    _, observations = store(separate)
    observations.record(
        "gemini",
        observed_at=NOW,
        source="antigravity-cli-json",
        last_run_tokens=10,
    )
    observations.path("gemini").chmod(0o644)
    with pytest.raises(AiUsageEvidenceError, match="invalid"):
        observations.load("gemini")
