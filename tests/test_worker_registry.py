from dataclasses import FrozenInstanceError

import pytest

from advancore.agent_runner.worker import WorkerError
from advancore.agent_runner.worker_registry import (
    WorkerApprovalState,
    WorkerRole,
    eligible_workers,
    get_worker_profile,
    validate_worker_registry,
    worker_profiles,
)


def test_registry_matches_fixed_worker_identities_and_validates():
    validate_worker_registry()
    assert [profile.name for profile in worker_profiles()] == [
        "dry-run", "kimi", "kimi-swarm", "codex", "gemini"
    ]


def test_gemini_is_owner_approved_for_implementation_and_fallback_only():
    gemini = get_worker_profile("gemini")
    assert gemini.approval_state == WorkerApprovalState.APPROVED
    assert gemini.launchable
    assert not gemini.requires_owner_setup
    assert not gemini.requires_fresh_usage_evidence
    assert gemini.authorised_roles == (
        WorkerRole.IMPLEMENTATION,
        WorkerRole.FALLBACK,
    )


def test_dry_run_is_simulation_only_and_never_implementation_eligible():
    dry_run = get_worker_profile("dry-run")
    assert dry_run.approval_state == WorkerApprovalState.SIMULATION_ONLY
    assert not dry_run.launchable
    assert dry_run not in eligible_workers(WorkerRole.IMPLEMENTATION)


def test_approved_roles_are_bounded_and_deterministic():
    assert [item.name for item in eligible_workers("implementation")] == [
        "kimi", "kimi-swarm", "codex", "gemini"
    ]
    assert [item.name for item in eligible_workers("review")] == ["kimi-swarm"]
    assert [item.name for item in eligible_workers("fallback")] == ["codex", "gemini"]


def test_unknown_name_and_role_fail_closed():
    with pytest.raises(WorkerError, match="Unknown worker profile"):
        get_worker_profile("user-command")
    with pytest.raises(WorkerError, match="Unknown worker role"):
        eligible_workers("superuser")


def test_profiles_are_frozen_and_callers_receive_an_immutable_tuple():
    profiles = worker_profiles()
    with pytest.raises(FrozenInstanceError):
        profiles[0].launchable = True
    with pytest.raises(TypeError):
        profiles[0] = profiles[-1]
