"""Redacted vendor-neutral owner notifications from the validated inbox."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from advancore.agent_runner.orchestration_inbox import OrchestrationInbox


OWNER_NOTIFICATION_SCHEMA = "advancore-owner-notifications-v1"
MAX_NOTIFICATION_TEXT = 240


@dataclass(frozen=True)
class OwnerNotification:
    notification_id: str
    severity: str
    title: str
    message: str
    task_id: str | None
    run_id: str
    owner_decision_required: bool


@dataclass(frozen=True)
class OwnerNotificationFeed:
    schema_version: str
    notifications: tuple[OwnerNotification, ...]


def _bounded(value: object, fallback: str) -> str:
    text = " ".join(value.split()) if isinstance(value, str) else fallback
    if not text:
        text = fallback
    return text[:MAX_NOTIFICATION_TEXT]


def build_owner_notification_feed(inbox: OrchestrationInbox) -> OwnerNotificationFeed:
    """Project already validated entries without carrying operational details."""
    notifications = []
    for entry in inbox.entries:
        title = _bounded(entry.task_title or entry.task_id, "AdvanCore automation")
        message = _bounded(entry.reason, "Automation attention is required.")
        identity = "\0".join((entry.run_id, entry.status, entry.classification, message))
        notifications.append(
            OwnerNotification(
                notification_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                severity="decision" if entry.owner_decision_required else "investigation",
                title=title,
                message=message,
                task_id=entry.task_id,
                run_id=entry.run_id,
                owner_decision_required=entry.owner_decision_required,
            )
        )
    return OwnerNotificationFeed(OWNER_NOTIFICATION_SCHEMA, tuple(notifications))


def serialize_owner_notification_feed(feed: OwnerNotificationFeed) -> str:
    return json.dumps(
        {
            "schema_version": feed.schema_version,
            "notifications": [asdict(item) for item in feed.notifications],
        },
        indent=2,
        sort_keys=True,
    )

