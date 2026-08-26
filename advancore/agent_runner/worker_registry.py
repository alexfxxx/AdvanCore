"""Immutable authority-aware registry for code-owned worker identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from advancore.agent_runner.worker import (
    APPROVED_PLANNER_NAMES,
    APPROVED_WORKER_NAMES,
    CANDIDATE_WORKER_NAMES,
    WorkerError,
)


class WorkerApprovalState(str, Enum):
    APPROVED = "APPROVED"
    CANDIDATE = "CANDIDATE"
    SIMULATION_ONLY = "SIMULATION_ONLY"


class WorkerRole(str, Enum):
    IMPLEMENTATION = "implementation"
    PLANNING = "planning"
    REVIEW = "review"
    FALLBACK = "fallback"
    SIMULATION = "simulation"


@dataclass(frozen=True)
class WorkerProfile:
    name: str
    label: str
    provider: str
    approval_state: WorkerApprovalState
    authorised_roles: tuple[WorkerRole, ...]
    launchable: bool
    requires_owner_setup: bool
    requires_fresh_usage_evidence: bool

    def is_eligible(self, role: WorkerRole) -> bool:
        return (
            self.approval_state == WorkerApprovalState.APPROVED
            and self.launchable
            and role in self.authorised_roles
        )


_PROFILES: Mapping[str, WorkerProfile] = MappingProxyType(
    {
        "dry-run": WorkerProfile(
            name="dry-run",
            label="Safe simulation",
            provider="local",
            approval_state=WorkerApprovalState.SIMULATION_ONLY,
            authorised_roles=(WorkerRole.SIMULATION,),
            launchable=False,
            requires_owner_setup=False,
            requires_fresh_usage_evidence=False,
        ),
        "kimi": WorkerProfile(
            name="kimi",
            label="Kimi",
            provider="kimi",
            approval_state=WorkerApprovalState.APPROVED,
            authorised_roles=(WorkerRole.IMPLEMENTATION, WorkerRole.PLANNING),
            launchable=True,
            requires_owner_setup=False,
            requires_fresh_usage_evidence=True,
        ),
        "kimi-swarm": WorkerProfile(
            name="kimi-swarm",
            label="Kimi / Kimi-Swarm",
            provider="kimi",
            approval_state=WorkerApprovalState.APPROVED,
            authorised_roles=(
                WorkerRole.IMPLEMENTATION,
                WorkerRole.PLANNING,
                WorkerRole.REVIEW,
            ),
            launchable=True,
            requires_owner_setup=False,
            requires_fresh_usage_evidence=True,
        ),
        "codex": WorkerProfile(
            name="codex",
            label="Codex",
            provider="openai",
            approval_state=WorkerApprovalState.APPROVED,
            authorised_roles=(
                WorkerRole.IMPLEMENTATION,
                WorkerRole.PLANNING,
                WorkerRole.FALLBACK,
            ),
            launchable=True,
            requires_owner_setup=False,
            requires_fresh_usage_evidence=False,
        ),
        "gemini": WorkerProfile(
            name="gemini",
            label="Gemini",
            provider="google",
            approval_state=WorkerApprovalState.APPROVED,
            authorised_roles=(WorkerRole.IMPLEMENTATION, WorkerRole.FALLBACK),
            launchable=True,
            requires_owner_setup=False,
            requires_fresh_usage_evidence=False,
        ),
    }
)


def worker_profiles() -> tuple[WorkerProfile, ...]:
    """Return profiles in deterministic display/routing order."""
    return tuple(_PROFILES.values())


def get_worker_profile(name: str) -> WorkerProfile:
    if not isinstance(name, str) or name not in _PROFILES:
        raise WorkerError(f"Unknown worker profile: {name!r}")
    return _PROFILES[name]


def eligible_workers(role: WorkerRole | str) -> tuple[WorkerProfile, ...]:
    try:
        resolved_role = role if isinstance(role, WorkerRole) else WorkerRole(role)
    except (TypeError, ValueError) as exc:
        raise WorkerError(f"Unknown worker role: {role!r}") from exc
    return tuple(profile for profile in _PROFILES.values() if profile.is_eligible(resolved_role))


def validate_worker_registry() -> None:
    """Fail closed if registry identities drift from code-owned adapter lists."""
    expected = set(APPROVED_WORKER_NAMES) | set(CANDIDATE_WORKER_NAMES)
    if set(_PROFILES) != expected:
        raise WorkerError("Worker registry identities do not match adapter policy")
    approved = {
        profile.name
        for profile in _PROFILES.values()
        if profile.approval_state == WorkerApprovalState.APPROVED
    }
    expected_real = set(APPROVED_WORKER_NAMES) - {"dry-run"}
    if approved != expected_real:
        raise WorkerError("Worker registry approval states do not match adapter policy")
    planners = {
        profile.name
        for profile in _PROFILES.values()
        if WorkerRole.PLANNING in profile.authorised_roles
    }
    if planners != set(APPROVED_PLANNER_NAMES) - {"dry-run"}:
        raise WorkerError("Worker registry planner roles do not match adapter policy")
    if _PROFILES["dry-run"].launchable:
        raise WorkerError("Simulation worker registry entry is unsafe")
    gemini = _PROFILES["gemini"]
    if (
        gemini.authorised_roles
        != (WorkerRole.IMPLEMENTATION, WorkerRole.FALLBACK)
        or not gemini.launchable
        or gemini.requires_owner_setup
        or gemini.requires_fresh_usage_evidence
    ):
        raise WorkerError("Gemini activation policy is unsafe")


validate_worker_registry()
