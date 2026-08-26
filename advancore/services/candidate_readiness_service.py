"""Non-probing pre-authentication readiness for candidate AI workers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from advancore.agent_runner.worker_registry import (
    WorkerApprovalState,
    get_worker_profile,
)


class CandidateCheckState(str, Enum):
    PASS = "PASS"
    OWNER_REQUIRED = "OWNER_REQUIRED"
    BLOCKED = "BLOCKED"


class CandidateReadinessState(str, Enum):
    OWNER_SETUP_REQUIRED = "OWNER_SETUP_REQUIRED"
    READY_FOR_EVALUATION = "READY_FOR_EVALUATION"
    ACTIVATION_READY = "ACTIVATION_READY"
    ACTIVATED = "ACTIVATED"


@dataclass(frozen=True)
class CandidateReadinessCheck:
    key: str
    label: str
    state: CandidateCheckState
    message: str


@dataclass(frozen=True)
class CandidateReadinessSummary:
    worker: str
    state: CandidateReadinessState
    activation_allowed: bool
    checks: tuple[CandidateReadinessCheck, ...]
    next_owner_action: str
    accounts_probed: int = 0
    processes_launched: int = 0


class CandidateReadinessService:
    """Describe setup gates from code-owned facts only; access no provider."""

    def get_summary(self, worker: str) -> CandidateReadinessSummary:
        profile = get_worker_profile(worker)
        if worker == "gemini" and profile.approval_state == WorkerApprovalState.APPROVED:
            checks = (
                CandidateReadinessCheck(
                    "registry_boundary",
                    "Governed registry boundary",
                    CandidateCheckState.PASS,
                    "Gemini is approved only for implementation and fallback work.",
                ),
                CandidateReadinessCheck(
                    "provider_surface",
                    "Provider surface",
                    CandidateCheckState.PASS,
                    "The fixed local Antigravity CLI is the approved surface.",
                ),
                CandidateReadinessCheck(
                    "authentication",
                    "Account authentication",
                    CandidateCheckState.PASS,
                    "Owner-present Google authentication and a synthetic smoke "
                    "test passed.",
                ),
                CandidateReadinessCheck(
                    "data_boundary",
                    "Data boundary",
                    CandidateCheckState.PASS,
                    "Credential screening, fixed arguments, and workspace "
                    "sandboxing remain active.",
                ),
                CandidateReadinessCheck(
                    "activation_approval",
                    "Production activation",
                    CandidateCheckState.PASS,
                    "The owner approved Gemini as the second implementation worker.",
                ),
            )
            return CandidateReadinessSummary(
                worker=profile.name,
                state=CandidateReadinessState.ACTIVATED,
                activation_allowed=True,
                checks=checks,
                next_owner_action=(
                    "No account action is required. TASK-099 will connect the "
                    "Kimi, Gemini, then Codex runtime sequence."
                ),
            )
        if profile.approval_state != WorkerApprovalState.CANDIDATE:
            raise ValueError("Worker is not a candidate")
        checks = (
            CandidateReadinessCheck(
                "registry_boundary",
                "Safe registry boundary",
                CandidateCheckState.PASS,
                "Candidate is registered but has no production role.",
            ),
            CandidateReadinessCheck(
                "launch_boundary",
                "Launch boundary",
                CandidateCheckState.PASS,
                "Candidate owns no executable, command, endpoint, or credential path.",
            ),
            CandidateReadinessCheck(
                "provider_surface",
                "Provider surface",
                CandidateCheckState.OWNER_REQUIRED,
                "Owner must choose the supported Gemini access method.",
            ),
            CandidateReadinessCheck(
                "authentication",
                "Account authentication",
                CandidateCheckState.OWNER_REQUIRED,
                "Owner-present Google authentication has not been completed.",
            ),
            CandidateReadinessCheck(
                "data_terms",
                "Data handling terms",
                CandidateCheckState.OWNER_REQUIRED,
                "Owner must review provider data handling for the selected surface.",
            ),
            CandidateReadinessCheck(
                "billing_terms",
                "Billing and entitlement",
                CandidateCheckState.OWNER_REQUIRED,
                "Subscription entitlement and any API billing remain unverified.",
            ),
            CandidateReadinessCheck(
                "usage_evidence",
                "Usage evidence",
                CandidateCheckState.BLOCKED,
                "A bounded usage reading depends on the authenticated surface.",
            ),
            CandidateReadinessCheck(
                "smoke_evaluation",
                "Bounded evaluation",
                CandidateCheckState.BLOCKED,
                "Credential-safe smoke evaluation must follow owner setup.",
            ),
            CandidateReadinessCheck(
                "activation_approval",
                "Production activation",
                CandidateCheckState.BLOCKED,
                "Explicit owner approval and controller review are still required.",
            ),
        )
        return CandidateReadinessSummary(
            worker=profile.name,
            state=CandidateReadinessState.OWNER_SETUP_REQUIRED,
            activation_allowed=False,
            checks=checks,
            next_owner_action=(
                "In an owner-present session, choose the Gemini access surface, "
                "review its data and billing terms, then authenticate directly."
            ),
        )
