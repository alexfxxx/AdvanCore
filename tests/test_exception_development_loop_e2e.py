"""Operational acceptance for the exception-based development loop (TASK-029)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from advancore.agent_runner.auto_pipeline import AutoPipelineResult, AutoPipelineStatus
from advancore.agent_runner.finalize import FinalizationResult, FinalizationStatus
from advancore.agent_runner.controller_decision import (
    DecisionValue,
    build_controller_decision,
    default_decisions_dir,
    write_controller_decision,
)
from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.goal_task import GoalTaskGenerationResult, GoalTaskGenerationStatus
from advancore.agent_runner.orchestration import (
    OrchestrationConfig,
    OrchestrationCheckpoint,
    OrchestrationError,
    OrchestrationPhase,
    OrchestrationStatus,
    OwnerAction,
    load_checkpoint,
    reconcile_completed_run,
    run_orchestration,
    save_checkpoint,
)
from advancore.agent_runner.review_bundle import ReviewBundle, serialize_bundle
from advancore.agent_runner.task import Task


TASK_ID = "TASK-001"
TASK_NAME = "TASK-001-controlled-acceptance.md"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "feature/task-029")
    _git(repo, "config", "user.name", "Acceptance Fake")
    _git(repo, "config", "user.email", "acceptance@example.invalid")
    (repo / ".gitignore").write_text(".agent_runner/\n", encoding="utf-8")
    (repo / "tasks").mkdir()
    (repo / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "baseline.txt")
    _git(repo, "commit", "-m", "baseline")
    return repo


def _task_text(status: str = "DRAFT") -> str:
    return f"""# {TASK_ID} — Controlled acceptance

STATUS: {status}

## Objective

Exercise the bounded loop.

## Allowed changed-file scope

- `bounded.py`

## Owner decisions

- None.
"""


def _generation(repo: Path, events: list[str]) -> GoalTaskGenerationResult:
    events.extend(["planner:kimi-swarm:unavailable", "planner:codex:fallback"])
    task_path = repo / "tasks" / TASK_NAME
    task_path.write_text(_task_text(), encoding="utf-8")
    artifact = repo / ".agent_runner" / "goal_task" / "goal_task.jsonl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps({"primary": "kimi-swarm", "fallback": "codex", "reason": "unavailable"})
        + "\n",
        encoding="utf-8",
    )
    return GoalTaskGenerationResult(
        ok=True,
        status=GoalTaskGenerationStatus.DRAFT_CREATED,
        goal_accepted=True,
        planner_type="kimi-swarm",
        planner_success=True,
        primary_planner="kimi-swarm",
        fallback_planner="codex",
        terminal_planner="codex",
        failure_classification="UNAVAILABLE",
        integrity_ok=True,
        fallback_used=True,
        recovery_evidence=["kimi-swarm unavailable", "codex proposal accepted"],
        proposal_valid=True,
        task_id=TASK_ID,
        task_path=task_path,
        task_written=True,
        artifact_path=artifact,
        owner_decision_count=0,
        messages=["runner rendered canonical STATUS: DRAFT task"],
    )


def _bundle(repo: Path, events: list[str]) -> Path:
    events.append("runner:verification:passed")
    (repo / "bounded.py").write_text("accepted = True\n", encoding="utf-8")
    head = _git(repo, "rev-parse", "HEAD")
    bundle = ReviewBundle(
        timestamp="2026-08-23T00:00:00+00:00",
        task_id=TASK_ID,
        task_filename=TASK_NAME,
        previous_status="READY",
        current_status="READY",
        branch="feature/task-029",
        pre_head=head,
        post_head=head,
        runner_status="awaiting_approval",
        worker_type="codex-controlled-fake",
        worker_success=True,
        post_verification_ok=True,
        changed_paths=["bounded.py"],
        recommended_action="REVIEW",
    )
    path = repo / ".agent_runner" / "review" / "bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(serialize_bundle(bundle)), encoding="utf-8")
    return path


def test_complete_two_decision_loop_with_controlled_finalization(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path)
    events: list[str] = []
    worker_calls: list[list[str]] = []
    finalize_calls: list[str] = []

    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.generate_goal_task",
        lambda **_: _generation(repo, events),
    )
    first = run_orchestration(
        OrchestrationConfig(
            goal="Implement one bounded acceptance change",
            planner="kimi-swarm",
            fallback_planner="codex",
            worker="codex",
            apply=True,
        ),
        repo,
    )
    events.append("pause:task-approval")
    assert first.status == OrchestrationStatus.AWAITING_TASK_APPROVAL.value
    assert worker_calls == finalize_calls == []
    task_path = repo / "tasks" / TASK_NAME
    assert "STATUS: DRAFT" in task_path.read_text(encoding="utf-8")

    def controlled_worker(tasks_dir: Path, task_id: str, **kwargs) -> AutoPipelineResult:
        events.append("worker:codex:implementation-only")
        worker_calls.append(kwargs["worker"].allowed_scope)
        bundle = _bundle(repo, events)
        return AutoPipelineResult(
            status=AutoPipelineStatus.READY_FOR_APPROVAL,
            task=Task(task_id, "Controlled acceptance", "READY", TASK_NAME, task_path),
            review_bundle_path=bundle,
            messages=["worker has no approval or finalization authority"],
        )

    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.run_auto_pipeline", controlled_worker
    )
    second = run_orchestration(
        OrchestrationConfig(
            resume_run_id=first.run_id,
            owner_action=OwnerAction.APPROVE_TASK,
            apply=True,
        ),
        repo,
    )
    events.extend(["owner:task-approved", "pause:implementation-decision"])
    assert second.status == OrchestrationStatus.AWAITING_IMPLEMENTATION_DECISION.value
    assert worker_calls == [["bounded.py"]]
    assert finalize_calls == []
    assert _git(repo, "status", "--porcelain") == "?? bounded.py"
    assert _git(repo, "show", "--name-only", "--format=", "HEAD") == f"tasks/{TASK_NAME}"

    def controlled_finalize(*_, **__) -> FinalizationResult:
        events.append("finalization:delegated-feature-branch")
        finalize_calls.append("feature/task-029")
        return FinalizationResult(
            ok=True,
            status=FinalizationStatus.PUSHED,
            task_id=TASK_ID,
            branch="feature/task-029",
            commit_sha="controlled-finalization-evidence",
            messages=["recorded intent only; no live remote invoked"],
        )

    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.run_finalization", controlled_finalize
    )
    final = run_orchestration(
        OrchestrationConfig(
            resume_run_id=first.run_id,
            owner_action=OwnerAction.APPROVE_IMPLEMENTATION,
            apply=True,
        ),
        repo,
    )
    events.append("owner:implementation-approved")
    assert final.status == OrchestrationStatus.PUBLISHED.value
    assert finalize_calls == ["feature/task-029"]
    assert events.index("planner:kimi-swarm:unavailable") < events.index("planner:codex:fallback")
    assert events.index("worker:codex:implementation-only") < events.index("runner:verification:passed")
    assert events.index("runner:verification:passed") < events.index("finalization:delegated-feature-branch")
    checkpoint = load_checkpoint(first.run_id, repo)
    assert checkpoint.owner_action_actor == "owner"
    assert checkpoint.push_verified is True
    assert _git(repo, "remote") == ""


def test_reconcile_historical_task_029_shape_after_later_feature_commit(tmp_path: Path):
    """Recognize canonical historical authority without replaying publication."""
    repo = _repo(tmp_path)
    task_path = repo / "tasks" / TASK_NAME
    task_path.write_text(_task_text("APPROVED"), encoding="utf-8")
    _git(repo, "add", f"tasks/{TASK_NAME}")
    _git(repo, "commit", "-m", "approved controlled task")
    review_head = _git(repo, "rev-parse", "HEAD")

    bundle = ReviewBundle(
        timestamp="2026-08-23T00:00:00+00:00",
        task_id=TASK_ID,
        task_filename=TASK_NAME,
        previous_status="READY",
        current_status="REVIEW",
        branch="feature/task-029",
        pre_head=review_head,
        post_head=review_head,
        runner_status="COMPLETED",
        worker_type="codex-controlled-fake",
        worker_success=True,
        post_verification_ok=True,
    )
    bundle_path = repo / ".agent_runner" / "review" / "historical.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(json.dumps(serialize_bundle(bundle)), encoding="utf-8")
    decision = build_controller_decision(
        bundle_path, bundle, decision=DecisionValue.APPROVE,
        actor_role=ActorRole.OWNER, task_id=TASK_ID,
        task_filename=TASK_NAME, repo_root=repo,
    )
    decision_path = write_controller_decision(decision, default_decisions_dir(repo))

    (repo / "bounded.py").write_text("accepted = True\n", encoding="utf-8")
    _git(repo, "add", "bounded.py")
    _git(repo, "commit", "-m", "historical finalized implementation")
    finalized_commit = _git(repo, "rev-parse", "HEAD")
    finalize_path = repo / ".agent_runner" / "finalize" / "finalize.jsonl"
    finalize_path.parent.mkdir(parents=True)
    finalize_path.write_text(json.dumps({
        "timestamp": "2026-08-23T00:01:00+00:00", "mode": "finalize",
        "status": "PUSHED", "task_id": TASK_ID, "task_filename": TASK_NAME,
        "branch": "feature/task-029", "pre_head": review_head,
        "post_head": finalized_commit, "commit_sha": finalized_commit,
        "decision_path": str(decision_path.relative_to(repo)),
        "bundle_path": str(bundle_path.relative_to(repo)),
    }) + "\n", encoding="utf-8")

    (repo / "later-authorized.txt").write_text("later work\n", encoding="utf-8")
    _git(repo, "add", "later-authorized.txt")
    _git(repo, "commit", "-m", "later authorized feature work")
    synchronized_tip = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/feature/task-029", synchronized_tip)
    checkpoint = OrchestrationCheckpoint(
        schema_version="advancore-orchestration-v1", run_id="ORCH-task-029-history",
        goal_hash="0123456789abcdef", goal_summary="Historical TASK-029",
        planner="kimi-swarm", fallback_planner="codex", worker="codex",
        controller="manual", repair_attempts=0, max_rework=0, apply=True,
        phase=OrchestrationPhase.FINALIZATION.value,
        status=OrchestrationStatus.STALE_EVIDENCE.value,
        branch="feature/task-029", expected_head=review_head,
        task_id=TASK_ID, task_path=str(task_path.relative_to(repo)),
    )
    checkpoint_path = save_checkpoint(checkpoint, repo)
    evidence_before = {
        path: path.read_bytes() for path in (bundle_path, decision_path, finalize_path)
    }
    preview_state = {
        "checkpoint": checkpoint_path.read_bytes(), "head": _git(repo, "rev-parse", "HEAD"),
        "status": _git(repo, "status", "--porcelain"),
        "index": _git(repo, "diff", "--cached", "--binary"),
        "branch": _git(repo, "symbolic-ref", "--short", "HEAD"),
        "local": _git(repo, "rev-parse", "refs/heads/feature/task-029"),
        "tracking": _git(repo, "rev-parse", "refs/remotes/origin/feature/task-029"),
    }

    preview = reconcile_completed_run(checkpoint.run_id, repo)
    assert preview.ok and preview.status == OrchestrationStatus.STALE_EVIDENCE.value
    assert checkpoint_path.read_bytes() == preview_state["checkpoint"]
    assert _git(repo, "rev-parse", "HEAD") == preview_state["head"]
    assert _git(repo, "status", "--porcelain") == preview_state["status"]
    assert _git(repo, "diff", "--cached", "--binary") == preview_state["index"]
    assert _git(repo, "symbolic-ref", "--short", "HEAD") == preview_state["branch"]
    assert _git(repo, "rev-parse", "refs/heads/feature/task-029") == preview_state["local"]
    assert _git(repo, "rev-parse", "refs/remotes/origin/feature/task-029") == preview_state["tracking"]

    applied = reconcile_completed_run(checkpoint.run_id, repo, apply=True)
    reconciled = load_checkpoint(checkpoint.run_id, repo)
    assert applied.status == OrchestrationStatus.PUBLISHED.value
    assert reconciled.commit_sha == finalized_commit
    assert reconciled.expected_head == synchronized_tip
    assert reconciled.review_bundle_path == str(bundle_path.relative_to(repo))
    assert {path: path.read_bytes() for path in evidence_before} == evidence_before


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (AutoPipelineStatus.WORKER_FAILED, OrchestrationStatus.FAILED),
        (AutoPipelineStatus.TEST_FAILED, OrchestrationStatus.FAILED),
        (AutoPipelineStatus.SCOPE_FAILED, OrchestrationStatus.FAILED),
    ],
)
def test_worker_verification_and_publication_attempts_fail_closed(
    tmp_path: Path, monkeypatch, status: AutoPipelineStatus, expected: OrchestrationStatus
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.generate_goal_task",
        lambda **_: _generation(repo, []),
    )
    paused = run_orchestration(OrchestrationConfig(goal="bounded", apply=True), repo)
    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.run_auto_pipeline",
        lambda *_, **__: AutoPipelineResult(status=status, messages=["controlled failure evidence"]),
    )
    result = run_orchestration(
        OrchestrationConfig(
            resume_run_id=paused.run_id,
            owner_action=OwnerAction.APPROVE_TASK,
            apply=True,
        ),
        repo,
    )
    assert result.status == expected.value
    assert result.blocking_reason == f"Auto-pipeline terminal status: {status.value}"
    assert load_checkpoint(paused.run_id, repo).push_verified is False
    assert _git(repo, "remote") == ""


def test_malformed_planner_output_stops_before_task_or_worker(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.generate_goal_task",
        lambda **_: GoalTaskGenerationResult(
            ok=False,
            status=GoalTaskGenerationStatus.PROPOSAL_REJECTED,
            planner_type="codex",
            proposal_valid=False,
            messages=["malformed controlled proposal"],
        ),
    )
    result = run_orchestration(OrchestrationConfig(goal="bounded", apply=True), repo)
    assert result.status == OrchestrationStatus.FAILED.value
    assert result.blocking_reason == "Goal-task generation failed: proposal_rejected"
    assert not list((repo / "tasks").glob("TASK-*.md"))
    assert _git(repo, "remote") == ""


def test_task_approval_preflight_rejects_unrelated_dirty_path_before_transition(
    tmp_path: Path, monkeypatch
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.generate_goal_task",
        lambda **_: _generation(repo, []),
    )
    paused = run_orchestration(OrchestrationConfig(goal="bounded", apply=True), repo)
    task_path = repo / "tasks" / TASK_NAME
    (repo / "unrelated.txt").write_text("owner work\n", encoding="utf-8")

    with pytest.raises(OrchestrationError, match="only"):
        run_orchestration(
            OrchestrationConfig(
                resume_run_id=paused.run_id,
                owner_action=OwnerAction.APPROVE_TASK,
                apply=True,
            ),
            repo,
        )
    assert "STATUS: DRAFT" in task_path.read_text(encoding="utf-8")
    assert _git(repo, "diff", "--cached", "--name-only") == ""


def test_task_approval_preflight_rejects_main_before_transition(
    tmp_path: Path, monkeypatch
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "advancore.agent_runner.orchestration.generate_goal_task",
        lambda **_: _generation(repo, []),
    )
    paused = run_orchestration(OrchestrationConfig(goal="bounded", apply=True), repo)
    _git(repo, "branch", "-m", "main")
    task_path = repo / "tasks" / TASK_NAME

    with pytest.raises(OrchestrationError, match="Branch mismatch|non-main"):
        run_orchestration(
            OrchestrationConfig(
                resume_run_id=paused.run_id,
                owner_action=OwnerAction.APPROVE_TASK,
                apply=True,
            ),
            repo,
        )
    assert "STATUS: DRAFT" in task_path.read_text(encoding="utf-8")
