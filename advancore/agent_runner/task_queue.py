"""Controller-owned queue for approved governed task identifiers.

TASK-143 implementation scaffold. The assigned implementation worker must
replace the fail-closed TODO methods without adding execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class TaskQueueError(RuntimeError):
    """Raised when queue state or a requested transition is unsafe."""


class TaskQueueStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class TaskQueueRecord:
    task_id: str
    task_path: str
    worker: str
    status: TaskQueueStatus
    enqueued_at: datetime
    claimed_at: datetime | None = None
    finished_at: datetime | None = None


class GovernedTaskQueue:
    """Persist bounded task metadata; never launch or authorize a worker."""

    def __init__(self, repository_root: Path, state_path: Path):
        raise TaskQueueError("TASK-143 implementation required")

    def list_records(self, *, now: datetime | None = None) -> list[TaskQueueRecord]:
        raise TaskQueueError("TASK-143 implementation required")

    def enqueue(
        self,
        task_id: str,
        task_path: str,
        worker: str,
        *,
        now: datetime | None = None,
    ) -> TaskQueueRecord:
        raise TaskQueueError("TASK-143 implementation required")

    def claim_next(self, *, now: datetime | None = None) -> TaskQueueRecord | None:
        raise TaskQueueError("TASK-143 implementation required")

    def complete(self, task_id: str, *, now: datetime | None = None) -> TaskQueueRecord:
        raise TaskQueueError("TASK-143 implementation required")

    def block(self, task_id: str, *, now: datetime | None = None) -> TaskQueueRecord:
        raise TaskQueueError("TASK-143 implementation required")
