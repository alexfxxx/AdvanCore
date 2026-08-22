"""Tests for the end-to-end controller orchestration layer (TASK-021).

These tests are fully isolated: they use temporary directories and mock Git,
worker, planner, and pipeline interactions so they do not depend on the state
of the real repository or on Kimi Code being installed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner.controller_adapter import (
    AdapterResultState,
    ControllerAdapterResult,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    DecisionValue,
    build_controller_decision,
    default_decisions_dir,
    write_controller_decision,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoff,
    build_controller_handoff,
    default_handoff_dir,
    write_controller_handoff,
)
from advancore.agent_runner.finalize import FinalizationResult, FinalizationStatus
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.goal_task import (
    GoalTaskGenerationResult,
    GoalTaskGenerationStatus,
)
from advancore.agent_runner.lifecycle import ActorRole, TaskStatus, transition_task
from advancore.agent_runner.auto_pipeline import (
    AutoPipelineResult,
    AutoPipelineStatus,
)
from advancore.agent_runner.orchestration import (
    MAX_REPAIR_ATTEMPTS,
    MAX_REWORK_CYCLES,
    OrchestrationCheckpoint,
    OrchestrationConfig,
    OrchestrationError,
    OrchestrationPhase,
    OrchestrationResult,
    OrchestrationStatus,
    default_orchestration_dir,
    load_checkpoint,
    run_orchestration,
    save_checkpoint,
)
from advancore.agent_runner.review_bundle import (
    ReviewBundle,
    build_review_bundle,
    serialize_bundle,
)
from advancore.agent_runner.runner import PostWorkerVerification, RunnerResult, RunnerStatus
from advancore.agent_runner.task import Task, find_task
from advancore.agent_runner.worker import WorkerAdapter, WorkerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _write_task(
    tasks_dir: Path,
    task_id: str,
    title: str,
    status: str,
    filename: str | None = None,
    owner_decisions: list[str] | None = None,
    allowed_scope: list[str] | None = None,
) -> Path:
    """Write a task file and return its path."""
    filename = filename or f"{task_id}-sample-task.md"
    path = tasks_dir / filename
    text = f"# {task_id} — {title}\n\nSTATUS: {status}\n\n## Objective\n\nDo the thing.\n"
    if allowed_scope is not None:
        text += "\n## Allowed changed-file scope\n\n"
        for scope_path in allowed_scope:
            text += f"- `{scope_path}`\n"
    text += "\n## Owner decisions\n\n"
    if owner_decisions:
        for decision in owner_decisions:
            text += f"- {decision}\n"
    else:
        text += "- None.\n"
    path.write_text(text, encoding="utf-8")
    return path


def _patch_get_git_info(*snapshots: GitInfo):
    """Patch ``get_git_info`` in the orchestration module to return *snapshots*.

    The last snapshot is repeated indefinitely so the orchestrator can call
    ``get_git_info`` an arbitrary number of times during a test.
    """
    snapshots_list = list(snapshots)
    if not snapshots_list:
        raise ValueError("at least one GitInfo snapshot is required")

    def _fake(cwd=None):
        if len(snapshots_list) == 1:
            return snapshots_list[0]
        if len(snapshots_list) > 1:
            return snapshots_list.pop(0)
        return snapshots_list[0]

    return patch("advancore.agent_runner.orchestration.get_git_info", side_effect=_fake)


@dataclass
class FakeWorkerAdapter(WorkerAdapter):
    """Test-only worker/planner adapter that records invocations."""

    name_value: str = "fake"
    return_success: bool = True
    return_message: str = "fake worker ran"
    recorded: list[tuple[str, Path]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.name_value

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return ["fake-worker", instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        self.recorded.append((instruction, working_dir))
        return WorkerResult(
            success=self.return_success,
            command=self.build_command(instruction, working_dir),
            message=self.return_message,
        )


def _make_goal_task_result(
    repo_root: Path,
    tasks_dir: Path,
    task_id: str = "TASK-022",
    owner_decision_count: int = 0,
    ok: bool = True,
) -> GoalTaskGenerationResult:
    """Return a canned goal-task generation result."""
    task_path = tasks_dir / f"{task_id}-sample-task.md"
    artifact_path = repo_root / ".agent_runner" / "goal_task" / "goal_task.jsonl"
    return GoalTaskGenerationResult(
        ok=ok,
        status=GoalTaskGenerationStatus.DRAFT_CREATED,
        goal_accepted=True,
        planner_type="fake",
        planner_success=True,
        proposal_valid=True,
        task_id=task_id,
        task_path=task_path,
        task_written=ok,
        artifact_path=artifact_path if ok else None,
        owner_decision_count=owner_decision_count,
        messages=["Generated DRAFT task"],
    )


def _make_auto_result(
    repo_root: Path,
    task_id: str,
    status: str = "READY_FOR_APPROVAL",
    review_bundle_path: Path | None = None,
) -> AutoPipelineResult:
    """Return a canned AutoPipelineResult."""
    task_path = repo_root / "tasks" / f"{task_id}-sample-task.md"
    return AutoPipelineResult(
        status=AutoPipelineStatus(status),
        task=Task(
            task_id=task_id,
            title="Sample",
            status="READY",
            filename=f"{task_id}-sample-task.md",
            path=task_path,
        ),
        auto_artifact_path=repo_root / ".agent_runner" / "auto" / "auto_pipeline.jsonl",
        review_bundle_path=review_bundle_path,
        repair_attempts=[],
        messages=[f"auto-pipeline: {status}"],
    )


def _make_review_bundle(
    repo_root: Path, task_id: str, changed_paths: list[str]
) -> ReviewBundle:
    """Build a minimal review bundle."""
    task_path = repo_root / "tasks" / f"{task_id}-sample-task.md"
    runner_result = RunnerResult(
        status=RunnerStatus.AWAITING_APPROVAL,
        task=Task(
            task_id=task_id,
            title="Sample",
            status="READY",
            filename=f"{task_id}-sample-task.md",
            path=task_path,
        ),
        pre_git_info=_git_info(repo_root),
        post_git_info=_git_info(
            repo_root, clean=False, status_lines=[f" M {p}" for p in changed_paths]
        ),
        worker_result=WorkerResult(success=True),
        post_verification=PostWorkerVerification(
            ok=True, changed_paths=changed_paths
        ),
    )
    return build_review_bundle(runner_result)


def _write_bundle_file(bundle: ReviewBundle, bundle_path: Path) -> None:
    """Write *bundle* to *bundle_path* as JSON."""
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(serialize_bundle(bundle), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _make_decision(
    bundle: ReviewBundle,
    bundle_path: Path,
    decision: DecisionValue,
    actor: ActorRole = ActorRole.CONTROLLER,
) -> ControllerDecision:
    """Build a controller decision record against *bundle*."""
    return build_controller_decision(
        bundle_path=bundle_path,
        bundle=bundle,
        decision=decision,
        actor_role=actor,
        repo_root=bundle_path.parent.parent.parent,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfig:
    def test_repair_attempts_clamped(self):
        config = OrchestrationConfig(repair_attempts=-1)
        assert config.repair_attempts == 0
        config = OrchestrationConfig(repair_attempts=10)
        assert config.repair_attempts == MAX_REPAIR_ATTEMPTS

    def test_max_rework_clamped(self):
        config = OrchestrationConfig(max_rework=-1)
        assert config.max_rework == 0
        config = OrchestrationConfig(max_rework=10)
        assert config.max_rework == MAX_REWORK_CYCLES


# ---------------------------------------------------------------------------
# Preview / dry-run
# ---------------------------------------------------------------------------


class TestPreview:
    def test_preview_with_valid_goal_shows_plan_and_writes_nothing(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-021-existing.md").write_text("x")

        config = OrchestrationConfig(goal="Add feature", planner="dry-run")
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                result = run_orchestration(config, repo_root)

        assert result.ok is True
        assert result.status == OrchestrationStatus.AWAITING_TASK_APPROVAL.value
        assert result.task_id == "TASK-022"
        assert result.phase == OrchestrationPhase.TASK_DRAFT_GENERATION.value
        assert not (repo_root / ".agent_runner" / "orchestration").exists()
        assert not (tasks_dir / "TASK-022-sample-task.md").exists()

    def test_preview_with_owner_decisions_shows_owner_required(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-021-existing.md").write_text("x")

        config = OrchestrationConfig(goal="Add feature", planner="dry-run")
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                gen_result = _make_goal_task_result(
                    repo_root, tasks_dir, owner_decision_count=1
                )
                mock_gen.return_value = gen_result
                result = run_orchestration(config, repo_root)

        assert result.status == OrchestrationStatus.OWNER_DECISION_REQUIRED.value
        assert result.owner_decision_required is True

    def test_apply_with_empty_goal_fails_before_external_action(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        config = OrchestrationConfig(goal="   ", apply=True)
        with _patch_get_git_info(_git_info(repo_root)):
            result = run_orchestration(config, repo_root)

        assert result.ok is False
        assert result.status == OrchestrationStatus.FAILED.value
        assert "empty" in (result.blocking_reason or "").lower()

    def test_apply_with_oversized_goal_fails_before_external_action(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        config = OrchestrationConfig(goal="x" * 3000, apply=True)
        with _patch_get_git_info(_git_info(repo_root)):
            result = run_orchestration(config, repo_root)

        assert result.ok is False
        assert result.status == OrchestrationStatus.FAILED.value
        assert "exceeds" in (result.blocking_reason or "").lower()


# ---------------------------------------------------------------------------
# Goal-task generation and binding
# ---------------------------------------------------------------------------


class TaskDraftGeneration:
    def test_new_apply_delegates_once_to_goal_task_generation(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-021-existing.md").write_text("x")

        fake = FakeWorkerAdapter(name_value="fake-planner")
        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                gen_result = _make_goal_task_result(repo_root, tasks_dir)
                mock_gen.return_value = gen_result
                result = run_orchestration(config, repo_root)

        assert result.ok is False
        assert result.status == OrchestrationStatus.AWAITING_TASK_APPROVAL.value
        assert mock_gen.call_count == 1
        assert result.task_id == "TASK-022"

    def test_generated_draft_pauses_awaiting_task_approval(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-021-existing.md").write_text("x")
        _write_task(tasks_dir, "TASK-022", "Sample", "DRAFT")

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            result = run_orchestration(config, repo_root)

        assert result.status == OrchestrationStatus.AWAITING_TASK_APPROVAL.value
        assert result.controller_gate is None

    def test_worker_or_planner_cannot_authorize_ready_transition(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-021-existing.md").write_text("x")
        _write_task(tasks_dir, "TASK-022", "Sample", "DRAFT")

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            result = run_orchestration(config, repo_root)

        # Even if the fake planner/worker returned success, the task is DRAFT.
        assert result.status == OrchestrationStatus.AWAITING_TASK_APPROVAL.value


# ---------------------------------------------------------------------------
# Resume invariants
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_with_new_goal_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        checkpoint_path = default_orchestration_dir(repo_root) / "ORCH-test.json"
        checkpoint_path.parent.mkdir(parents=True)
        checkpoint_path.write_text(
            json.dumps(
                {
                    "schema_version": "advancore-orchestration-v1",
                    "run_id": "ORCH-test",
                    "goal_hash": "abcd",
                    "goal_summary": "summary",
                    "planner": "dry-run",
                    "worker": "dry-run",
                    "controller": "manual",
                    "repair_attempts": 0,
                    "max_rework": 0,
                    "apply": True,
                    "phase": "AWAITING_TASK_APPROVAL",
                    "completed_phases": ["GOAL_VALIDATION", "TASK_DRAFT_GENERATION"],
                    "task_id": "TASK-022",
                    "task_path": str(repo_root / "tasks" / "TASK-022-sample-task.md"),
                    "task_written": True,
                }
            ),
            encoding="utf-8",
        )

        config = OrchestrationConfig(
            goal="Different goal", resume_run_id="ORCH-test", apply=True
        )
        with pytest.raises(OrchestrationError, match="Cannot specify --goal"):
            run_orchestration(config, repo_root)

    def test_resume_with_unknown_checkpoint_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        config = OrchestrationConfig(resume_run_id="ORCH-missing", apply=True)
        with pytest.raises(OrchestrationError, match="Checkpoint not found"):
            run_orchestration(config, repo_root)

    def test_resume_with_malformed_checkpoint_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        checkpoint_path = default_orchestration_dir(repo_root) / "ORCH-bad.json"
        checkpoint_path.parent.mkdir(parents=True)
        checkpoint_path.write_text("not json", encoding="utf-8")

        config = OrchestrationConfig(resume_run_id="ORCH-bad", apply=True)
        with pytest.raises(OrchestrationError, match="Cannot read checkpoint"):
            run_orchestration(config, repo_root)

    def test_resume_with_unsupported_schema_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        checkpoint_path = default_orchestration_dir(repo_root) / "ORCH-old.json"
        checkpoint_path.parent.mkdir(parents=True)
        checkpoint_path.write_text(
            json.dumps(
                {
                    "schema_version": "advancore-orchestration-v0",
                    "run_id": "ORCH-old",
                }
            ),
            encoding="utf-8",
        )

        config = OrchestrationConfig(resume_run_id="ORCH-old", apply=True)
        with pytest.raises(OrchestrationError, match="Unsupported checkpoint schema"):
            run_orchestration(config, repo_root)

    def test_resume_with_task_id_mismatch_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "DRAFT")

        config = OrchestrationConfig(goal="Add feature", planner="dry-run", apply=True)
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                result = run_orchestration(config, repo_root)
        run_id = result.run_id

        # Mutate the checkpoint task_id to a different task.
        checkpoint_path = default_orchestration_dir(repo_root) / f"{run_id}.json"
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        data["task_id"] = "TASK-999"
        data["task_path"] = str(tasks_dir / "TASK-999-missing.md")
        checkpoint_path.write_text(json.dumps(data), encoding="utf-8")

        config = OrchestrationConfig(resume_run_id=run_id, apply=True)
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            result = run_orchestration(config, repo_root)

        # The orchestrator should fail when it cannot load the mismatched task.
        assert result.ok is False
        assert "Cannot load task" in (result.blocking_reason or "")

    def test_resume_with_branch_mismatch_reports_stale_evidence(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY")
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        _write_bundle_file(bundle, bundle_path)

        config = OrchestrationConfig(goal="Add feature", planner="dry-run", apply=True)
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    result = run_orchestration(config, repo_root)
        run_id = result.run_id

        # Resume with a different branch.
        config = OrchestrationConfig(resume_run_id=run_id, apply=True)
        with _patch_get_git_info(_git_info(repo_root, branch="other-branch")):
            result = run_orchestration(config, repo_root)

        assert result.ok is False
        assert result.status == OrchestrationStatus.STALE_EVIDENCE.value
        assert "Branch mismatch" in (result.blocking_reason or "")

    def test_completed_goal_task_generation_not_invoked_again(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY")

        config = OrchestrationConfig(goal="Add feature", planner="dry-run", apply=True)
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                result = run_orchestration(config, repo_root)
        run_id = result.run_id
        assert mock_gen.call_count == 1

        # Resume should not call generate_goal_task again.
        config = OrchestrationConfig(resume_run_id=run_id, apply=True)
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen2:
                result = run_orchestration(config, repo_root)
        assert mock_gen2.call_count == 0


# ---------------------------------------------------------------------------
# Task execution and auto-pipeline delegation
# ---------------------------------------------------------------------------


class TestTaskExecution:
    def test_ready_task_delegates_to_auto_pipeline(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        bundle_path = repo_root / ".agent_runner" / "review" / "bundle.json"
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        _write_bundle_file(bundle, bundle_path)

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", worker="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    result = run_orchestration(config, repo_root)

        assert mock_auto.call_count == 1
        assert result.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value

    def test_ready_for_approval_does_not_auto_approve(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        bundle_path = repo_root / ".agent_runner" / "review" / "bundle.json"
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        _write_bundle_file(bundle, bundle_path)

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", worker="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    result = run_orchestration(config, repo_root)

        assert result.controller_gate is None
        assert result.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value

    def test_repair_exhausted_stops_with_correct_status(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])

        config = OrchestrationConfig(
            goal="Add feature",
            planner="dry-run",
            worker="dry-run",
            repair_attempts=2,
            apply=True,
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", status="REPAIR_EXHAUSTED"
                    )
                    result = run_orchestration(config, repo_root)

        assert result.status == OrchestrationStatus.REPAIR_EXHAUSTED.value

    def test_non_repairable_stops_with_correct_status(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])

        config = OrchestrationConfig(
            goal="Add feature",
            planner="dry-run",
            worker="dry-run",
            apply=True,
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", status="NON_REPAIRABLE"
                    )
                    result = run_orchestration(config, repo_root)

        assert result.status == OrchestrationStatus.NON_REPAIRABLE.value


# ---------------------------------------------------------------------------
# Implementation decision gate
# ---------------------------------------------------------------------------


class TestImplementationDecision:
    def test_missing_decision_pauses_awaiting_implementation_decision(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "timestamp": bundle.timestamp,
                    "task_id": bundle.task_id,
                    "task_filename": bundle.task_filename,
                    "previous_status": bundle.previous_status,
                    "current_status": bundle.current_status,
                    "branch": bundle.branch,
                    "pre_head": bundle.pre_head,
                    "post_head": bundle.post_head,
                    "runner_status": bundle.runner_status,
                    "worker_type": bundle.worker_type,
                    "worker_success": bundle.worker_success,
                    "post_verification_ok": bundle.post_verification_ok,
                    "post_verification_messages": bundle.post_verification_messages,
                    "changed_paths": bundle.changed_paths,
                    "diff_summary": bundle.diff_summary,
                    "recommended_action": bundle.recommended_action,
                }
            ),
            encoding="utf-8",
        )

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", worker="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    result = run_orchestration(config, repo_root)

        assert result.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
        assert result.controller_gate is None

    def test_approve_delegates_to_finalization_once(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "timestamp": bundle.timestamp,
                    "task_id": bundle.task_id,
                    "task_filename": bundle.task_filename,
                    "previous_status": bundle.previous_status,
                    "current_status": bundle.current_status,
                    "branch": bundle.branch,
                    "pre_head": bundle.pre_head,
                    "post_head": bundle.post_head,
                    "runner_status": bundle.runner_status,
                    "worker_type": bundle.worker_type,
                    "worker_success": bundle.worker_success,
                    "post_verification_ok": bundle.post_verification_ok,
                    "post_verification_messages": bundle.post_verification_messages,
                    "changed_paths": bundle.changed_paths,
                    "diff_summary": bundle.diff_summary,
                    "recommended_action": bundle.recommended_action,
                }
            ),
            encoding="utf-8",
        )
        decision = _make_decision(bundle, bundle_path, DecisionValue.APPROVE)
        decision_path = write_controller_decision(
            decision, default_decisions_dir(repo_root)
        )

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", worker="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    with patch(
                        "advancore.agent_runner.orchestration.run_finalization"
                    ) as mock_finalize:
                        mock_finalize.return_value = FinalizationResult(
                            ok=True,
                            status=FinalizationStatus.PUSHED,
                            task_id="TASK-022",
                        )
                        result = run_orchestration(config, repo_root)

        assert mock_finalize.call_count == 1
        assert result.status == OrchestrationStatus.PUBLISHED.value

    def test_blocked_decision_never_calls_finalization(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "timestamp": bundle.timestamp,
                    "task_id": bundle.task_id,
                    "task_filename": bundle.task_filename,
                    "previous_status": bundle.previous_status,
                    "current_status": bundle.current_status,
                    "branch": bundle.branch,
                    "pre_head": bundle.pre_head,
                    "post_head": bundle.post_head,
                    "runner_status": bundle.runner_status,
                    "worker_type": bundle.worker_type,
                    "worker_success": bundle.worker_success,
                    "post_verification_ok": bundle.post_verification_ok,
                    "post_verification_messages": bundle.post_verification_messages,
                    "changed_paths": bundle.changed_paths,
                    "diff_summary": bundle.diff_summary,
                    "recommended_action": bundle.recommended_action,
                }
            ),
            encoding="utf-8",
        )
        decision = _make_decision(bundle, bundle_path, DecisionValue.BLOCKED)
        write_controller_decision(decision, default_decisions_dir(repo_root))

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", worker="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    with patch(
                        "advancore.agent_runner.orchestration.run_finalization"
                    ) as mock_finalize:
                        result = run_orchestration(config, repo_root)

        assert mock_finalize.call_count == 0
        assert result.status == OrchestrationStatus.BLOCKED.value


# ---------------------------------------------------------------------------
# Rework cycle
# ---------------------------------------------------------------------------


class TestRework:
    def test_rework_follows_lifecycle_and_one_bounded_cycle(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "timestamp": bundle.timestamp,
                    "task_id": bundle.task_id,
                    "task_filename": bundle.task_filename,
                    "previous_status": bundle.previous_status,
                    "current_status": bundle.current_status,
                    "branch": bundle.branch,
                    "pre_head": bundle.pre_head,
                    "post_head": bundle.post_head,
                    "runner_status": bundle.runner_status,
                    "worker_type": bundle.worker_type,
                    "worker_success": bundle.worker_success,
                    "post_verification_ok": bundle.post_verification_ok,
                    "post_verification_messages": bundle.post_verification_messages,
                    "changed_paths": bundle.changed_paths,
                    "diff_summary": bundle.diff_summary,
                    "recommended_action": bundle.recommended_action,
                }
            ),
            encoding="utf-8",
        )
        decision = _make_decision(bundle, bundle_path, DecisionValue.REWORK)
        write_controller_decision(decision, default_decisions_dir(repo_root))

        config = OrchestrationConfig(
            goal="Add feature",
            planner="dry-run",
            worker="dry-run",
            max_rework=1,
            apply=True,
        )
        auto_call_count = 0

        def _auto_side_effect(*args, **kwargs):
            nonlocal auto_call_count
            auto_call_count += 1
            if auto_call_count == 1:
                return _make_auto_result(
                    repo_root, "TASK-022", review_bundle_path=bundle_path
                )
            return _make_auto_result(
                repo_root, "TASK-022", review_bundle_path=bundle_path
            )

        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline",
                    side_effect=_auto_side_effect,
                ):
                    result = run_orchestration(config, repo_root)

        # First run returns REWORK, second run has no new decision -> pause.
        assert auto_call_count == 2
        assert result.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value

    def test_rework_exhaustion_requires_intervention(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "timestamp": bundle.timestamp,
                    "task_id": bundle.task_id,
                    "task_filename": bundle.task_filename,
                    "previous_status": bundle.previous_status,
                    "current_status": bundle.current_status,
                    "branch": bundle.branch,
                    "pre_head": bundle.pre_head,
                    "post_head": bundle.post_head,
                    "runner_status": bundle.runner_status,
                    "worker_type": bundle.worker_type,
                    "worker_success": bundle.worker_success,
                    "post_verification_ok": bundle.post_verification_ok,
                    "post_verification_messages": bundle.post_verification_messages,
                    "changed_paths": bundle.changed_paths,
                    "diff_summary": bundle.diff_summary,
                    "recommended_action": bundle.recommended_action,
                }
            ),
            encoding="utf-8",
        )
        decision = _make_decision(bundle, bundle_path, DecisionValue.REWORK)
        write_controller_decision(decision, default_decisions_dir(repo_root))

        config = OrchestrationConfig(
            goal="Add feature",
            planner="dry-run",
            worker="dry-run",
            max_rework=0,
            apply=True,
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    result = run_orchestration(config, repo_root)

        assert result.status == OrchestrationStatus.REWORK_EXHAUSTED.value


# ---------------------------------------------------------------------------
# Finalization and publication
# ---------------------------------------------------------------------------


class TestFinalization:
    def test_finalization_failure_not_retried_blindly(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "timestamp": bundle.timestamp,
                    "task_id": bundle.task_id,
                    "task_filename": bundle.task_filename,
                    "previous_status": bundle.previous_status,
                    "current_status": bundle.current_status,
                    "branch": bundle.branch,
                    "pre_head": bundle.pre_head,
                    "post_head": bundle.post_head,
                    "runner_status": bundle.runner_status,
                    "worker_type": bundle.worker_type,
                    "worker_success": bundle.worker_success,
                    "post_verification_ok": bundle.post_verification_ok,
                    "post_verification_messages": bundle.post_verification_messages,
                    "changed_paths": bundle.changed_paths,
                    "diff_summary": bundle.diff_summary,
                    "recommended_action": bundle.recommended_action,
                }
            ),
            encoding="utf-8",
        )
        decision = _make_decision(bundle, bundle_path, DecisionValue.APPROVE)
        write_controller_decision(decision, default_decisions_dir(repo_root))

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", worker="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    with patch(
                        "advancore.agent_runner.orchestration.run_finalization"
                    ) as mock_finalize:
                        mock_finalize.return_value = FinalizationResult(
                            ok=False,
                            status=FinalizationStatus.PUBLICATION_FAILED,
                            task_id="TASK-022",
                        )
                        result = run_orchestration(config, repo_root)

        assert mock_finalize.call_count == 1
        assert result.status == OrchestrationStatus.BLOCKED.value


# ---------------------------------------------------------------------------
# Checkpoint safety
# ---------------------------------------------------------------------------


class TestCheckpoint:
    def test_checkpoint_atomic_write_and_partial_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        checkpoint = OrchestrationCheckpoint(
            schema_version="advancore-orchestration-v1",
            run_id="ORCH-test",
            goal_hash="abcd",
            goal_summary="summary",
            planner="dry-run",
            worker="dry-run",
            controller="manual",
            repair_attempts=0,
            max_rework=0,
            apply=True,
            phase=OrchestrationPhase.GOAL_VALIDATION.value,
        )
        path = save_checkpoint(checkpoint, repo_root)
        assert path.exists()
        assert not any(path.parent.glob(f".{path.name}.tmp-*"))

        # Corrupt the checkpoint.
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(OrchestrationError, match="Cannot read checkpoint"):
            load_checkpoint("ORCH-test", repo_root)

    def test_checkpoint_excludes_sensitive_content(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        checkpoint = OrchestrationCheckpoint(
            schema_version="advancore-orchestration-v1",
            run_id="ORCH-test",
            goal_hash="abcd",
            goal_summary="summary",
            planner="dry-run",
            worker="dry-run",
            controller="manual",
            repair_attempts=0,
            max_rework=0,
            apply=True,
            phase=OrchestrationPhase.GOAL_VALIDATION.value,
            messages=["ok"],
        )
        path = save_checkpoint(checkpoint, repo_root)
        raw = path.read_text(encoding="utf-8")
        assert "password" not in raw.lower()
        assert "secret" not in raw.lower()
        assert "stdout" not in raw.lower()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_orchestrate_preview_cli(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-021-existing.md").write_text("x")
        monkeypatch.chdir(repo_root)
        fake_git_info = lambda cwd=None: _git_info(repo_root, clean=True)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            fake_git_info,
        )
        monkeypatch.setattr(
            "advancore.agent_runner.orchestration.get_git_info",
            fake_git_info,
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            ["orchestrate", "--goal", "Add feature", "--planner", "dry-run"]
        )
        assert code == 0

    def test_orchestrate_goal_and_resume_mutually_exclusive(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root, clean=True),
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            ["orchestrate", "--goal", "Add feature", "--resume", "ORCH-test"]
        )
        assert code == 1


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_no_code_path_targets_main(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        config = OrchestrationConfig(goal="Add feature", apply=True)
        with _patch_get_git_info(_git_info(repo_root, branch="main")):
            result = run_orchestration(config, repo_root)

        # Goal-task generation rejects main branch before worker launch.
        assert result.ok is False

    def test_orchestrator_does_not_directly_stage_commit_push(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-022", "Sample", "READY", allowed_scope=["foo.py"])
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = _make_review_bundle(repo_root, "TASK-022", ["foo.py"])
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(
            json.dumps(
                {
                    "timestamp": bundle.timestamp,
                    "task_id": bundle.task_id,
                    "task_filename": bundle.task_filename,
                    "previous_status": bundle.previous_status,
                    "current_status": bundle.current_status,
                    "branch": bundle.branch,
                    "pre_head": bundle.pre_head,
                    "post_head": bundle.post_head,
                    "runner_status": bundle.runner_status,
                    "worker_type": bundle.worker_type,
                    "worker_success": bundle.worker_success,
                    "post_verification_ok": bundle.post_verification_ok,
                    "post_verification_messages": bundle.post_verification_messages,
                    "changed_paths": bundle.changed_paths,
                    "diff_summary": bundle.diff_summary,
                    "recommended_action": bundle.recommended_action,
                }
            ),
            encoding="utf-8",
        )
        decision = _make_decision(bundle, bundle_path, DecisionValue.APPROVE)
        write_controller_decision(decision, default_decisions_dir(repo_root))

        config = OrchestrationConfig(
            goal="Add feature", planner="dry-run", worker="dry-run", apply=True
        )
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with patch(
                "advancore.agent_runner.orchestration.generate_goal_task"
            ) as mock_gen:
                mock_gen.return_value = _make_goal_task_result(repo_root, tasks_dir)
                with patch(
                    "advancore.agent_runner.orchestration.run_auto_pipeline"
                ) as mock_auto:
                    mock_auto.return_value = _make_auto_result(
                        repo_root, "TASK-022", review_bundle_path=bundle_path
                    )
                    with patch(
                        "advancore.agent_runner.orchestration.run_finalization"
                    ) as mock_finalize:
                        mock_finalize.return_value = FinalizationResult(
                            ok=True,
                            status=FinalizationStatus.PUSHED,
                            task_id="TASK-022",
                        )
                        run_orchestration(config, repo_root)

        # Orchestrator delegates finalization; it never calls git add/commit/push itself.
        assert mock_finalize.call_count == 1
