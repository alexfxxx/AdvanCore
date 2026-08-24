"""Tests for TASK-047 fixed authorized worker routing."""

from pathlib import Path

from advancore.agent_runner.standing_authority import RoutineAction, StandingAuthorityError
from advancore.agent_runner.worker import WorkerAdapter, WorkerResult
from advancore.agent_runner.worker_routing import AuthorizedWorkerAdapter


class Authority:
    def __init__(self, blocked=None):
        self.actions = []
        self.blocked = blocked

    def consume(self, task_id, branch, action):
        self.actions.append((task_id, branch, action))
        if action == self.blocked:
            raise StandingAuthorityError("blocked")


class Worker(WorkerAdapter):
    def __init__(self, name="codex"):
        self._name = name
        self.allowed_scope = []
        self.runs = 0

    @property
    def name(self):
        return self._name

    def build_command(self, instruction, working_dir):
        return [self.name, instruction]

    def run(self, instruction, working_dir):
        self.runs += 1
        return WorkerResult(True, message="ok")


def test_primary_consumes_worker_authority_at_launch(tmp_path):
    authority = Authority()
    worker = Worker("kimi-swarm")
    adapter = AuthorizedWorkerAdapter(
        worker, authority, "TASK-047", "feature", (RoutineAction.RUN_WORKER,)
    )
    assert adapter.run("work", tmp_path).success
    assert worker.runs == 1
    assert [item[2] for item in authority.actions] == [RoutineAction.RUN_WORKER]


def test_fallback_consumes_fallback_then_worker_authority(tmp_path):
    authority = Authority()
    worker = Worker()
    adapter = AuthorizedWorkerAdapter(
        worker,
        authority,
        "TASK-047",
        "feature",
        (RoutineAction.APPROVED_FALLBACK, RoutineAction.RUN_WORKER),
    )
    assert adapter.run("work", tmp_path).success
    assert [item[2] for item in authority.actions] == [
        RoutineAction.APPROVED_FALLBACK,
        RoutineAction.RUN_WORKER,
    ]


def test_missing_authority_blocks_before_worker_launch(tmp_path):
    authority = Authority(RoutineAction.APPROVED_FALLBACK)
    worker = Worker()
    adapter = AuthorizedWorkerAdapter(
        worker,
        authority,
        "TASK-047",
        "feature",
        (RoutineAction.APPROVED_FALLBACK, RoutineAction.RUN_WORKER),
    )
    result = adapter.run("work", tmp_path)
    assert not result.success
    assert result.terminal_reason == "authority_blocked"
    assert worker.runs == 0


def test_scope_updates_are_forwarded_to_registered_delegate():
    worker = Worker()
    adapter = AuthorizedWorkerAdapter(
        worker, Authority(), "TASK-047", "feature", (RoutineAction.RUN_WORKER,)
    )
    adapter.allowed_scope = ["one.py"]
    assert worker.allowed_scope == ["one.py"]
    assert adapter.allowed_scope == ["one.py"]

