"""Focused tests for explicit owner decision intake and resume (TASK-025)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner.__main__ import main
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.orchestration import (
    OrchestrationCheckpoint,
    OrchestrationConfig,
    OrchestrationError,
    OrchestrationPhase,
    OwnerAction,
    default_orchestration_dir,
    load_checkpoint,
    run_orchestration,
    save_checkpoint,
)
from advancore.agent_runner.review_bundle import ReviewBundle, serialize_bundle


HEAD = "abc1230000000000000000000000000000000000"
BRANCH = "agent-control-foundation"


def _git(repo_root: Path, *, head: str = HEAD) -> GitInfo:
    return GitInfo(
        repo_root=repo_root,
        current_branch=BRANCH,
        head_sha=head,
        is_clean=True,
        status_lines=[],
    )


def _task(tasks_dir: Path, status: str = "DRAFT") -> Path:
    path = tasks_dir / "TASK-025-owner-intake.md"
    path.write_text(
        "# TASK-025 — Owner intake\n\n"
        f"STATUS: {status}\n\n"
        "## Objective\n\nTest owner intake.\n\n"
        "## Owner decisions\n\n- None.\n",
        encoding="utf-8",
    )
    return path


def _checkpoint(repo_root: Path, task_path: Path, phase: str) -> OrchestrationCheckpoint:
    checkpoint = OrchestrationCheckpoint(
        schema_version="advancore-orchestration-v1",
        run_id="ORCH-owner-test",
        goal_hash="hash",
        goal_summary="goal",
        planner="dry-run",
        worker="dry-run",
        controller="manual",
        repair_attempts=0,
        max_rework=0,
        apply=True,
        phase=phase,
        branch=BRANCH,
        expected_head=HEAD,
        task_id="TASK-025",
        task_path=str(task_path),
        task_written=True,
    )
    save_checkpoint(checkpoint, repo_root)
    return checkpoint


def _bundle(repo_root: Path, checkpoint: OrchestrationCheckpoint) -> Path:
    path = repo_root / ".agent_runner" / "review" / "bundle.json"
    path.parent.mkdir(parents=True)
    bundle = ReviewBundle(
        timestamp="2026-08-23T00:00:00+00:00",
        task_id="TASK-025",
        task_filename=Path(checkpoint.task_path or "").name,
        previous_status="READY",
        current_status="READY",
        branch=BRANCH,
        pre_head=HEAD,
        post_head=HEAD,
        runner_status="awaiting_controller",
        worker_type="dry-run",
        worker_success=True,
        post_verification_ok=True,
        recommended_action="REVIEW",
    )
    path.write_text(json.dumps(serialize_bundle(bundle)), encoding="utf-8")
    checkpoint.review_bundle_path = str(path)
    save_checkpoint(checkpoint, repo_root)
    return path


def test_owner_action_requires_resume_and_known_enum():
    with pytest.raises(OrchestrationError, match="requires --resume"):
        OrchestrationConfig(goal="new goal", owner_action="APPROVE_TASK")
    with pytest.raises(OrchestrationError, match="Unknown owner action"):
        OrchestrationConfig(resume_run_id="ORCH-x", owner_action="approve somehow")


def test_owner_note_is_bounded_single_line():
    with pytest.raises(OrchestrationError, match="single line"):
        OrchestrationConfig(
            resume_run_id="ORCH-x",
            owner_action=OwnerAction.APPROVE_TASK,
            owner_note="yes\nbecause",
        )
    with pytest.raises(OrchestrationError, match="400"):
        OrchestrationConfig(
            resume_run_id="ORCH-x",
            owner_action=OwnerAction.APPROVE_TASK,
            owner_note="x" * 401,
        )


def test_task_approval_preview_writes_nothing(tmp_path: Path):
    repo_root = tmp_path / "repo"
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _task(tasks_dir)
    _checkpoint(repo_root, task_path, OrchestrationPhase.AWAITING_TASK_APPROVAL.value)
    before_task = task_path.read_bytes()
    checkpoint_path = default_orchestration_dir(repo_root) / "ORCH-owner-test.json"
    before_checkpoint = checkpoint_path.read_bytes()

    config = OrchestrationConfig(
        resume_run_id="ORCH-owner-test", owner_action=OwnerAction.APPROVE_TASK
    )
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        result = run_orchestration(config, repo_root)

    assert result.ok is True
    assert result.owner_action_evidence["state"] == "preview"
    assert "DRAFT -> READY" in " ".join(result.messages)
    assert task_path.read_bytes() == before_task
    assert checkpoint_path.read_bytes() == before_checkpoint
    assert not (repo_root / ".agent_runner" / "audit").exists()


def test_task_approval_apply_uses_lifecycle_then_continues(tmp_path: Path):
    repo_root = tmp_path / "repo"
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _task(tasks_dir)
    _checkpoint(repo_root, task_path, OrchestrationPhase.AWAITING_TASK_APPROVAL.value)

    config = OrchestrationConfig(
        resume_run_id="ORCH-owner-test",
        owner_action=OwnerAction.APPROVE_TASK,
        apply=True,
    )
    sentinel = object()
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with patch(
            "advancore.agent_runner.orchestration._phase_task_execution",
            return_value=sentinel,
        ):
            result = run_orchestration(config, repo_root)

    assert result is sentinel
    assert "STATUS: READY" in task_path.read_text(encoding="utf-8")
    stored = load_checkpoint("ORCH-owner-test", repo_root)
    assert stored.owner_action == OwnerAction.APPROVE_TASK.value
    assert stored.owner_action_actor == "owner"
    assert stored.owner_action_state == "applied"


def test_phase_mismatch_and_resume_override_fail_closed(tmp_path: Path):
    repo_root = tmp_path / "repo"
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _task(tasks_dir)
    _checkpoint(repo_root, task_path, OrchestrationPhase.AWAITING_TASK_APPROVAL.value)

    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with pytest.raises(OrchestrationError, match="not valid at phase"):
            run_orchestration(
                OrchestrationConfig(
                    resume_run_id="ORCH-owner-test",
                    owner_action=OwnerAction.APPROVE_IMPLEMENTATION,
                ),
                repo_root,
            )
        with pytest.raises(OrchestrationError, match="cannot be mixed"):
            run_orchestration(
                OrchestrationConfig(
                    resume_run_id="ORCH-owner-test",
                    owner_action=OwnerAction.APPROVE_TASK,
                    worker="codex",
                    resume_overrides=("--worker",),
                ),
                repo_root,
            )


def test_implementation_preview_validates_evidence_and_writes_nothing(tmp_path: Path):
    repo_root = tmp_path / "repo"
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _task(tasks_dir, "READY")
    checkpoint = _checkpoint(
        repo_root, task_path, OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value
    )
    _bundle(repo_root, checkpoint)
    checkpoint_path = default_orchestration_dir(repo_root) / "ORCH-owner-test.json"
    before = checkpoint_path.read_bytes()

    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        result = run_orchestration(
            OrchestrationConfig(
                resume_run_id="ORCH-owner-test",
                owner_action=OwnerAction.REWORK_IMPLEMENTATION,
                owner_note="Tests need correction",
            ),
            repo_root,
        )

    assert result.ok is True
    assert result.owner_action_evidence["action"] == "REWORK_IMPLEMENTATION"
    assert "ControllerDecision REWORK" in " ".join(result.messages)
    assert checkpoint_path.read_bytes() == before
    assert not (repo_root / ".agent_runner" / "decisions").exists()
    assert not (repo_root / ".agent_runner" / "controller_handoff").exists()


def test_implementation_approval_records_owner_decision_and_continues(tmp_path: Path):
    repo_root = tmp_path / "repo"
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _task(tasks_dir, "READY")
    checkpoint = _checkpoint(
        repo_root, task_path, OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value
    )
    _bundle(repo_root, checkpoint)

    sentinel = object()
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with patch(
            "advancore.agent_runner.orchestration._phase_finalization",
            return_value=sentinel,
        ):
            result = run_orchestration(
                OrchestrationConfig(
                    resume_run_id="ORCH-owner-test",
                    owner_action=OwnerAction.APPROVE_IMPLEMENTATION,
                    owner_note="Owner reviewed bounded evidence",
                    apply=True,
                ),
                repo_root,
            )

    assert result is sentinel
    stored = load_checkpoint("ORCH-owner-test", repo_root)
    assert stored.owner_action == "APPROVE_IMPLEMENTATION"
    assert stored.owner_action_actor == "owner"
    assert stored.decision == "APPROVE"
    decision_path = Path(stored.decision_path or "")
    if not decision_path.is_absolute():
        decision_path = repo_root / decision_path
    decision_payload = json.loads(decision_path.read_text())
    assert decision_payload["actor_role"] == "owner"
    assert decision_payload["task_id"] == "TASK-025"
    assert decision_payload["bundle_branch"] == BRANCH
    assert decision_payload["bundle_post_head"] == HEAD


def test_stale_head_fails_before_owner_action(tmp_path: Path):
    repo_root = tmp_path / "repo"
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _task(tasks_dir)
    _checkpoint(repo_root, task_path, OrchestrationPhase.AWAITING_TASK_APPROVAL.value)
    with patch(
        "advancore.agent_runner.orchestration.get_git_info",
        return_value=_git(repo_root, head="different"),
    ):
        with pytest.raises(OrchestrationError, match="HEAD mismatch"):
            run_orchestration(
                OrchestrationConfig(
                    resume_run_id="ORCH-owner-test",
                    owner_action=OwnerAction.APPROVE_TASK,
                ),
                repo_root,
            )


@pytest.mark.parametrize("worker_args", [["--worker", "codex"], ["--worker=codex"]])
def test_cli_rejects_worker_supplied_owner_action_mix(
    tmp_path: Path, capsys, worker_args: list[str]
):
    repo_root = tmp_path / "repo"
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _task(tasks_dir)
    _checkpoint(repo_root, task_path, OrchestrationPhase.AWAITING_TASK_APPROVAL.value)
    with patch("advancore.agent_runner.__main__.get_git_info", return_value=_git(repo_root)):
        with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
            rc = main([
                "orchestrate", "--resume", "ORCH-owner-test",
                "--owner-action", "APPROVE_TASK", *worker_args,
            ])
    assert rc == 1
    assert "cannot be mixed" in capsys.readouterr().err
