"""Redacted vendor-neutral owner notifications from the validated inbox."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from advancore.agent_runner.orchestration_inbox import OrchestrationInbox


OWNER_NOTIFICATION_SCHEMA = "advancore-owner-notifications-v1"
_TASK_ID_RE = re.compile(r"^TASK-[0-9]{3,6}$")
_RUN_ID_RE = re.compile(r"^ORCH-[A-Za-z0-9_-]{1,120}$")


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


def _safe_run_id(value: object) -> str:
    if isinstance(value, str) and _RUN_ID_RE.fullmatch(value):
        return value
    return "ORCH-redacted-invalid"


def build_owner_notification_feed(inbox: OrchestrationInbox) -> OwnerNotificationFeed:
    """Project already validated entries without carrying operational details."""
    notifications = []
    for entry in inbox.entries:
        task_id = (
            entry.task_id
            if isinstance(entry.task_id, str) and _TASK_ID_RE.fullmatch(entry.task_id)
            else None
        )
        run_id = _safe_run_id(entry.run_id)
        if entry.owner_decision_required:
            severity = "decision"
            title = f"{task_id} needs your decision" if task_id else "AdvanCore needs your decision"
            message = "A governed task is waiting for an owner decision. Open AI Center for details."
        elif entry.classification == "stale-or-invalid-evidence":
            severity = "investigation"
            title = f"{task_id} needs inspection" if task_id else "AdvanCore needs inspection"
            message = "Automation evidence needs local controller inspection. Open AI Center for details."
        else:
            severity = "investigation"
            title = f"{task_id} needs investigation" if task_id else "AdvanCore needs investigation"
            message = "A local controller investigation is required. Open AI Center for details."
        identity = "\0".join((run_id, severity, task_id or "none", message))
        notifications.append(
            OwnerNotification(
                notification_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                severity=severity,
                title=title,
                message=message,
                task_id=task_id,
                run_id=run_id,
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
