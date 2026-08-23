"""Acceptance tests for the complete explicit owner-action resume path (TASK-026)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from advancore.agent_runner.auto_pipeline import (
    AutoPipelineResult,
    AutoPipelineStatus,
    PytestResult,
)
from advancore.agent_runner.controller_decision import (
    DecisionValue,
    build_controller_decision,
    default_decisions_dir,
    write_controller_decision,
)
from advancore.agent_runner.finalize import FinalizationResult, FinalizationStatus
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.goal_task import (
    GoalTaskGenerationResult,
    GoalTaskGenerationStatus,
)
from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.orchestration import (
    OrchestrationConfig,
    OrchestrationCheckpoint,
    OrchestrationError,
    OrchestrationPhase,
    OrchestrationStatus,
    OwnerAction,
    load_checkpoint,
    run_orchestration,
    save_checkpoint,
)
from advancore.agent_runner.review_bundle import ReviewBundle, serialize_bundle
from advancore.agent_runner.task import Task
from advancore.agent_runner.worker import WorkerAdapter, WorkerResult


TASK_ID = "TASK-026"
TASK_FILENAME = "TASK-026-owner-action-acceptance.md"
RUN_BRANCH = "task-026-owner-action-acceptance"
RUN_HEAD = "0260000000000000000000000000000000000000"


def test_real_git_owner_rework_reaches_fresh_review_handoff(tmp_path: Path):
    repo = tmp_path / "real-rework"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "feature/rework"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", "../remote.git"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(".agent_runner/\n", encoding="utf-8")
    tasks = repo / "tasks"
    tasks.mkdir()
    task_path = tasks / "TASK-038-real-rework.md"
    task_path.write_text(
        "# TASK-038 — Real rework\n\nSTATUS: READY\n\n"
        "## Objective\n\nExercise phase-aware rework.\n\n"
        "## Allowed changed-file scope\n\n"
        "- `bounded.py`\n- `tasks/TASK-038-real-rework.md`\n\n"
        "## Owner decisions\n\nNone.\n",
        encoding="utf-8",
    )
    source = repo / "bounded.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/feature/rework", head],
        cwd=repo,
        check=True,
    )
    source.write_text("value = 2\n", encoding="utf-8")

    prior_bundle = ReviewBundle(
        timestamp="2026-08-23T00:00:00+00:00",
        task_id="TASK-038",
        task_filename=task_path.name,
        previous_status="READY",
        current_status="READY",
        branch="feature/rework",
        pre_head=head,
        post_head=head,
        runner_status="awaiting_approval",
        worker_type="controlled-worker",
        worker_success=True,
        post_verification_ok=True,
        changed_paths=["bounded.py"],
        recommended_action="REVIEW",
    )
    prior_bundle_path = repo / ".agent_runner" / "review" / "prior.json"
    prior_bundle_path.parent.mkdir(parents=True)
    prior_bundle_path.write_text(
        json.dumps(serialize_bundle(prior_bundle)), encoding="utf-8"
    )
    checkpoint = OrchestrationCheckpoint(
        schema_version="advancore-orchestration-v1",
        run_id="ORCH-real-rework",
        goal_hash="goal",
        goal_summary="real rework",
        planner="dry-run",
        worker="dry-run",
        controller="manual",
        repair_attempts=0,
        max_rework=1,
        apply=True,
        phase=OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value,
        status=OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value,
        branch="feature/rework",
        expected_head=head,
        path_fingerprint=["bounded.py"],
        task_id="TASK-038",
        task_path=str(task_path),
        task_written=True,
        review_bundle_path=str(prior_bundle_path),
        auto_status=AutoPipelineStatus.READY_FOR_APPROVAL.value,
        completed_phases=[OrchestrationPhase.TASK_EXECUTION.value],
    )
    save_checkpoint(checkpoint, repo)
    pending = run_orchestration(
        OrchestrationConfig(resume_run_id=checkpoint.run_id, apply=True), repo
    )
    assert pending.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
    prior_handoff_path = Path(load_checkpoint(checkpoint.run_id, repo).handoff_path or "")

    class ControlledReworkWorker(WorkerAdapter):
        @property
        def name(self) -> str:
            return "controlled-rework"

        def build_command(self, instruction: str, working_dir: Path) -> list[str]:
            return []

        def run(self, instruction: str, working_dir: Path) -> WorkerResult:
            (working_dir / "bounded.py").write_text("value = 3\n", encoding="utf-8")
            return WorkerResult(success=True, message="controlled rework complete")

    passed = PytestResult(
        command=["pytest"],
        returncode=0,
        stdout="1 passed",
        stderr="",
        passed_count=1,
        summary="1 passed",
    )
    with patch(
        "advancore.agent_runner.orchestration.build_worker_adapter",
        return_value=ControlledReworkWorker(),
    ):
        with patch("advancore.agent_runner.auto_pipeline.run_pytest", return_value=passed):
            result = run_orchestration(
                OrchestrationConfig(
                    resume_run_id=checkpoint.run_id,
                    owner_action=OwnerAction.REWORK_IMPLEMENTATION,
                    owner_note="Apply the reviewed correction.",
                    apply=True,
                ),
                repo,
            )

    assert result.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
    assert source.read_text(encoding="utf-8") == "value = 3\n"
    assert "STATUS: REWORK" in task_path.read_text(encoding="utf-8")
    completed = load_checkpoint(checkpoint.run_id, repo)
    assert completed.rework_cycles_used == 1
    assert completed.rework_evidence is not None
    assert len(completed.consumed_rework_authorizations) == 1
    assert Path(completed.review_bundle_path or "").resolve() != prior_bundle_path.resolve()
    assert Path(completed.handoff_path or "").resolve() != prior_handoff_path.resolve()


def _git(repo_root: Path, *, head: str = RUN_HEAD) -> GitInfo:
    return GitInfo(
        repo_root=repo_root,
        current_branch=RUN_BRANCH,
        head_sha=head,
        is_clean=True,
        status_lines=[],
    )


def _write_draft(repo_root: Path) -> Path:
    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = tasks_dir / TASK_FILENAME
    task_path.write_text(
        f"# {TASK_ID} — Owner action acceptance\n\n"
        "STATUS: DRAFT\n\n"
        "## Objective\n\nExercise both owner gates.\n\n"
        "## Allowed changed-file scope\n\n- `bounded.py`\n\n"
        "## Owner decisions\n\n- None.\n",
        encoding="utf-8",
    )
    return task_path


def _write_bundle(repo_root: Path, task_path: Path) -> Path:
    bundle = ReviewBundle(
        timestamp="2026-08-23T00:00:00+00:00",
        task_id=TASK_ID,
        task_filename=task_path.name,
        previous_status="READY",
        current_status="READY",
        branch=RUN_BRANCH,
        pre_head=RUN_HEAD,
        post_head=RUN_HEAD,
        runner_status="awaiting_approval",
        worker_type="controlled-fake",
        worker_success=True,
        post_verification_ok=True,
        changed_paths=["bounded.py"],
        recommended_action="REVIEW",
    )
    path = repo_root / ".agent_runner" / "review" / "TASK-026-bundle.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(serialize_bundle(bundle)), encoding="utf-8")
    return path


def _tree_snapshot(repo_root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(repo_root)): path.read_bytes()
        for path in sorted(repo_root.rglob("*"))
        if path.is_file()
    }


def _start_run(repo_root: Path, task_path: Path) -> str:
    generation = GoalTaskGenerationResult(
        ok=True,
        status=GoalTaskGenerationStatus.DRAFT_CREATED,
        goal_accepted=True,
        planner_type="controlled-fake",
        planner_success=True,
        proposal_valid=True,
        task_id=TASK_ID,
        task_path=task_path,
        task_written=True,
        owner_decision_count=0,
        messages=["controlled DRAFT generated"],
    )
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with patch(
            "advancore.agent_runner.orchestration.generate_goal_task",
            return_value=generation,
        ):
            result = run_orchestration(
                OrchestrationConfig(goal="Exercise owner actions", apply=True), repo_root
            )
    assert result.status == OrchestrationStatus.AWAITING_TASK_APPROVAL.value
    assert result.phase == OrchestrationPhase.AWAITING_TASK_APPROVAL.value
    return result.run_id


def _advance_to_implementation_gate(
    repo_root: Path, task_path: Path, run_id: str, bundle_path: Path
) -> None:
    auto_result = AutoPipelineResult(
        status=AutoPipelineStatus.READY_FOR_APPROVAL,
        task=Task(TASK_ID, "Owner action acceptance", "READY", task_path.name, task_path),
        review_bundle_path=bundle_path,
        messages=["controlled verification passed"],
    )
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with patch(
            "advancore.agent_runner.orchestration.run_auto_pipeline",
            return_value=auto_result,
        ):
            result = run_orchestration(
                OrchestrationConfig(
                    resume_run_id=run_id,
                    owner_action=OwnerAction.APPROVE_TASK,
                    apply=True,
                ),
                repo_root,
            )
    assert result.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
    checkpoint = load_checkpoint(run_id, repo_root)
    assert checkpoint.phase == OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION.value
    assert checkpoint.task_id == TASK_ID
    assert Path(checkpoint.review_bundle_path or "").resolve() == bundle_path.resolve()
    assert checkpoint.branch == RUN_BRANCH
    assert checkpoint.expected_head == RUN_HEAD


def test_two_gate_owner_resume_reaches_controlled_push_once(tmp_path: Path):
    repo_root = tmp_path / "repo"
    task_path = _write_draft(repo_root)
    bundle_path = _write_bundle(repo_root, task_path)
    run_id = _start_run(repo_root, task_path)

    before = _tree_snapshot(repo_root)
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        preview = run_orchestration(
            OrchestrationConfig(
                resume_run_id=run_id, owner_action=OwnerAction.APPROVE_TASK
            ),
            repo_root,
        )
    assert preview.owner_action_evidence["state"] == "preview"
    assert _tree_snapshot(repo_root) == before

    _advance_to_implementation_gate(repo_root, task_path, run_id, bundle_path)
    checkpoint = load_checkpoint(run_id, repo_root)
    handoff_path = Path(checkpoint.handoff_path or "")
    before = _tree_snapshot(repo_root)
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        preview = run_orchestration(
            OrchestrationConfig(
                resume_run_id=run_id,
                owner_action=OwnerAction.APPROVE_IMPLEMENTATION,
            ),
            repo_root,
        )
    assert preview.owner_action_evidence["state"] == "preview"
    assert _tree_snapshot(repo_root) == before

    pushed = FinalizationResult(
        ok=True,
        status=FinalizationStatus.PUSHED,
        task_id=TASK_ID,
        branch=RUN_BRANCH,
        commit_sha="final026",
        messages=["controlled fake PUSHED"],
    )
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with patch(
            "advancore.agent_runner.orchestration.run_finalization",
            return_value=pushed,
        ) as finalize:
            result = run_orchestration(
                OrchestrationConfig(
                    resume_run_id=run_id,
                    owner_action=OwnerAction.APPROVE_IMPLEMENTATION,
                    apply=True,
                ),
                repo_root,
            )
            repeated = run_orchestration(
                OrchestrationConfig(resume_run_id=run_id, apply=True), repo_root
            )

    assert result.status == repeated.status == OrchestrationStatus.PUBLISHED.value
    assert finalize.call_count == 1
    checkpoint = load_checkpoint(run_id, repo_root)
    assert checkpoint.run_id == run_id
    assert checkpoint.task_id == TASK_ID
    assert checkpoint.push_verified is True
    assert checkpoint.commit_sha == "final026"
    assert checkpoint.handoff_path == str(handoff_path)
    decision_path = Path(checkpoint.decision_path or "")
    if not decision_path.is_absolute():
        decision_path = repo_root / decision_path
    decision = json.loads(decision_path.read_text())
    assert decision["actor_role"] == "owner"
    assert decision["task_id"] == TASK_ID
    recorded_bundle = Path(decision["bundle_path"])
    if not recorded_bundle.is_absolute():
        recorded_bundle = repo_root / recorded_bundle
    assert recorded_bundle.resolve() == bundle_path.resolve()
    assert decision["bundle_branch"] == RUN_BRANCH
    assert decision["bundle_post_head"] == RUN_HEAD


@pytest.mark.parametrize(
    ("action", "phase"),
    [
        (OwnerAction.APPROVE_IMPLEMENTATION, OrchestrationPhase.AWAITING_TASK_APPROVAL),
        (OwnerAction.APPROVE_TASK, OrchestrationPhase.AWAITING_IMPLEMENTATION_DECISION),
    ],
)
def test_wrong_phase_stops_before_mutation(
    tmp_path: Path, action: OwnerAction, phase: OrchestrationPhase
):
    repo_root = tmp_path / "repo"
    task_path = _write_draft(repo_root)
    run_id = _start_run(repo_root, task_path)
    checkpoint = load_checkpoint(run_id, repo_root)
    checkpoint.phase = phase.value
    save_checkpoint(checkpoint, repo_root)
    before = _tree_snapshot(repo_root)
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with pytest.raises(OrchestrationError, match="not valid at phase"):
            run_orchestration(
                OrchestrationConfig(resume_run_id=run_id, owner_action=action, apply=True),
                repo_root,
            )
    assert _tree_snapshot(repo_root) == before


def test_stale_head_and_resume_override_stop_before_mutation(tmp_path: Path):
    repo_root = tmp_path / "repo"
    task_path = _write_draft(repo_root)
    run_id = _start_run(repo_root, task_path)
    before = _tree_snapshot(repo_root)
    with patch(
        "advancore.agent_runner.orchestration.get_git_info",
        return_value=_git(repo_root, head="stale"),
    ):
        with pytest.raises(OrchestrationError, match="HEAD mismatch"):
            run_orchestration(
                OrchestrationConfig(
                    resume_run_id=run_id,
                    owner_action=OwnerAction.APPROVE_TASK,
                    apply=True,
                ),
                repo_root,
            )
    assert _tree_snapshot(repo_root) == before

    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with pytest.raises(OrchestrationError, match="cannot be mixed"):
            run_orchestration(
                OrchestrationConfig(
                    resume_run_id=run_id,
                    owner_action=OwnerAction.APPROVE_TASK,
                    worker="codex",
                    resume_overrides=("--worker",),
                    apply=True,
                ),
                repo_root,
            )
    assert _tree_snapshot(repo_root) == before


def test_conflicting_worker_and_consumed_evidence_fail_closed(tmp_path: Path):
    repo_root = tmp_path / "repo"
    task_path = _write_draft(repo_root)
    bundle_path = _write_bundle(repo_root, task_path)
    run_id = _start_run(repo_root, task_path)
    _advance_to_implementation_gate(repo_root, task_path, run_id, bundle_path)
    checkpoint = load_checkpoint(run_id, repo_root)
    bundle = ReviewBundle(**json.loads(bundle_path.read_text()))

    worker_decision = build_controller_decision(
        bundle_path=bundle_path,
        bundle=bundle,
        decision=DecisionValue.APPROVE,
        actor_role=ActorRole.OWNER,
        repo_root=repo_root,
    )
    worker_decision.actor_role = ActorRole.WORKER.value
    worker_path = default_decisions_dir(repo_root) / "worker-injected.json"
    worker_path.parent.mkdir(parents=True, exist_ok=True)
    worker_path.write_text(json.dumps(worker_decision.__dict__), encoding="utf-8")
    before = _tree_snapshot(repo_root)
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with pytest.raises(OrchestrationError, match="Conflicting owner decision"):
            run_orchestration(
                OrchestrationConfig(
                    resume_run_id=run_id,
                    owner_action=OwnerAction.APPROVE_IMPLEMENTATION,
                    apply=True,
                ),
                repo_root,
            )
    assert _tree_snapshot(repo_root) == before

    worker_path.unlink()
    owner_decision = build_controller_decision(
        bundle_path=bundle_path,
        bundle=bundle,
        decision=DecisionValue.APPROVE,
        actor_role=ActorRole.OWNER,
        repo_root=repo_root,
    )
    consumed_path = write_controller_decision(owner_decision, default_decisions_dir(repo_root))
    checkpoint = load_checkpoint(run_id, repo_root)
    checkpoint.consumed_decision_paths.append(str(consumed_path.resolve()))
    save_checkpoint(checkpoint, repo_root)
    before = _tree_snapshot(repo_root)
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=_git(repo_root)):
        with pytest.raises(OrchestrationError, match="consumed"):
            run_orchestration(
                OrchestrationConfig(
                    resume_run_id=run_id,
                    owner_action=OwnerAction.APPROVE_IMPLEMENTATION,
                    apply=True,
                ),
                repo_root,
            )
    assert _tree_snapshot(repo_root) == before
