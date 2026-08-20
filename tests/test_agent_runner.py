"""Tests for the local agent runner foundation.

These tests are fully isolated: they use temporary directories and mock Git,
subprocess, and worker interactions so they do not depend on the state of the
real repository or on Kimi Code being installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner import (
    DryRunWorkerAdapter,
    KimiWorkerAdapter,
    WorkerAdapter,
    WorkerResult,
    build_worker_instruction,
    discover_tasks,
    execute,
    find_task,
    parse_task,
    plan,
    validate,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.runner import RunnerStatus
from advancore.agent_runner.task import Task, TaskError


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


# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------


class TestTaskParsing:
    def test_ready_task_is_parsed_correctly(self, tmp_path: Path):
        path = _write_task(tmp_path, "TASK-001", "Sample Ready Task", "READY")

        task = parse_task(path)

        assert task.task_id == "TASK-001"
        assert task.title == "Sample Ready Task"
        assert task.status == "READY"
        assert task.filename == "TASK-001-sample-task.md"
        assert task.path == path

    def test_missing_status_fails_safely(self, tmp_path: Path):
        path = tmp_path / "TASK-001-no-status.md"
        path.write_text("# TASK-001 — No Status\n\nNo status line here.\n")

        with pytest.raises(TaskError, match="No STATUS line"):
            parse_task(path)

    def test_missing_title_fails_safely(self, tmp_path: Path):
        path = tmp_path / "TASK-001-no-title.md"
        path.write_text("STATUS: READY\n\nNo title.\n")

        with pytest.raises(TaskError, match="No title/ID"):
            parse_task(path)

    def test_id_mismatch_between_filename_and_title_fails(self, tmp_path: Path):
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Mismatch",
            "READY",
            filename="TASK-002-mismatch.md",
        )

        with pytest.raises(TaskError, match="Task ID mismatch"):
            parse_task(path)

    def test_bad_filename_pattern_fails(self, tmp_path: Path):
        path = tmp_path / "not-a-task.md"
        path.write_text("# TASK-001 — Bad\n\nSTATUS: READY\n")

        with pytest.raises(TaskError, match="Filename does not match"):
            parse_task(path)


# ---------------------------------------------------------------------------
# Task discovery and selection
# ---------------------------------------------------------------------------


class TestTaskDiscoveryAndSelection:
    def test_discover_tasks_skips_unparseable_files(self, tmp_path: Path):
        _write_task(tmp_path, "TASK-001", "Ready", "READY")
        (tmp_path / "TASK-002-bad.md").write_text("no status")

        tasks = discover_tasks(tmp_path)

        assert len(tasks) == 1
        assert tasks[0].task_id == "TASK-001"

    def test_find_task_by_id(self, tmp_path: Path):
        _write_task(tmp_path, "TASK-001", "One", "READY")
        _write_task(tmp_path, "TASK-002", "Two", "READY")

        task = find_task(tmp_path, "TASK-002")

        assert task.task_id == "TASK-002"
        assert task.title == "Two"

    def test_find_task_by_path(self, tmp_path: Path):
        _write_task(tmp_path, "TASK-001", "One", "READY")

        task = find_task(tmp_path, "TASK-001-sample-task.md")

        assert task.task_id == "TASK-001"

    def test_find_task_unknown_raises(self, tmp_path: Path):
        with pytest.raises(TaskError, match="not found"):
            find_task(tmp_path, "TASK-999")

    def test_find_task_ambiguous_raises(self, tmp_path: Path):
        _write_task(
            tmp_path,
            "TASK-001",
            "One",
            "READY",
            filename="TASK-001-one.md",
        )
        _write_task(
            tmp_path,
            "TASK-001",
            "One Again",
            "READY",
            filename="TASK-001-two.md",
        )

        with pytest.raises(TaskError, match="ambiguous"):
            find_task(tmp_path, "TASK-001")


# ---------------------------------------------------------------------------
# Status gate
# ---------------------------------------------------------------------------


class TestStatusGate:
    def _task(self, tmp_path: Path, status: str) -> Task:
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Status Test",
            status,
            filename=f"TASK-001-{status.lower()}.md",
        )
        return parse_task(path)

    def test_ready_is_executable(self, tmp_path: Path):
        task = self._task(tmp_path, "READY")
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is True

    def test_rework_is_executable(self, tmp_path: Path):
        task = self._task(tmp_path, "REWORK")
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is True

    @pytest.mark.parametrize(
        "status",
        ["DRAFT", "REVIEW", "APPROVED", "BLOCKED", "IN_PROGRESS"],
    )
    def test_non_executable_statuses_are_rejected(self, tmp_path: Path, status: str):
        task = self._task(tmp_path, status)
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is False
        assert status in " ".join(result.messages)


# ---------------------------------------------------------------------------
# Branch gate
# ---------------------------------------------------------------------------


class TestBranchGate:
    def test_non_main_branch_passes(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is True
        assert any("not 'main'" in msg for msg in result.messages)

    def test_main_branch_fails(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "main", is_clean=True)
        assert result.ok is False
        assert any("main" in msg for msg in result.messages)


# ---------------------------------------------------------------------------
# Working-tree gate
# ---------------------------------------------------------------------------


class TestWorkingTreeGate:
    def test_clean_tree_passes(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "feature-branch", is_clean=True)
        assert result.ok is True

    def test_dirty_tree_fails(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "feature-branch", is_clean=False)
        assert result.ok is False
        assert any("uncommitted" in msg for msg in result.messages)


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------


class TestPromptGeneration:
    def test_instruction_references_agents_md_and_one_task_path(self):
        instruction = build_worker_instruction(
            "tasks/TASK-005-local-agent-runner-foundation.md"
        )

        assert "Read AGENTS.md" in instruction
        assert instruction.count("tasks/") == 1
        assert "tasks/TASK-005-local-agent-runner-foundation.md" in instruction
        assert "Execute" in instruction
        assert "completion report" in instruction

    def test_instruction_contains_approval_gate(self):
        instruction = build_worker_instruction("tasks/TASK-001.md")

        assert "Do not commit" in instruction
        assert "until explicitly approved" in instruction

    def test_instruction_does_not_embed_full_task_spec(self, tmp_path: Path):
        long_content = "Business context: " + "x " * 500
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Long Task",
            "READY",
            content=long_content,
        )

        instruction = build_worker_instruction(f"tasks/{path.name}")

        assert "Business context" not in instruction
        assert len(instruction) < 500


# ---------------------------------------------------------------------------
# Worker adapter boundary
# ---------------------------------------------------------------------------


@dataclass
class FakeWorkerAdapter(WorkerAdapter):
    """Test-only worker adapter that records invocations and returns canned output."""

    name_value: str = "fake"
    return_success: bool = True
    return_message: str = "fake worker ran"
    recorded: list[tuple[str, Path]] | None = None

    @property
    def name(self) -> str:
        return self.name_value

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return ["fake-worker", instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        if self.recorded is None:
            self.recorded = []
        self.recorded.append((instruction, working_dir))
        return WorkerResult(
            success=self.return_success,
            command=self.build_command(instruction, working_dir),
            message=self.return_message,
        )


class TestWorkerAdapterBoundary:
    def test_dry_run_adapter_never_executes(self):
        adapter = DryRunWorkerAdapter()
        result = adapter.run("instruction", Path("/tmp"))

        assert result.success is True
        assert "not be launched" in result.message
        assert adapter.build_command("x", Path("/tmp")) == []

    def test_kimi_adapter_builds_safe_prompt_command(self):
        adapter = KimiWorkerAdapter()
        command = adapter.build_command("do work", Path("/tmp"))

        assert command == ["kimi", "--prompt", "do work"]
        assert "--auto" not in command
        assert "--yolo" not in command

    def test_fake_adapter_can_be_used_in_tests(self, tmp_path: Path):
        fake = FakeWorkerAdapter()
        result = fake.run("instruction", tmp_path)

        assert result.success is True
        assert fake.recorded == [("instruction", tmp_path)]

    def test_worker_failure_is_controlled(self, tmp_path: Path):
        fake = FakeWorkerAdapter(return_success=False, return_message="boom")
        result = fake.run("instruction", tmp_path)

        assert result.success is False
        assert result.message == "boom"

    def test_kimi_adapter_reports_missing_executable(self, tmp_path: Path):
        adapter = KimiWorkerAdapter(executable="definitely-not-kimi")
        result = adapter.run("instruction", tmp_path)

        assert result.success is False
        assert "not found in PATH" in result.message


# ---------------------------------------------------------------------------
# Runner plan / execute
# ---------------------------------------------------------------------------


def _patch_git_info(repo_root: Path, branch: str, clean: bool):
    """Return a patch target that replaces ``get_git_info`` with a fake."""

    def _fake_get_git_info(cwd=None):
        return GitInfo(
            repo_root=repo_root,
            current_branch=branch,
            is_clean=clean,
            status_lines=[] if clean else ["?? some-file.py"],
        )

    return patch(
        "advancore.agent_runner.runner.get_git_info",
        side_effect=_fake_get_git_info,
    )


class TestRunnerPlan:
    def test_plan_succeeds_for_valid_ready_task(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "agent-control-foundation", True):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.PLANNING
        assert result.task.task_id == "TASK-001"
        assert result.validation.ok is True
        assert "Read AGENTS.md" in result.worker_instruction
        assert result.worker_command == []

    def test_plan_fails_on_main_branch(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "main", True):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.FAILED
        assert "main" in " ".join(result.messages)

    def test_plan_fails_on_dirty_tree(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "feature-branch", False):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.FAILED
        assert "uncommitted" in " ".join(result.messages)

    def test_plan_fails_for_non_ready_status(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Draft Task", "DRAFT")

        with _patch_git_info(repo_root, "feature-branch", True):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.FAILED
        assert "DRAFT" in " ".join(result.messages)

    def test_plan_does_not_launch_subprocess(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "feature-branch", True):
            with patch("advancore.agent_runner.worker.subprocess.run") as mock_run:
                result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.PLANNING
        mock_run.assert_not_called()

    def test_plan_does_not_run_git_mutation_commands(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with patch(
            "advancore.agent_runner.git_info.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=str(repo_root) + "\nagent-control-foundation\n",
                stderr="",
            )
            plan(tasks_dir, "TASK-001")

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "reset" not in args
            assert "checkout" not in args
            assert "merge" not in args
            assert "push" not in args
            assert "commit" not in args


class TestRunnerExecute:
    def test_execute_with_fake_worker_awaits_approval(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        fake = FakeWorkerAdapter()

        with _patch_git_info(repo_root, "feature-branch", True):
            result = execute(tasks_dir, "TASK-001", worker=fake)

        assert result.status == RunnerStatus.AWAITING_APPROVAL
        assert fake.recorded
        assert "approval" in " ".join(result.messages).lower()

    def test_execute_with_failing_worker_reports_failure(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        fake = FakeWorkerAdapter(return_success=False, return_message="worker error")

        with _patch_git_info(repo_root, "feature-branch", True):
            result = execute(tasks_dir, "TASK-001", worker=fake)

        assert result.status == RunnerStatus.WORKER_FAILED
        assert "worker error" in " ".join(result.messages)

    def test_execute_does_not_launch_worker_when_validation_fails(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        fake = FakeWorkerAdapter()

        with _patch_git_info(repo_root, "main", True):
            result = execute(tasks_dir, "TASK-001", worker=fake)

        assert result.status == RunnerStatus.FAILED
        assert fake.recorded is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_plan_returns_zero_for_valid_task(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.runner.get_git_info",
            lambda cwd=None: GitInfo(
                repo_root=repo_root,
                current_branch="feature-branch",
                is_clean=True,
                status_lines=[],
            ),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["plan", "TASK-001"])
        assert code == 0

    def test_cli_plan_returns_nonzero_for_failed_validation(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.runner.get_git_info",
            lambda cwd=None: GitInfo(
                repo_root=repo_root,
                current_branch="main",
                is_clean=True,
                status_lines=[],
            ),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["plan", "TASK-001"])
        assert code == 1
