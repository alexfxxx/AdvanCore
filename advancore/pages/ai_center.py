from pathlib import Path

import streamlit as st

from advancore.agent_runner.orchestration_inbox import build_orchestration_inbox
from advancore.agent_runner.worker_registry import WorkerRole
from advancore.agent_runner.worker_rehearsal import (
    run_multi_worker_governance_rehearsal,
)
from advancore.services.worker_health_service import WorkerHealthService
from advancore.services.worker_route_preview_service import (
    WorkerRoutePreviewService,
    WorkerRoutePreviewState,
)
from advancore.services.worker_routing_evidence_service import (
    WorkerRoutingEvidenceService,
)
from advancore.services.worker_usage_service import WorkerUsageService
from advancore.services.candidate_readiness_service import (
    CandidateCheckState,
    CandidateReadinessService,
)


def _worker_route_preview_service(root: Path) -> WorkerRoutePreviewService:
    usage = WorkerUsageService(root)
    health = WorkerHealthService(usage)
    evidence = WorkerRoutingEvidenceService(health)
    return WorkerRoutePreviewService(evidence)


def _render_worker_governance(root: Path) -> None:
    st.subheader("Worker routing status")
    st.caption(
        "Read-only preview. This starts no worker and consumes no controller authority."
    )
    try:
        preview = _worker_route_preview_service(root).preview(
            WorkerRole.IMPLEMENTATION
        )
    except Exception:
        st.warning("Worker routing preview is unavailable. No worker was started.")
    else:
        if preview.state == WorkerRoutePreviewState.SELECTED:
            st.success(
                f"Current evidence selects {preview.selected_worker} first for implementation."
            )
        else:
            st.warning(preview.message)
        with st.expander("Routing evidence"):
            for item in preview.evidence:
                st.write(f"{item.worker}: {item.state.value.replace('_', ' ').title()}")
            st.caption(
                "Codex readiness is checked at actual launch. Gemini remains outside "
                "production routing."
            )

    st.subheader("Offline governance self-check")
    try:
        rehearsal = run_multi_worker_governance_rehearsal(working_directory=root)
    except Exception:
        st.error("Offline worker-governance rehearsal is unavailable.")
        return
    passed = sum(check.passed for check in rehearsal.checks)
    if rehearsal.passed and rehearsal.workers_launched == 0:
        st.success(
            f"Governance rehearsal passed {passed}/{len(rehearsal.checks)} checks; "
            "zero workers launched."
        )
    else:
        st.error(
            "Governance rehearsal did not pass. Worker automation should remain paused."
        )


def _render_candidate_readiness() -> None:
    st.subheader("Gemini setup readiness")
    try:
        summary = CandidateReadinessService().get_summary("gemini")
    except Exception:
        st.error("Gemini candidate readiness is unavailable. Gemini remains inactive.")
        return
    st.warning("Gemini is safely registered but not authenticated or active.")
    st.write(summary.next_owner_action)
    with st.expander("Gemini pre-authentication checklist"):
        for check in summary.checks:
            label = check.state.value.replace("_", " ").title()
            st.write(f"{check.label} — {label}: {check.message}")
    blocked = sum(check.state == CandidateCheckState.BLOCKED for check in summary.checks)
    owner = sum(
        check.state == CandidateCheckState.OWNER_REQUIRED for check in summary.checks
    )
    st.caption(
        f"Owner-required checks: {owner}. Blocked follow-on checks: {blocked}. "
        "Accounts probed: 0. Processes launched: 0."
    )


def render(repo_root: Path | None = None):
    st.header("AI Center")
    st.caption("Automation runs independently and pauses only when attention is required.")
    root = (repo_root or Path.cwd()).resolve()
    try:
        inbox = build_orchestration_inbox(root)
    except Exception:
        st.warning("Automation status is unavailable. Local controller inspection is required.")
        return

    st.subheader("Needs your attention")
    if not inbox.entries:
        st.success("No owner decisions or automation investigations are waiting.")
    else:
        decision_count = sum(entry.owner_decision_required for entry in inbox.entries)
        st.metric("Waiting items", len(inbox.entries))
        st.metric("Owner decisions", decision_count)
        for entry in inbox.entries:
            label = entry.task_title or entry.task_id or "Automation run"
            with st.expander(label):
                st.write(f"Status: {entry.status}")
                st.write(entry.reason)
                if entry.owner_decision_required:
                    st.warning("Your decision is required before this work can continue.")
                else:
                    st.info("The local controller must investigate this item.")
    _render_worker_governance(root)
    _render_candidate_readiness()
