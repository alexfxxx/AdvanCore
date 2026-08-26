import pytest

from advancore.services.candidate_readiness_service import (
    CandidateCheckState,
    CandidateReadinessService,
    CandidateReadinessState,
)


def test_gemini_pre_auth_gate_is_explicit_and_fail_closed():
    summary = CandidateReadinessService().get_summary("gemini")
    assert summary.state == CandidateReadinessState.OWNER_SETUP_REQUIRED
    assert not summary.activation_allowed
    assert summary.accounts_probed == 0
    assert summary.processes_launched == 0
    checks = {check.key: check for check in summary.checks}
    assert checks["registry_boundary"].state == CandidateCheckState.PASS
    assert checks["provider_surface"].state == CandidateCheckState.OWNER_REQUIRED
    assert checks["authentication"].state == CandidateCheckState.OWNER_REQUIRED
    assert checks["usage_evidence"].state == CandidateCheckState.BLOCKED
    assert checks["activation_approval"].state == CandidateCheckState.BLOCKED


def test_subscription_is_not_inferred_as_api_entitlement_or_activation():
    rendered = repr(CandidateReadinessService().get_summary("gemini")).lower()
    assert "entitlement" in rendered
    assert "unverified" in rendered
    assert "activation_allowed=false" in rendered


@pytest.mark.parametrize("worker", ["kimi", "kimi-swarm", "codex", "dry-run"])
def test_approved_or_simulation_workers_are_not_candidate_setup(worker):
    with pytest.raises(ValueError, match="not a candidate"):
        CandidateReadinessService().get_summary(worker)


def test_readiness_service_never_probes_or_launches(monkeypatch):
    monkeypatch.setattr(
        "advancore.agent_runner.worker.subprocess.Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    summary = CandidateReadinessService().get_summary("gemini")
    assert summary.accounts_probed == summary.processes_launched == 0
