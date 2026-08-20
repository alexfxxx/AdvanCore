"""Tests for the task lifecycle control plane.

These tests are isolated from the real repository and Git state. They exercise
state-machine authority, file mutation, dry-run behaviour, malformed-file
handling, and audit metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from advancore.agent_runner.lifecycle import (
    ActorRole,
    LifecycleError,
    LifecycleResult,
    TaskStatus,
    is_transition_allowed,
    transition_task,
)
from advancore.agent_runner.task import TaskError
from advancore.agent_runner.git_info import GitInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_task(
    tasks_dir: Path,
    task_id: str,
    title: str,
    status: str,
    filename: str | None = None,
    content: str | None = None,
) -> Path:
    """Write a minimal task file and return its path."""
    filename = filename or f"{task_id}-sample-task.md"
    path = tasks_dir / filename
    body = content if content is not None else "Do the thing."
    path.write_text(
        f"# {task_id} — {title}\n\nSTATUS: {status}\n\n## Objective\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def _git_info(repo_root: Path) -> GitInfo:
    return GitInfo(
        repo_root=repo_root,
        current_branch="lifecycle-tests",
        head_sha="abc1230000000000000000000000000000000000",
        is_clean=True,
        status_lines=[],
    )


# ---------------------------------------------------------------------------
# Pure transition authority
# ---------------------------------------------------------------------------


class TestTransitionAuthority:
    @pytest.mark.parametrize(
        "current, requested, actor, expected",
        [
            # Worker transitions
            (TaskStatus.READY, TaskStatus.IN_PROGRESS, ActorRole.WORKER, True),
            (TaskStatus.REWORK, TaskStatus.IN_PROGRESS, ActorRole.WORKER, True),
            (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, ActorRole.WORKER, True),
            # Controller/reviewer transitions
            (TaskStatus.DRAFT, TaskStatus.READY, ActorRole.CONTROLLER, True),
            (TaskStatus.REVIEW, TaskStatus.APPROVED, ActorRole.CONTROLLER, True),
            (TaskStatus.REVIEW, TaskStatus.REWORK, ActorRole.CONTROLLER, True),
            (TaskStatus.READY, TaskStatus.BLOCKED, ActorRole.CONTROLLER, True),
            (TaskStatus.BLOCKED, TaskStatus.READY, ActorRole.CONTROLLER, True),
            (TaskStatus.BLOCKED, TaskStatus.REWORK, ActorRole.CONTROLLER, True),
            # Owner can perform controller transitions
            (TaskStatus.DRAFT, TaskStatus.READY, ActorRole.OWNER, True),
            (TaskStatus.REVIEW, TaskStatus.APPROVED, ActorRole.OWNER, True),
            # Owner can also perform worker transitions
            (TaskStatus.READY, TaskStatus.IN_PROGRESS, ActorRole.OWNER, True),
            (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, ActorRole.OWNER, True),
        ],
    )
    def test_allowed_transitions(
        self, current: TaskStatus, requested: TaskStatus, actor: ActorRole, expected: bool
    ):
        allowed, _reason = is_transition_allowed(current, requested, actor)
        assert allowed is expected

    @pytest.mark.parametrize(
        "current, requested, actor",
        [
            # Worker cannot approve
            (TaskStatus.REVIEW, TaskStatus.APPROVED, ActorRole.WORKER),
            (TaskStatus.REVIEW, TaskStatus.REWORK, ActorRole.WORKER),
            (TaskStatus.DRAFT, TaskStatus.READY, ActorRole.WORKER),
            # Worker cannot block or unblock
            (TaskStatus.READY, TaskStatus.BLOCKED, ActorRole.WORKER),
            (TaskStatus.BLOCKED, TaskStatus.READY, ActorRole.WORKER),
            # Controller cannot perform worker-only transitions
            (TaskStatus.READY, TaskStatus.IN_PROGRESS, ActorRole.CONTROLLER),
            (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, ActorRole.CONTROLLER),
            # Invalid skipped transitions
            (TaskStatus.DRAFT, TaskStatus.IN_PROGRESS, ActorRole.OWNER),
            (TaskStatus.READY, TaskStatus.REVIEW, ActorRole.OWNER),
            (TaskStatus.DRAFT, TaskStatus.APPROVED, ActorRole.OWNER),
            # Final state cannot transition
            (TaskStatus.APPROVED, TaskStatus.BLOCKED, ActorRole.CONTROLLER),
            (TaskStatus.APPROVED, TaskStatus.REWORK, ActorRole.CONTROLLER),
            # Same status is not a transition
            (TaskStatus.READY, TaskStatus.READY, ActorRole.WORKER),
        ],
    )
    def test_denied_transitions(
        self, current: TaskStatus, requested: TaskStatus, actor: ActorRole
    ):
        allowed, _reason = is_transition_allowed(current, requested, actor)
        assert allowed is False

    def test_blocked_from_any_non_final_working_state(self):
        for status in [
            TaskStatus.DRAFT,
            TaskStatus.READY,
            TaskStatus.IN_PROGRESS,
            TaskStatus.REVIEW,
            TaskStatus.REWORK,
        ]:
            allowed, _ = is_transition_allowed(status, TaskStatus.BLOCKED, ActorRole.CONTROLLER)
            assert allowed is True

    def test_blocked_from_approved_is_denied(self):
        allowed, _ = is_transition_allowed(
            TaskStatus.APPROVED, TaskStatus.BLOCKED, ActorRole.CONTROLLER
        )
        assert allowed is False

    def test_unknown_status_raises(self):
        with pytest.raises(LifecycleError, match="Unknown task status"):
            is_transition_allowed("READY", "UNKNOWN", ActorRole.WORKER)

    def test_unknown_actor_raises(self):
        with pytest.raises(LifecycleError, match="Unknown actor role"):
            is_transition_allowed(TaskStatus.READY, TaskStatus.IN_PROGRESS, "manager")


# ---------------------------------------------------------------------------
# Transition helper / file mutation
# ---------------------------------------------------------------------------


class TestTransitionTask:
    def test_dry_run_does_not_modify_file(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        original_text = "# TASK-001 — Test\n\nSTATUS: READY\n\nBody.\n"
        path = tasks_dir / "TASK-001-test.md"
        path.write_text(original_text, encoding="utf-8")

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.IN_PROGRESS,
            ActorRole.WORKER,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is True
        assert result.allowed is True
        assert result.applied is False
        assert result.mode == "preview"
        assert path.read_text(encoding="utf-8") == original_text

    def test_apply_changes_only_status_line(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        original_text = "# TASK-001 — Test\n\nSTATUS: READY\n\nBody line one.\nBody line two.\n"
        path = tasks_dir / "TASK-001-test.md"
        path.write_text(original_text, encoding="utf-8")

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.IN_PROGRESS,
            ActorRole.WORKER,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is True
        assert result.allowed is True
        assert result.applied is True
        assert result.mode == "apply"

        new_text = path.read_text(encoding="utf-8")
        assert new_text == (
            "# TASK-001 — Test\n\nSTATUS: IN_PROGRESS\n\nBody line one.\nBody line two.\n"
        )

    def test_denied_transition_does_not_modify_file(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        original_text = "# TASK-001 — Test\n\nSTATUS: REVIEW\n\nBody.\n"
        path = tasks_dir / "TASK-001-test.md"
        path.write_text(original_text, encoding="utf-8")

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.APPROVED,
            ActorRole.WORKER,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert result.allowed is False
        assert result.applied is False
        assert path.read_text(encoding="utf-8") == original_text

    def test_missing_status_line_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        path = tasks_dir / "TASK-001-test.md"
        path.write_text("# TASK-001 — Test\n\nNo status here.\n", encoding="utf-8")

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.READY,
            ActorRole.CONTROLLER,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "No STATUS line" in " ".join(result.messages)

    def test_duplicate_status_lines_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        path = tasks_dir / "TASK-001-test.md"
        path.write_text(
            "# TASK-001 — Test\n\nSTATUS: DRAFT\n\nSTATUS: READY\n",
            encoding="utf-8",
        )

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.READY,
            ActorRole.CONTROLLER,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "Ambiguous STATUS" in " ".join(result.messages)

    def test_unknown_task_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)

        result = transition_task(
            tasks_dir,
            "TASK-999",
            TaskStatus.READY,
            ActorRole.CONTROLLER,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert result.task_id is None


# ---------------------------------------------------------------------------
# Audit metadata
# ---------------------------------------------------------------------------


class TestLifecycleAudit:
    def _load_last_record(self, audit_path: Path) -> dict:
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lines[-1])

    def test_preview_writes_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready", "READY")

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.IN_PROGRESS,
            ActorRole.WORKER,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.audit_path is not None
        assert result.audit_path.exists()
        record = self._load_last_record(result.audit_path)
        assert record["mode"] == "lifecycle"
        assert record["task_id"] == "TASK-001"
        assert record["actor_role"] == "worker"
        assert record["previous_status"] == "READY"
        assert record["requested_status"] == "IN_PROGRESS"
        assert record["transition_allowed"] is True
        assert record["applied"] is False
        assert record["branch"] == "lifecycle-tests"
        assert record["head_sha"] == "abc1230000000000000000000000000000000000"

    def test_denied_attempt_writes_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Review", "REVIEW")

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.APPROVED,
            ActorRole.WORKER,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.allowed is False
        record = self._load_last_record(result.audit_path)
        assert record["transition_allowed"] is False
        assert record["applied"] is False

    def test_audit_record_excludes_task_body(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-001",
            "Secret",
            "READY",
            content="Business secret: password=abc token=xyz",
        )

        result = transition_task(
            tasks_dir,
            "TASK-001",
            TaskStatus.IN_PROGRESS,
            ActorRole.WORKER,
            apply=False,
            git_info=_git_info(repo_root),
        )

        record = self._load_last_record(result.audit_path)
        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "mode",
            "actor_role",
            "previous_status",
            "requested_status",
            "transition_allowed",
            "applied",
            "branch",
            "head_sha",
        }
        assert set(record.keys()) == expected_keys
        raw = json.dumps(record)
        assert "password" not in raw.lower()
        assert "token" not in raw.lower()
        assert "Business secret" not in raw


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestLifecycleCLI:
    def test_cli_transition_preview_returns_zero_for_allowed(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready", "READY")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["transition", "TASK-001", "--to", "IN_PROGRESS", "--actor", "worker"])
        assert code == 0

    def test_cli_transition_denied_returns_nonzero(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Review", "REVIEW")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["transition", "TASK-001", "--to", "APPROVED", "--actor", "worker"])
        assert code == 1

    def test_cli_apply_mutates_status_line(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready", "READY")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            ["transition", "TASK-001", "--to", "IN_PROGRESS", "--actor", "worker", "--apply"]
        )
        assert code == 0
        text = (tasks_dir / "TASK-001-sample-task.md").read_text(encoding="utf-8")
        assert "STATUS: IN_PROGRESS" in text
