"""Tests for the governed auto-pipeline (TASK-017).

These tests are fully isolated: they use temporary directories and mock Git,
subprocess, and worker interactions so they do not depend on the state of the
real repository, on Kimi Code being installed, or on the full pytest suite
actually running.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner import (
    AutoPipelineResult,
    AutoPipelineStatus,
    DiffCheckResult,
    KimiSwarmWorkerAdapter,
    PytestResult,
    RepairAttempt,
    RepairConfig,
    RepairStatus,
    WorkerAdapter,
    WorkerResult,
    classify_repair_status,
    parse_task,
    parse_task_allowed_scope,
    run_auto_pipeline,
)
from advancore.agent_runner.auto_pipeline import (
    AutoArtifactWriteError,
    ScopeResult,
    build_repair_evidence,
    build_repair_instruction,
    build_scope_result,
    format_auto_pipeline_report,
    run_git_diff_check,
    run_pytest,
    write_auto_artifact,
)
from advancore.agent_runner.worker import build_kimi_swarm_instruction
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
    allowed_scope: list[str] | None = None,
) -> Path:
    """Write a task file and return its path."""
    filename = filename or f"{task_id}-sample-task.md"
    path = tasks_dir / filename
    body = content if content is not None else "Do the thing."
    text = f"# {task_id} — {title}\n\nSTATUS: {status}\n\n## Objective\n\n{body}\n"
    if allowed_scope is not None:
        text += "\n## Allowed changed-file scope\n\n"
        for i, scope_path in enumerate(allowed_scope, 1):
            text += f"{i}. `{scope_path}`\n"
    path.write_text(text, encoding="utf-8")
    return path


def _git_info(
    repo_root: Path,
    branch: str = "agent-control-foundation",
    head_sha: str = "abc1230000000000000000000000000000000000",
    clean: bool = True,
    status_lines: list[str] | None = None,
) -> GitInfo:
    return GitInfo(
        repo_root=repo_root,
        current_branch=branch,
        head_sha=head_sha,
        is_clean=clean,
        status_lines=status_lines or [],
    )


def _sequence_git_info(*snapshots: GitInfo):
    iterator = iter(snapshots)

    def _fake(cwd=None):
        return next(iterator)

    return _fake


def _patch_sequence_git_info(*snapshots: GitInfo):
    return patch(
        "advancore.agent_runner.runner.get_git_info",
        side_effect=_sequence_git_info(*snapshots),
    )


@contextmanager
def _patch_sequence_git_info_for_repair(*snapshots: GitInfo):
    """Patch get_git_info in both runner and auto_pipeline for repair tests.

    The initial ``execute()`` call consumes the first two snapshots from the
    runner patch; each repair attempt consumes two snapshots from the
    auto_pipeline patch. Both patches share the same iterator so the overall
    order of Git snapshots is preserved.
    """
    from contextlib import ExitStack

    snapshots_list = list(snapshots)
    side_effect = _sequence_git_info(*snapshots_list)
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "advancore.agent_runner.runner.get_git_info",
                side_effect=side_effect,
            )
        )
        stack.enter_context(
            patch(
                "advancore.agent_runner.auto_pipeline.get_git_info",
                side_effect=side_effect,
            )
        )
        yield


def _patch_detect_staged_paths(paths: list[str] | None = None):
    return patch(
        "advancore.agent_runner.auto_pipeline.detect_staged_paths",
        return_value=paths or [],
    )


@dataclass
class FakeWorkerAdapter(WorkerAdapter):
    """Test-only worker adapter that records invocations and returns canned output."""

    name_value: str = "fake"
    return_success: bool = True
    return_message: str = "fake worker ran"
    return_success_sequence: list[bool] | None = None
    recorded: list[tuple[str, Path]] | None = None
    _sequence_index: int = 0

    @property
    def name(self) -> str:
        return self.name_value

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return ["fake-worker", instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        if self.recorded is None:
            self.recorded = []
        self.recorded.append((instruction, working_dir))

        if self.return_success_sequence is not None:
            if self._sequence_index < len(self.return_success_sequence):
                success = self.return_success_sequence[self._sequence_index]
            else:
                success = self.return_success
            self._sequence_index += 1
        else:
            success = self.return_success

        return WorkerResult(
            success=success,
            command=self.build_command(instruction, working_dir),
            message=self.return_message,
        )


def _passing_pytest(repo_root: Path) -> PytestResult:
    return PytestResult(
        command=["python", "-m", "pytest", "tests/", "-v"],
        returncode=0,
        stdout="test_x.py::test_x PASSED\n1 passed in 0.01s",
        stderr="",
        passed_count=1,
        summary="1 passed",
    )


def _failing_pytest(repo_root: Path) -> PytestResult:
    return PytestResult(
        command=["python", "-m", "pytest", "tests/", "-v"],
        returncode=1,
        stdout="test_x.py::test_x FAILED\n1 failed in 0.01s",
        stderr="",
        passed_count=0,
        summary="1 failed",
    )


def _passing_diff_check(repo_root: Path) -> DiffCheckResult:
    return DiffCheckResult(
        commands=[["git", "diff", "--check"], ["git", "diff", "--cached", "--check"]],
        returncodes=[0, 0],
        stdout="",
        stderr="",
    )


def _failing_diff_check(repo_root: Path) -> DiffCheckResult:
    return DiffCheckResult(
        commands=[["git", "diff", "--check"], ["git", "diff", "--cached", "--check"]],
        returncodes=[1, 0],
        stdout="",
        stderr="error: trailing whitespace",
    )


def _sequence_runner(results: list):
    """Return a callable that yields results in order on each invocation."""
    index = 0

    def _runner(*args, **kwargs):
        nonlocal index
        if index >= len(results):
            raise RuntimeError("sequence runner exhausted")
        result = results[index]
        index += 1
        return result

    return _runner


def _sequence_git_info_list(*snapshots: GitInfo):
    """Return a list of get_git_info return values for patching."""
    return list(snapshots)


# ---------------------------------------------------------------------------
# Scope parsing helpers
# ---------------------------------------------------------------------------


class TestAllowedScopeParsing:
    def test_parse_scope_extracts_backtick_paths(self, tmp_path: Path):
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Scope Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py", "tests/test_x.py"],
        )
        scope = parse_task_allowed_scope(path)
        assert scope == ["advancore/agent_runner/auto_pipeline.py", "tests/test_x.py"]

    def test_missing_scope_section_returns_none(self, tmp_path: Path):
        path = _write_task(tmp_path, "TASK-001", "No Scope", "READY")
        assert parse_task_allowed_scope(path) is None

    def test_scope_section_without_paths_returns_empty(self, tmp_path: Path):
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Empty Scope",
            "READY",
            content="## Allowed changed-file scope\n\nNo paths here.\n",
        )
        # Because content is in Objective section, the scope section will be appended empty.
        path.write_text(
            path.read_text(encoding="utf-8")
            .replace("## Allowed changed-file scope\n\nNo paths here.\n", "")
            + "\n## Allowed changed-file scope\n\nJust text.\n",
            encoding="utf-8",
        )
        scope = parse_task_allowed_scope(path)
        assert scope == []


class TestScopeValidation:
    def test_allowed_actual_paths_pass(self):
        result = build_scope_result(
            ["advancore/agent_runner/auto_pipeline.py"],
            ["advancore/agent_runner/auto_pipeline.py"],
        )
        assert result.ok is True
        assert result.out_of_scope_paths == []

    def test_actual_path_outside_scope_fails(self):
        result = build_scope_result(
            ["advancore/agent_runner/auto_pipeline.py"],
            ["advancore/agent_runner/other.py"],
        )
        assert result.ok is False
        assert "advancore/agent_runner/other.py" in result.out_of_scope_paths

    def test_untracked_file_outside_scope_fails(self):
        result = build_scope_result(
            ["advancore/agent_runner/auto_pipeline.py"],
            ["secret.txt"],
        )
        assert result.ok is False
        assert "secret.txt" in result.out_of_scope_paths

    def test_allowed_untracked_file_passes(self):
        result = build_scope_result(
            ["advancore/agent_runner/auto_pipeline.py", "notes.txt"],
            ["notes.txt"],
        )
        assert result.ok is True

    def test_missing_required_scope_fails(self):
        result = build_scope_result(None, ["file.py"], require_scope=True)
        assert result.ok is False
        assert result.missing_scope is True

    def test_missing_scope_not_required_passes(self):
        result = build_scope_result(None, ["file.py"], require_scope=False)
        assert result.ok is True

    def test_unsafe_allowed_path_fails(self):
        result = build_scope_result(["../escape.py"], ["../escape.py"])
        assert result.ok is False
        assert result.unsafe_allowed_paths == ["../escape.py"]

    def test_absolute_allowed_path_fails(self):
        result = build_scope_result(["/etc/passwd"], ["/etc/passwd"])
        assert result.ok is False
        assert "/etc/passwd" in result.unsafe_allowed_paths


# ---------------------------------------------------------------------------
# Full pipeline success/failure
# ---------------------------------------------------------------------------


class TestAutoPipelineSuccess:
    def test_ready_task_successful_worker_passing_tests_ready_for_approval(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M advancore/agent_runner/auto_pipeline.py"],
        )
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert result.task is not None
        assert result.task.task_id == "TASK-018"
        assert result.worker_result is not None
        assert result.worker_result.success is True
        assert result.pytest_result is not None
        assert result.pytest_result.ok is True
        assert result.diff_check_result is not None
        assert result.diff_check_result.ok is True
        assert result.scope_result is not None
        assert result.scope_result.ok is True
        assert result.review_bundle_path is not None
        assert result.auto_artifact_path is not None
        assert result.auto_artifact_path.exists()

    def test_review_bundle_and_audit_paths_are_recorded(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.review_bundle_path is not None
        assert result.audit_path is not None


class TestAutoPipelineValidationFailures:
    def test_dirty_tree_rejected_before_worker_launch(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        dirty = _git_info(repo_root, clean=False, status_lines=["?? dirty.txt"])
        fake = FakeWorkerAdapter()

        with patch(
            "advancore.agent_runner.runner.get_git_info",
            return_value=dirty,
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.VALIDATION_FAILED
        assert fake.recorded is None
        assert result.validation is not None
        assert any("uncommitted" in msg for msg in result.validation.messages)

    def test_main_branch_rejected_before_worker_launch(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        main_info = _git_info(repo_root, branch="main")
        fake = FakeWorkerAdapter()

        with patch(
            "advancore.agent_runner.runner.get_git_info",
            return_value=main_info,
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.VALIDATION_FAILED
        assert fake.recorded is None
        assert result.validation is not None
        assert any("main" in msg for msg in result.validation.messages)

    def test_non_executable_status_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "DRAFT",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        git_info = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with patch(
            "advancore.agent_runner.runner.get_git_info",
            return_value=git_info,
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.VALIDATION_FAILED
        assert fake.recorded is None
        assert result.validation is not None
        assert any("DRAFT" in msg for msg in result.validation.messages)

    def test_missing_allowed_scope_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-018", "Auto Pipeline Task", "READY")
        git_info = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with patch(
            "advancore.agent_runner.runner.get_git_info",
            return_value=git_info,
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.SCOPE_FAILED
        assert fake.recorded is None
        assert "missing" in " ".join(result.messages).lower()

    def test_unsafe_allowed_scope_path_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["../escape.py"],
        )
        git_info = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with patch(
            "advancore.agent_runner.runner.get_git_info",
            return_value=git_info,
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.SCOPE_FAILED
        assert fake.recorded is None
        assert "unsafe" in " ".join(result.messages).lower()


class TestAutoPipelineWorkerAndVerificationFailures:
    def test_worker_failure_stops_pipeline_before_pytest(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        fake = FakeWorkerAdapter(return_success=False, return_message="worker error")
        pytest_ran = []

        def _tracking_pytest(repo_root: Path):
            pytest_ran.append(True)
            return _passing_pytest(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_tracking_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.WORKER_FAILED
        assert pytest_ran == []
        assert result.pytest_result is None

    def test_pytest_failure_returns_test_failed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_failing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.TEST_FAILED
        assert result.pytest_result is not None
        assert result.pytest_result.ok is False

    def test_diff_check_failure_returns_diff_check_failed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_failing_diff_check,
            )

        assert result.status == AutoPipelineStatus.DIFF_CHECK_FAILED
        assert result.diff_check_result is not None
        assert result.diff_check_result.ok is False

    def test_tracked_modification_outside_scope_fails(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M advancore/agent_runner/other.py"],
        )

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.SCOPE_FAILED
        assert result.scope_result is not None
        assert "advancore/agent_runner/other.py" in result.scope_result.out_of_scope_paths

    def test_untracked_file_outside_scope_fails(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root, clean=False, status_lines=["?? secret.txt"])

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.SCOPE_FAILED
        assert "secret.txt" in result.scope_result.out_of_scope_paths

    def test_allowed_untracked_file_accepted(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=[
                "advancore/agent_runner/auto_pipeline.py",
                "notes.txt",
            ],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root, clean=False, status_lines=["?? notes.txt"])

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert "notes.txt" in result.scope_result.actual_paths

    def test_deleted_file_participates_in_scope_validation(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" D advancore/agent_runner/other.py"],
        )

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.SCOPE_FAILED
        assert "advancore/agent_runner/other.py" in result.scope_result.out_of_scope_paths

    def test_renamed_file_participates_in_scope_validation(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=["R  old.py -> advancore/agent_runner/auto_pipeline.py"],
        )

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert "advancore/agent_runner/auto_pipeline.py" in result.scope_result.actual_paths

    def test_renamed_file_new_path_outside_scope_fails(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=["R  old.py -> other.py"],
        )

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.SCOPE_FAILED
        assert "other.py" in result.scope_result.out_of_scope_paths

    def test_head_movement_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.POST_WORKER_VERIFICATION_FAILED
        assert result.pre_git_info.head_sha != result.post_git_info.head_sha

    def test_worker_created_staged_changes_fail_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths(
            ["advancore/agent_runner/auto_pipeline.py"]
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.status == AutoPipelineStatus.SCOPE_FAILED
        assert result.staged_paths == ["advancore/agent_runner/auto_pipeline.py"]


class TestAutoPipelineArtifactAndAudit:
    def test_auto_artifact_excludes_sensitive_content(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            content="Business secret: password=abc token=xyz",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        assert result.auto_artifact_path is not None
        raw = result.auto_artifact_path.read_text(encoding="utf-8")
        assert "password" not in raw.lower()
        assert "token" not in raw.lower()
        assert "Business secret" not in raw

    def test_auto_artifact_write_failure_is_reported(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            with patch(
                "advancore.agent_runner.auto_pipeline.write_auto_artifact"
            ) as mock_write:
                mock_write.side_effect = AutoArtifactWriteError("disk full")
                result = run_auto_pipeline(
                    tasks_dir,
                    "TASK-018",
                    worker=FakeWorkerAdapter(),
                    pytest_runner=_passing_pytest,
                    diff_check_runner=_passing_diff_check,
                )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert result.auto_artifact_write_ok is False
        assert "disk full" in " ".join(result.messages)

    def test_audit_write_failure_is_reported(self, tmp_path: Path):
        from advancore.agent_runner.audit import AuditWriteError

        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            with patch(
                "advancore.agent_runner.runner.write_audit_record"
            ) as mock_write:
                mock_write.side_effect = AuditWriteError("disk full")
                result = run_auto_pipeline(
                    tasks_dir,
                    "TASK-018",
                    worker=FakeWorkerAdapter(),
                    pytest_runner=_passing_pytest,
                    diff_check_runner=_passing_diff_check,
                )

        assert result.audit_write_ok is False
        assert "disk full" in " ".join(result.messages)


class TestKimiSwarmWorkerAdapter:
    def test_swarm_adapter_uses_prompt_boundary(self):
        adapter = KimiSwarmWorkerAdapter(
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"]
        )
        command = adapter.build_swarm_command(
            "tasks/TASK-018-auto-pipeline.md", Path("/tmp/repo")
        )
        assert command[0] == "kimi"
        assert "--prompt" in command
        assert "AgentSwarm" in command[command.index("--prompt") + 1]
        assert "--auto" not in command
        assert "--yolo" not in command
        assert "-y" not in command

    def test_swarm_instruction_includes_scope_and_governance(self):
        instruction = build_kimi_swarm_instruction(
            "tasks/TASK-018-auto-pipeline.md",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        assert "AgentSwarm" in instruction
        assert "allowed changed-file scope" in instruction.lower()
        assert "advancore/agent_runner/auto_pipeline.py" in instruction
        assert "Do NOT stage, commit, push, merge" in instruction
        assert "Do NOT declare" in instruction

    def test_swarm_adapter_reports_missing_executable(self, tmp_path: Path):
        adapter = KimiSwarmWorkerAdapter(executable="definitely-not-kimi")
        result = adapter.run("instruction", tmp_path)
        assert result.success is False
        assert "not found in PATH" in result.message


class TestAutoPipelineReport:
    def test_report_contains_required_fields(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        report = format_auto_pipeline_report(result)
        assert "TASK-018" in report
        assert result.git_info.current_branch in report
        assert result.pre_git_info.head_sha in report
        assert result.post_git_info.head_sha in report
        assert "READY FOR CONTROLLER/OWNER REVIEW" in report
        assert "NO staging / commit / push / merge performed" in report
        assert "review bundle" in report.lower()
        assert "pytest" in report.lower()
        assert "diff check" in report.lower()
        assert "allowed paths" in report.lower()
        assert "actual paths" in report.lower()

    def test_report_excludes_full_task_body(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            content="Business secret: password=abc token=xyz",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=FakeWorkerAdapter(),
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
            )

        report = format_auto_pipeline_report(result)
        assert "password" not in report.lower()
        assert "Business secret" not in report


class TestAutoPipelineNoPublicationSideEffects:
    def test_auto_pipeline_never_runs_git_publication_commands(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            with patch(
                "advancore.agent_runner.auto_pipeline._run"
            ) as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="",
                    stderr="",
                )
                run_auto_pipeline(
                    tasks_dir,
                    "TASK-018",
                    worker=FakeWorkerAdapter(),
                    pytest_runner=_passing_pytest,
                    diff_check_runner=_passing_diff_check,
                )

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "add" not in args
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "checkout" not in args
            assert "switch" not in args
            assert "reset" not in args
            assert "rebase" not in args



# ---------------------------------------------------------------------------
# Bounded autonomous repair loop (TASK-018)
# ---------------------------------------------------------------------------


class TestRepairClassification:
    def test_classify_repair_status_recoverable_failures(self):
        assert classify_repair_status(AutoPipelineStatus.TEST_FAILED) == RepairStatus.REPAIRABLE
        assert classify_repair_status(AutoPipelineStatus.DIFF_CHECK_FAILED) == RepairStatus.REPAIRABLE
        assert classify_repair_status(AutoPipelineStatus.WORKER_FAILED) == RepairStatus.REPAIRABLE

    def test_classify_repair_status_non_repairable_failures(self):
        assert classify_repair_status(AutoPipelineStatus.VALIDATION_FAILED) == RepairStatus.NON_REPAIRABLE
        assert classify_repair_status(AutoPipelineStatus.POST_WORKER_VERIFICATION_FAILED) == RepairStatus.NON_REPAIRABLE
        assert classify_repair_status(AutoPipelineStatus.SCOPE_FAILED) == RepairStatus.NON_REPAIRABLE
        assert classify_repair_status(AutoPipelineStatus.ARTIFACT_FAILED) == RepairStatus.NON_REPAIRABLE
        assert classify_repair_status(AutoPipelineStatus.NON_REPAIRABLE) == RepairStatus.NON_REPAIRABLE
        assert classify_repair_status(AutoPipelineStatus.REPAIR_EXHAUSTED) == RepairStatus.NON_REPAIRABLE

    def test_repair_config_clamps_to_approved_range(self):
        assert RepairConfig(max_attempts=-1).max_attempts == 0
        assert RepairConfig(max_attempts=0).max_attempts == 0
        assert RepairConfig(max_attempts=1).max_attempts == 1
        assert RepairConfig(max_attempts=2).max_attempts == 2
        assert RepairConfig(max_attempts=5).max_attempts == 2


class TestRepairInstruction:
    def test_repair_instruction_contains_required_fields(self, tmp_path: Path):
        task_path = _write_task(
            tmp_path,
            "TASK-018",
            "Repair Instruction Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        task = parse_task(task_path)
        instruction = build_repair_instruction(
            task=task,
            attempt_number=1,
            max_attempts=2,
            triggering_gate="TEST_FAILED",
            evidence={"pytest_returncode": 1, "pytest_summary": "1 failed"},
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        assert "TASK-018" in instruction
        assert "tasks/TASK-018" in instruction
        assert "TEST_FAILED" in instruction
        assert "Attempt: 1 of 2" in instruction
        assert "pytest_returncode" in instruction
        assert "Allowed changed-file scope" in instruction
        assert "advancore/agent_runner/auto_pipeline.py" in instruction
        assert "Do NOT stage, commit, push, merge" in instruction
        assert "Do NOT declare" in instruction
        assert "Do not use --auto, --yolo" in instruction
        assert "permission-bypass" in instruction

    def test_repair_instruction_excludes_full_transcripts_and_secrets(self, tmp_path: Path):
        task_path = _write_task(
            tmp_path,
            "TASK-018",
            "Repair Instruction Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        task = parse_task(task_path)
        evidence = {
            "worker_message": "error",
            "secret": "password=abc token=xyz",  # should not appear in real use
        }
        instruction = build_repair_instruction(
            task=task,
            attempt_number=1,
            max_attempts=2,
            triggering_gate="WORKER_FAILED",
            evidence=evidence,
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        # Even if evidence is malformed, the instruction must not expand environment/repo dumps.
        assert "ENV" not in instruction
        assert "stdout" not in instruction.lower() or "worker_message" in instruction


class TestRepairEvidence:
    def test_build_repair_evidence_for_pytest(self):
        result = AutoPipelineResult(
            status=AutoPipelineStatus.TEST_FAILED,
            pytest_result=_failing_pytest(Path("/tmp")),
        )
        evidence = build_repair_evidence(result)
        assert evidence["triggering_gate"] == "TEST_FAILED"
        assert evidence["pytest_returncode"] == 1
        assert evidence["pytest_summary"] == "1 failed"

    def test_build_repair_evidence_for_diff_check(self):
        result = AutoPipelineResult(
            status=AutoPipelineStatus.DIFF_CHECK_FAILED,
            diff_check_result=_failing_diff_check(Path("/tmp")),
        )
        evidence = build_repair_evidence(result)
        assert evidence["triggering_gate"] == "DIFF_CHECK_FAILED"
        assert evidence["diff_check_returncodes"] == [1, 0]
        assert "trailing whitespace" in evidence["diff_check_error_summary"]

    def test_build_repair_evidence_truncates_long_stderr(self):
        long_stderr = "x" * 1000
        result = AutoPipelineResult(
            status=AutoPipelineStatus.DIFF_CHECK_FAILED,
            diff_check_result=DiffCheckResult(
                commands=[],
                returncodes=[1, 0],
                stdout="",
                stderr=long_stderr,
            ),
        )
        evidence = build_repair_evidence(result)
        assert len(evidence["diff_check_error_summary"]) <= 500


class TestRepairLoopSuccess:
    def test_repair_disabled_preserves_task_017_behavior(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_failing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=0,
            )

        assert result.status == AutoPipelineStatus.TEST_FAILED
        assert len(fake.recorded) == 1  # only initial worker
        assert result.repair_attempts == []
        assert result.max_repair_attempts == 0

    def test_pytest_failure_repairable_and_succeeds_on_first_attempt(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()
        pytest_ran = []

        pytest_runner = _sequence_runner([_failing_pytest(repo_root), _passing_pytest(repo_root)])

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=pytest_runner,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert len(fake.recorded) == 2  # initial + repair
        assert len(result.repair_attempts) == 1
        attempt = result.repair_attempts[0]
        assert attempt.attempt_number == 1
        assert attempt.triggering_gate == "TEST_FAILED"
        assert attempt.status == RepairStatus.SUCCEEDED
        assert attempt.verification_status == "READY_FOR_APPROVAL"
        assert attempt.worker_type == "fake"
        assert pytest_runner  # used

    def test_diff_check_failure_repairable_and_succeeds_after_two_attempts(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair1_pre = _git_info(repo_root)
        repair1_post = _git_info(repo_root)
        repair2_pre = _git_info(repo_root)
        repair2_post = _git_info(repo_root)
        fake = FakeWorkerAdapter(return_success_sequence=[True, True])
        diff_check_runner = _sequence_runner(
            [
                _failing_diff_check(repo_root),
                _failing_diff_check(repo_root),
                _passing_diff_check(repo_root),
            ]
        )

        with _patch_sequence_git_info_for_repair(
            pre, post, repair1_pre, repair1_post, repair2_pre, repair2_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=diff_check_runner,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert len(fake.recorded) == 3  # initial + 2 repairs
        assert len(result.repair_attempts) == 2
        assert result.repair_attempts[0].status == RepairStatus.FAILED
        assert result.repair_attempts[1].status == RepairStatus.SUCCEEDED
        assert result.repair_attempts[1].verification_status == "READY_FOR_APPROVAL"

    def test_worker_failure_repairable_and_succeeds(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter(return_success_sequence=[False, True])

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert len(fake.recorded) == 2
        assert len(result.repair_attempts) == 1
        assert result.repair_attempts[0].triggering_gate == "WORKER_FAILED"
        assert result.repair_attempts[0].status == RepairStatus.SUCCEEDED


class TestRepairLoopEscalation:
    def test_missing_scope_is_non_repairable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-018", "No Scope Task", "READY")
        git_info = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with patch(
            "advancore.agent_runner.runner.get_git_info",
            return_value=git_info,
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.NON_REPAIRABLE
        assert fake.recorded is None
        assert result.repair_attempts == []

    def test_unsafe_scope_is_non_repairable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Unsafe Scope Task",
            "READY",
            allowed_scope=["../escape.py"],
        )
        git_info = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with patch(
            "advancore.agent_runner.runner.get_git_info",
            return_value=git_info,
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.NON_REPAIRABLE
        assert fake.recorded is None

    def test_staged_paths_detected_are_non_repairable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths(
            ["advancore/agent_runner/auto_pipeline.py"]
        ):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.NON_REPAIRABLE
        assert len(fake.recorded) == 1  # initial worker only
        assert result.repair_attempts == []
        assert result.staged_paths == ["advancore/agent_runner/auto_pipeline.py"]

    def test_head_movement_is_non_repairable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.NON_REPAIRABLE
        assert len(fake.recorded) == 1
        assert result.repair_attempts == []

    def test_out_of_scope_changes_non_repairable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M advancore/agent_runner/other.py"],
        )
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.NON_REPAIRABLE
        assert len(fake.recorded) == 1
        assert result.repair_attempts == []
        assert "advancore/agent_runner/other.py" in result.scope_result.out_of_scope_paths

    def test_repair_budget_exhausted(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair1_pre = _git_info(repo_root)
        repair1_post = _git_info(repo_root)
        repair2_pre = _git_info(repo_root)
        repair2_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()
        pytest_runner = _sequence_runner(
            [
                _failing_pytest(repo_root),
                _failing_pytest(repo_root),
                _failing_pytest(repo_root),
            ]
        )

        with _patch_sequence_git_info_for_repair(
            pre, post, repair1_pre, repair1_post, repair2_pre, repair2_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=pytest_runner,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.REPAIR_EXHAUSTED
        assert len(fake.recorded) == 3  # initial + 2 repairs
        assert len(result.repair_attempts) == 2
        assert result.repair_attempts[0].status == RepairStatus.FAILED
        assert result.repair_attempts[1].status == RepairStatus.FAILED

    def test_non_repairable_failure_does_not_consume_budget(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info(pre, post), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.NON_REPAIRABLE
        assert len(fake.recorded) == 1
        assert len(result.repair_attempts) == 0


class TestRepairLoopVerification:
    def test_full_pytest_reruns_after_repair(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()
        pytest_runs: list[Path] = []

        def _tracking_pytest(repo_root: Path):
            pytest_runs.append(repo_root)
            if len(pytest_runs) == 1:
                return _failing_pytest(repo_root)
            return _passing_pytest(repo_root)

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_tracking_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert len(pytest_runs) == 2

    def test_diff_check_reruns_after_repair(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()
        diff_check_runs: list[Path] = []

        def _tracking_diff_check(repo_root: Path):
            diff_check_runs.append(repo_root)
            if len(diff_check_runs) == 1:
                return _failing_diff_check(repo_root)
            return _passing_diff_check(repo_root)

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_tracking_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert len(diff_check_runs) == 2

    def test_scope_verification_reruns_after_repair(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root, clean=False, status_lines=["?? secret.txt"])
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_passing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.NON_REPAIRABLE
        # Initial scope failed; non-repairable, so scope verification ran once.
        assert result.scope_result is not None
        assert "secret.txt" in result.scope_result.out_of_scope_paths


class TestRepairLoopAuditAndReport:
    def test_auto_artifact_contains_repair_metadata(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()
        pytest_runner = _sequence_runner(
            [_failing_pytest(repo_root), _passing_pytest(repo_root)]
        )

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=pytest_runner,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
        assert result.auto_artifact_path is not None
        lines = result.auto_artifact_path.read_text(encoding="utf-8").strip().splitlines()
        last_record = json.loads(lines[-1])
        assert last_record["max_repair_attempts"] == 2
        assert len(last_record["repair_attempts"]) == 1
        assert last_record["repair_attempts"][0]["attempt_number"] == 1
        assert last_record["repair_attempts"][0]["status"] == "SUCCEEDED"

    def test_report_shows_repair_attempts_and_status(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()
        pytest_runner = _sequence_runner(
            [_failing_pytest(repo_root), _passing_pytest(repo_root)]
        )

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=pytest_runner,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        report = format_auto_pipeline_report(result)
        assert "Repair attempts used: 1" in report
        assert "attempt 1: SUCCEEDED" in report
        assert "READY FOR CONTROLLER/OWNER REVIEW" in report
        assert "Controller/owner action required: no" in report

    def test_exhausted_report_shows_owner_action_required(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]):
            result = run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=_failing_pytest,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=1,
            )

        assert result.status == AutoPipelineStatus.REPAIR_EXHAUSTED
        report = format_auto_pipeline_report(result)
        assert "Repair attempts used: 1" in report
        assert "REPAIR_EXHAUSTED" in report
        assert "Controller/owner action required: yes" in report


class TestRepairLoopNoPublication:
    def test_repair_never_runs_git_publication_commands(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-018",
            "Auto Pipeline Task",
            "READY",
            allowed_scope=["advancore/agent_runner/auto_pipeline.py"],
        )
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        repair_pre = _git_info(repo_root)
        repair_post = _git_info(repo_root)
        fake = FakeWorkerAdapter()
        pytest_runner = _sequence_runner(
            [_failing_pytest(repo_root), _passing_pytest(repo_root)]
        )

        with _patch_sequence_git_info_for_repair(
            pre, post, repair_pre, repair_post
        ), _patch_detect_staged_paths([]), patch(
            "advancore.agent_runner.auto_pipeline._run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            run_auto_pipeline(
                tasks_dir,
                "TASK-018",
                worker=fake,
                pytest_runner=pytest_runner,
                diff_check_runner=_passing_diff_check,
                max_repair_attempts=2,
            )

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "add" not in args
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "checkout" not in args
            assert "switch" not in args
            assert "reset" not in args
            assert "rebase" not in args


class TestRepairCLIOption:
    def test_cli_auto_supports_repair_attempts_option(self):
        from advancore.agent_runner.__main__ import main

        with patch("advancore.agent_runner.__main__.run_auto_pipeline") as mock_run, patch(
            "advancore.agent_runner.__main__.get_git_info"
        ) as mock_git:
            mock_git.return_value = GitInfo(
                repo_root=Path("/tmp/repo"),
                current_branch="agent-control-foundation",
                head_sha="abc123",
                is_clean=True,
                status_lines=[],
            )
            mock_run.return_value = AutoPipelineResult(
                status=AutoPipelineStatus.READY_FOR_APPROVAL,
                max_repair_attempts=2,
            )
            with patch("advancore.agent_runner.__main__.print"):
                exit_code = main(["auto", "TASK-018", "--repair-attempts", "2"])

        assert exit_code == 0
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["max_repair_attempts"] == 2
