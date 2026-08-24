"""Read-only AI Center exception inbox tests (TASK-049)."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from advancore.agent_runner.orchestration_inbox import (
    INBOX_SCHEMA_VERSION,
    OrchestrationInbox,
    OrchestrationInboxEntry,
)


def _run(inbox):
    script = """
from advancore.pages import ai_center
ai_center.render()
"""
    with patch(
        "advancore.pages.ai_center.build_orchestration_inbox", return_value=inbox
    ):
        return AppTest.from_string(script).run()


def test_ai_center_shows_plain_all_clear_state():
    app = _run(OrchestrationInbox(INBOX_SCHEMA_VERSION, ()))
    assert not app.exception
    assert any("No owner decisions" in item.value for item in app.success)


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
