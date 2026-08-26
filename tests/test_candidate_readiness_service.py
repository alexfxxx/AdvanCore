import pytest

from advancore.services.candidate_readiness_service import (
    CandidateCheckState,
    CandidateReadinessService,
    CandidateReadinessState,
)


def test_gemini_activation_summary_records_completed_owner_gates():
    summary = CandidateReadinessService().get_summary("gemini")

    assert summary.state == CandidateReadinessState.ACTIVATED
    assert summary.activation_allowed
    assert summary.accounts_probed == 0
    assert summary.processes_launched == 0
    assert all(check.state == CandidateCheckState.PASS for check in summary.checks)
    checks = {check.key: check for check in summary.checks}
    assert "Antigravity CLI" in checks["provider_surface"].message
    assert "authentication" in checks["authentication"].message
    assert "Kimi, Gemini, then Codex" in summary.next_owner_action


def test_activation_does_not_infer_subscription_balance_or_api_billing():
    rendered = repr(CandidateReadinessService().get_summary("gemini")).lower()

    assert "api key" not in rendered
    assert "billing" not in rendered
    assert "remaining" not in rendered


@pytest.mark.parametrize("worker", ["kimi", "kimi-swarm", "codex", "dry-run"])
def test_other_approved_or_simulation_workers_are_not_candidate_setup(worker):
    with pytest.raises(ValueError, match="not a candidate"):
        CandidateReadinessService().get_summary(worker)


def test_readiness_service_never_probes_or_launches(monkeypatch):
    monkeypatch.setattr(
        "advancore.agent_runner.worker.subprocess.Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not launch")
        ),
    )
    summary = CandidateReadinessService().get_summary("gemini")
    assert summary.accounts_probed == summary.processes_launched == 0
