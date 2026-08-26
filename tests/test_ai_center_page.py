"""Read-only AI Center exception inbox tests (TASK-049)."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from advancore.agent_runner.orchestration_inbox import (
    INBOX_SCHEMA_VERSION,
    OrchestrationInbox,
    OrchestrationInboxEntry,
)
from advancore.agent_runner.worker_rehearsal import MultiWorkerRehearsalReport, RehearsalCheck
from advancore.services.worker_route_preview_service import (
    WorkerRoutePreview,
    WorkerRoutePreviewState,
)
from advancore.agent_runner.worker_registry import WorkerRole
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
)
from advancore.services.candidate_readiness_service import CandidateReadinessService


def _run(inbox):
    script = """
from advancore.pages import ai_center
ai_center.render()
"""
    preview = WorkerRoutePreview(
        WorkerRole.IMPLEMENTATION,
        WorkerRoutePreviewState.SELECTED,
        "kimi-swarm",
        (WorkerAvailabilityEvidence("kimi-swarm", WorkerAvailability.AVAILABLE),),
        "selected",
    )
    rehearsal = MultiWorkerRehearsalReport(
        True, (RehearsalCheck("policy", True, "bounded"),)
    )
    with patch(
        "advancore.pages.ai_center.build_orchestration_inbox", return_value=inbox
    ), patch(
        "advancore.pages.ai_center._worker_route_preview_service"
    ) as route, patch(
        "advancore.pages.ai_center.run_multi_worker_governance_rehearsal",
        return_value=rehearsal,
    ):
        route.return_value.preview.return_value = preview
        return AppTest.from_string(script).run()


def test_ai_center_shows_plain_all_clear_state():
    app = _run(OrchestrationInbox(INBOX_SCHEMA_VERSION, ()))
    assert not app.exception
    assert any("No owner decisions" in item.value for item in app.success)
    assert any("Current evidence selects kimi-swarm" in item.value for item in app.success)
    assert any("zero workers launched" in item.value for item in app.success)


def test_ai_center_shows_only_bounded_owner_exception_fields():
    entry = OrchestrationInboxEntry(
        run_id="ORCH-test",
        task_id="TASK-049",
        task_title="Owner exception inbox",
        phase="AWAITING_IMPLEMENTATION_DECISION",
        status="OWNER_DECISION_REQUIRED",
        classification="action-required",
        reason="Implementation review is ready.",
        evidence_references=("hidden.json",),
        owner_decision_required=True,
        command="hidden terminal command",
    )
    app = _run(OrchestrationInbox(INBOX_SCHEMA_VERSION, (entry,)))
    assert not app.exception
    rendered = " ".join(item.value for item in (*app.markdown, *app.warning))
    assert "Implementation review is ready" in rendered
    assert "Your decision is required" in rendered
    assert "hidden terminal command" not in rendered
    assert "hidden.json" not in rendered


def test_ai_center_fails_closed_without_local_details():
    script = """
from advancore.pages import ai_center
ai_center.render()
"""
    with patch(
        "advancore.pages.ai_center.build_orchestration_inbox",
        side_effect=RuntimeError("secret local path"),
    ):
        app = AppTest.from_string(script).run()
    assert not app.exception
    assert any("status is unavailable" in item.value for item in app.warning)
    assert all("secret local path" not in item.value for item in app.warning)


def test_governance_panel_blocks_without_evidence_and_does_not_launch(monkeypatch):
    preview = WorkerRoutePreview(
        WorkerRole.IMPLEMENTATION,
        WorkerRoutePreviewState.BLOCKED,
        None,
        (
            WorkerAvailabilityEvidence(
                "kimi-swarm", WorkerAvailability.UNAVAILABLE
            ),
            WorkerAvailabilityEvidence("codex", WorkerAvailability.UNAVAILABLE),
        ),
        "No approved worker is currently proven available.",
    )
    rehearsal = MultiWorkerRehearsalReport(
        True, (RehearsalCheck("policy", True, "bounded"),)
    )
    script = """
from pathlib import Path
from advancore.pages import ai_center
ai_center._render_worker_governance(Path.cwd())
"""
    with patch(
        "advancore.pages.ai_center._worker_route_preview_service"
    ) as route, patch(
        "advancore.pages.ai_center.run_multi_worker_governance_rehearsal",
        return_value=rehearsal,
    ), patch(
        "advancore.agent_runner.worker.subprocess.Popen",
        side_effect=AssertionError("must not launch"),
    ):
        route.return_value.preview.return_value = preview
        app = AppTest.from_string(script).run()
    assert not app.exception
    assert any("No approved worker" in item.value for item in app.warning)
    assert any("zero workers launched" in item.value for item in app.success)


def test_gemini_readiness_panel_shows_owner_approved_activation():
    script = """
from advancore.pages import ai_center
ai_center._render_candidate_readiness()
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    rendered = " ".join(
        item.value for item in (*app.markdown, *app.success, *app.caption)
    )
    assert "authenticated and owner-approved" in rendered
    assert "TASK-099" in rendered
    assert "Accounts probed by this view: 0" in rendered
    assert "Processes launched by this view: 0" in rendered
    assert CandidateReadinessService().get_summary("gemini").activation_allowed is True
