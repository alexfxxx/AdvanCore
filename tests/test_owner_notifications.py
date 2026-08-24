"""Tests for TASK-050 redacted owner notification contract."""

import json

from advancore.agent_runner.orchestration_inbox import (
    INBOX_SCHEMA_VERSION,
    OrchestrationInbox,
    OrchestrationInboxEntry,
)
from advancore.agent_runner.owner_notifications import (
    OWNER_NOTIFICATION_SCHEMA,
    build_owner_notification_feed,
    serialize_owner_notification_feed,
)


def _entry(owner=True):
    return OrchestrationInboxEntry(
        run_id="ORCH-notify",
        task_id="TASK-050",
        task_title="Owner notifications",
        phase="AWAITING_IMPLEMENTATION_DECISION",
        status="OWNER_DECISION_REQUIRED" if owner else "BLOCKED",
        classification="action-required" if owner else "operator-investigation",
        reason="A bounded decision is waiting.",
        evidence_references=("secret/evidence.json",),
        owner_decision_required=owner,
        command="dangerous hidden command --token secret",
    )


def test_notification_feed_is_stable_bounded_and_redacted():
    inbox = OrchestrationInbox(INBOX_SCHEMA_VERSION, (_entry(),))
    first = build_owner_notification_feed(inbox)
    second = build_owner_notification_feed(inbox)
    assert first == second
    assert first.schema_version == OWNER_NOTIFICATION_SCHEMA
    item = first.notifications[0]
    assert item.severity == "decision"
    assert len(item.notification_id) == 24
    serialized = serialize_owner_notification_feed(first)
    for prohibited in ("dangerous hidden command", "secret/evidence", "--token"):
        assert prohibited not in serialized


def test_notification_json_has_only_delivery_safe_fields():
    payload = json.loads(
        serialize_owner_notification_feed(
            build_owner_notification_feed(
                OrchestrationInbox(INBOX_SCHEMA_VERSION, (_entry(False),))
            )
        )
    )
    assert set(payload) == {"schema_version", "notifications"}
    assert set(payload["notifications"][0]) == {
        "notification_id",
        "severity",
        "title",
        "message",
        "task_id",
        "run_id",
        "owner_decision_required",
    }
    assert payload["notifications"][0]["severity"] == "investigation"


def test_empty_inbox_produces_empty_feed():
    feed = build_owner_notification_feed(OrchestrationInbox(INBOX_SCHEMA_VERSION, ()))
    assert feed.notifications == ()

