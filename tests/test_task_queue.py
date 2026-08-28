"""Contract tests for the governed task queue (TASK-143)."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from advancore.agent_runner.task_queue import (
    GovernedTaskQueue,
    TaskQueueError,
    TaskQueueStatus,
)


def _queue(tmp_path: Path) -> tuple[GovernedTaskQueue, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    state_path = tmp_path / "controller" / "task-queue.json"
    return GovernedTaskQueue(repository, state_path), state_path


def _time(hour: int) -> datetime:
    return datetime(2026, 8, 28, hour, tzinfo=timezone.utc)


def test_fifo_enqueue_claim_complete_and_persistence(tmp_path):
    queue, state_path = _queue(tmp_path)
    queue.enqueue("TASK-139", "tasks/TASK-139-worker-timeline.md", "kimi-swarm", now=_time(1))
    queue.enqueue("TASK-143", "tasks/TASK-143-task-queue.md", "gemini", now=_time(2))

    first = queue.claim_next(now=_time(3))
    assert first is not None
    assert first.task_id == "TASK-139"
    assert first.status == TaskQueueStatus.RUNNING
    completed = queue.complete("TASK-139", now=_time(4))
    assert completed.status == TaskQueueStatus.COMPLETED
    assert queue.claim_next(now=_time(5)).task_id == "TASK-143"

    reloaded = GovernedTaskQueue(tmp_path / "repo", state_path)
    assert [record.task_id for record in reloaded.list_records(now=_time(5))] == [
        "TASK-139",
        "TASK-143",
    ]
    assert state_path.stat().st_mode & 0o077 == 0
    assert state_path.parent.stat().st_mode & 0o077 == 0


def test_duplicate_and_invalid_values_fail_closed(tmp_path):
    queue, _ = _queue(tmp_path)
    queue.enqueue("TASK-139", "tasks/TASK-139-worker-timeline.md", "kimi-swarm", now=_time(1))
    with pytest.raises(TaskQueueError):
        queue.enqueue("TASK-139", "tasks/TASK-139-other.md", "gemini", now=_time(2))

    invalid = (
        ("task-140", "tasks/TASK-140-x.md", "kimi"),
        ("TASK-140", "../TASK-140-x.md", "kimi"),
        ("TASK-140", "/tmp/TASK-140-x.md", "kimi"),
        ("TASK-140", "tasks/TASK-141-wrong.md", "kimi"),
        ("TASK-140", "tasks/TASK-140-x.md", "shell-command"),
    )
    for task_id, task_path, worker in invalid:
        with pytest.raises(TaskQueueError):
            queue.enqueue(task_id, task_path, worker, now=_time(2))


def test_invalid_transitions_fail_closed(tmp_path):
    queue, _ = _queue(tmp_path)
    queue.enqueue("TASK-139", "tasks/TASK-139-worker-timeline.md", "kimi", now=_time(1))
    with pytest.raises(TaskQueueError):
        queue.complete("TASK-139", now=_time(2))
    with pytest.raises(TaskQueueError):
        queue.block("TASK-999", now=_time(2))
    queue.claim_next(now=_time(2))
    queue.complete("TASK-139", now=_time(3))
    with pytest.raises(TaskQueueError):
        queue.complete("TASK-139", now=_time(4))


def test_stale_running_claim_is_blocked_before_next_claim(tmp_path):
    queue, _ = _queue(tmp_path)
    queue.enqueue("TASK-139", "tasks/TASK-139-worker-timeline.md", "kimi", now=_time(1))
    queue.enqueue("TASK-140", "tasks/TASK-140-dashboard.md", "gemini", now=_time(2))
    queue.claim_next(now=_time(3))

    next_record = queue.claim_next(now=_time(3) + timedelta(hours=2))
    assert next_record is not None and next_record.task_id == "TASK-140"
    states = {record.task_id: record.status for record in queue.list_records(now=_time(5))}
    assert states["TASK-139"] == TaskQueueStatus.BLOCKED


def test_active_claim_prevents_second_concurrent_claim(tmp_path):
    queue, _ = _queue(tmp_path)
    queue.enqueue("TASK-139", "tasks/TASK-139-worker-timeline.md", "kimi", now=_time(1))
    queue.enqueue("TASK-140", "tasks/TASK-140-dashboard.md", "gemini", now=_time(2))
    queue.claim_next(now=_time(3))
    assert queue.claim_next(now=_time(3) + timedelta(minutes=5)) is None


def test_corrupt_oversized_future_and_in_repository_state_fail_closed(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(TaskQueueError):
        GovernedTaskQueue(repository, repository / "queue.json")

    queue, state_path = _queue(tmp_path)
    state_path.parent.mkdir(mode=0o700)
    state_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(TaskQueueError):
        queue.list_records(now=_time(3))

    state_path.write_text("x" * (600 * 1024), encoding="utf-8")
    with pytest.raises(TaskQueueError):
        queue.list_records(now=_time(3))

    state_path.write_text(
        json.dumps(
            [
                {
                    "task_id": "TASK-139",
                    "task_path": "tasks/TASK-139-x.md",
                    "worker": "kimi",
                    "status": "QUEUED",
                    "enqueued_at": (_time(3) + timedelta(days=2)).isoformat(),
                    "claimed_at": None,
                    "finished_at": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(TaskQueueError):
        queue.list_records(now=_time(3))
