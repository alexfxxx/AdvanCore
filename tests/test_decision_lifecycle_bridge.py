"""Tests for the controller decision to task lifecycle bridge.

These tests verify that a validated controller decision record can be previewed
and, only with an explicit apply flag, bridged into the existing authority-aware
task lifecycle. They exercise decision mapping, linkage validation, authority
restrictions, fail-closed behavior, and audit metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner.audit import build_bridge_audit_payload
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    ControllerDecisionError,
    DecisionValue,
    build_controller_decision,
    default_decisions_dir,
    find_latest_decision,
    load_controller_decision,
    serialize_controller_decision,
    write_controller_decision,
)
from advancore.agent_runner.decision_lifecycle_bridge import (
    DecisionLifecycleBridgeError,
    DecisionLifecycleResult,
    _map_decision_to_target_status,
    apply_controller_decision,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.lifecycle import ActorRole, TaskStatus
from advancore.agent_runner.review_bundle import ReviewBundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_task(
    tasks_dir: Path,
    task_id: str,
    title: str,
    status: str,
    filename: str | None = None,
) -> Path:
    """Write a minimal task file and return its path."""
    filename = filename or f"{task_id}-sample-task.md"
    path = tasks_dir / filename
    path.write_text(
        f"# {task_id} — {title}\n\nSTATUS: {status}\n\n## Objective\n\nDo the thing.\n",
        encoding="utf-8",
    )
    return path


def _make_bundle(
    *,
    task_id: str = "TASK-012",
    task_filename: str = "TASK-012-sample-task.md",
    branch: str = "agent-control-foundation",
    pre_head: str = "pre000000000000000000000000000000000000",
    post_head: str | None = "post00000000000000000000000000000000000",
    current_status: str = "REVIEW",
    runner_status: str = "awaiting_approval",
) -> ReviewBundle:
    return ReviewBundle(
        timestamp="2026-08-21T00:00:00+00:00",
        task_id=task_id,
        task_filename=task_filename,
        previous_status=current_status,
        current_status=current_status,
        branch=branch,
        pre_head=pre_head,
        post_head=post_head,
        runner_status=runner_status,
        worker_type="kimi",
        worker_success=True,
        post_verification_ok=True,
        post_verification_messages=["PASS: branch unchanged"],
        changed_paths=["advancore/agent_runner/decision_lifecycle_bridge.py"],
        diff_summary={"total": 1, "counts": {"modified": 1}},
        audit_path=".agent_runner/audit/runner.jsonl",
        recommended_action="REVIEW",
        messages=["Worker completed."],
    )


def _make_decision(
    bundle_path: Path,
    bundle: ReviewBundle,
    *,
    decision: str = "APPROVE",
    actor_role: ActorRole = ActorRole.CONTROLLER,
    repo_root: Path | None = None,
) -> ControllerDecision:
    return build_controller_decision(
        bundle_path,
        bundle,
        decision=decision,
        actor_role=actor_role,
        repo_root=repo_root,
    )


def _git_info(
    repo_root: Path,
    branch: str = "agent-control-foundation",
    head_sha: str = "abc1230000000000000000000000000000000000",
) -> GitInfo:
    return GitInfo(
        repo_root=repo_root,
        current_branch=branch,
        head_sha=head_sha,
        is_clean=True,
        status_lines=[],
    )


def _load_last_record(audit_path: Path) -> dict:
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# Decision-to-status mapping
# ---------------------------------------------------------------------------


class TestDecisionMapping:
    @pytest.mark.parametrize(
        "decision, expected",
        [
            ("APPROVE", TaskStatus.APPROVED),
            ("REWORK", TaskStatus.REWORK),
            ("BLOCKED", TaskStatus.BLOCKED),
        ],
    )
    def test_decision_values_map_to_expected_target_status(
        self, decision: str, expected: TaskStatus
    ):
        assert _map_decision_to_target_status(decision) == expected

    def test_unknown_decision_value_is_rejected(self):
        with pytest.raises(DecisionLifecycleBridgeError, match="Unknown controller decision"):
            _map_decision_to_target_status("REJECT")


# ---------------------------------------------------------------------------
# Happy path: preview and apply
# ---------------------------------------------------------------------------


class TestBridgePreviewAndApply:
    def test_approve_preview_is_permitted_for_review_task(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is True
        assert result.decision == "APPROVE"
        assert result.actor_role == "controller"
        assert result.target_status == "APPROVED"
        assert result.transition_allowed is True
        assert result.applied is False
        assert result.mode == "preview"
        assert result.current_status == "REVIEW"

    def test_approve_apply_changes_only_status_line(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        original_text = (
            "# TASK-012 — Bridge Task\n\nSTATUS: REVIEW\n\n## Objective\n\nDo it.\n"
        )
        task_path = tasks_dir / "TASK-012-sample-task.md"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is True
        assert result.applied is True

        new_text = task_path.read_text(encoding="utf-8")
        assert new_text == original_text.replace("STATUS: REVIEW", "STATUS: APPROVED")
        assert new_text.count("STATUS:") == 1

    def test_preview_does_not_mutate_task_file(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        original_text = "# TASK-012 — Bridge Task\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path = tasks_dir / "TASK-012-sample-task.md"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert task_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Lifecycle state-machine obedience
# ---------------------------------------------------------------------------


class TestLifecycleObedience:
    def test_approve_from_ready_is_denied_without_mutation(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        original_text = "# TASK-012 — Bridge Task\n\nSTATUS: READY\n\nBody.\n"
        task_path = tasks_dir / "TASK-012-sample-task.md"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(current_status="READY")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert result.transition_allowed is False
        assert result.applied is False
        assert task_path.read_text(encoding="utf-8") == original_text

    def test_rework_uses_existing_transition_rules(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        task_path = _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(current_status="REVIEW")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(
            bundle_path, bundle, decision="REWORK", repo_root=repo_root
        )
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is True
        assert result.target_status == "REWORK"
        assert result.applied is True
        assert "STATUS: REWORK" in task_path.read_text(encoding="utf-8")

    def test_blocked_from_non_final_state_is_allowed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        task_path = _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(current_status="REVIEW")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(
            bundle_path, bundle, decision="BLOCKED", repo_root=repo_root
        )
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is True
        assert result.target_status == "BLOCKED"
        assert result.applied is True
        assert "STATUS: BLOCKED" in task_path.read_text(encoding="utf-8")

    def test_blocked_from_approved_is_denied(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        original_text = "# TASK-012 — Bridge Task\n\nSTATUS: APPROVED\n\nBody.\n"
        task_path = tasks_dir / "TASK-012-sample-task.md"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(current_status="APPROVED")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(
            bundle_path, bundle, decision="BLOCKED", repo_root=repo_root
        )
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert result.transition_allowed is False
        assert task_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Authority restrictions
# ---------------------------------------------------------------------------


class TestAuthorityRestrictions:
    def test_worker_actor_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        original_text = "# TASK-012 — Bridge Task\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path = tasks_dir / "TASK-012-sample-task.md"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        # Build a valid controller decision, then tamper with the actor role.
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision.actor_role = "worker"
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=True,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert result.applied is False
        assert "worker cannot apply" in " ".join(result.messages).lower()
        assert task_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Linkage validation
# ---------------------------------------------------------------------------


class TestLinkageValidation:
    def test_missing_decision_record_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        missing_path = repo_root / ".agent_runner" / "decisions" / "missing.json"

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=missing_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "cannot load decision record" in " ".join(result.messages).lower()

    def test_malformed_decision_record_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        decisions_dir = repo_root / ".agent_runner" / "decisions"
        decisions_dir.mkdir(parents=True)
        decision_path = decisions_dir / "bad.json"
        decision_path.write_text("not valid json", encoding="utf-8")

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "cannot load decision record" in " ".join(result.messages).lower()

    def test_missing_linked_review_bundle_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        decisions_dir = repo_root / ".agent_runner" / "decisions"
        decisions_dir.mkdir(parents=True)
        decision_path = decisions_dir / "decision.json"
        decision = ControllerDecision(
            timestamp="2026-08-21T00:00:00+00:00",
            task_id="TASK-012",
            task_filename="TASK-012-sample-task.md",
            bundle_path=".agent_runner/review/missing.json",
            bundle_task_id="TASK-012",
            bundle_task_filename="TASK-012-sample-task.md",
            bundle_branch="agent-control-foundation",
            bundle_pre_head="pre",
            bundle_post_head=None,
            decision="APPROVE",
            actor_role="controller",
        )
        decision_path.write_text(
            json.dumps(serialize_controller_decision(decision), sort_keys=True),
            encoding="utf-8",
        )

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "cannot load linked review bundle" in " ".join(result.messages).lower()

    def test_malformed_linked_review_bundle_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text("not valid json", encoding="utf-8")
        decisions_dir = repo_root / ".agent_runner" / "decisions"
        decisions_dir.mkdir(parents=True)
        decision_path = decisions_dir / "decision.json"
        decision = ControllerDecision(
            timestamp="2026-08-21T00:00:00+00:00",
            task_id="TASK-012",
            task_filename="TASK-012-sample-task.md",
            bundle_path=str(bundle_path),
            bundle_task_id="TASK-012",
            bundle_task_filename="TASK-012-sample-task.md",
            bundle_branch="agent-control-foundation",
            bundle_pre_head="pre",
            bundle_post_head=None,
            decision="APPROVE",
            actor_role="controller",
        )
        decision_path.write_text(
            json.dumps(serialize_controller_decision(decision), sort_keys=True),
            encoding="utf-8",
        )

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "cannot load linked review bundle" in " ".join(result.messages).lower()

    def test_decision_bundle_task_id_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")
        # Create a decoy task so the tampered decision task_id can still be found.
        _write_task(tasks_dir, "TASK-999", "Decoy Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        # Tamper with the loaded decision record's task_id.
        decision.task_id = "TASK-999"
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "task id mismatch" in " ".join(result.messages).lower()

    def test_decision_bundle_task_filename_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision.task_filename = "TASK-012-other.md"
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "filename mismatch" in " ".join(result.messages).lower()

    def test_branch_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(branch="feature-branch")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root, branch="agent-control-foundation"),
        )

        assert result.ok is False
        assert "branch mismatch" in " ".join(result.messages).lower()

    def test_linked_task_file_identity_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        # Task file ID does not match decision/bundle.
        _write_task(
            tasks_dir,
            "TASK-999",
            "Wrong Task",
            "REVIEW",
            filename="TASK-999-wrong-task.md",
        )

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "cannot find linked task" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# HEAD freshness evidence
# ---------------------------------------------------------------------------


class TestHeadEvidence:
    def test_head_evidence_is_surfaced_without_rejection(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(
            pre_head="pre000000000000000000000000000000000000",
            post_head="post00000000000000000000000000000000000",
        )
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        git_info = _git_info(
            repo_root,
            head_sha="current0000000000000000000000000000000",
        )
        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=git_info,
        )

        assert result.ok is True
        assert result.head_evidence["current_head"] == "current0000000000000000000000000000000"
        assert result.head_evidence["bundle_pre_head"] == "pre000000000000000000000000000000000000"
        assert result.head_evidence["bundle_post_head"] == "post00000000000000000000000000000000000"
        assert any("HEAD evidence" in msg for msg in result.messages)


# ---------------------------------------------------------------------------
# Audit behavior
# ---------------------------------------------------------------------------


class TestBridgeAudit:
    def test_preview_writes_bridge_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        git_info = _git_info(repo_root)
        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=git_info,
        )

        assert result.audit_path is not None
        assert result.audit_path.exists()
        record = _load_last_record(result.audit_path)
        assert record["mode"] == "bridge"
        assert record["task_id"] == "TASK-012"
        assert record["actor_role"] == "controller"
        assert record["decision"] == "APPROVE"
        assert record["target_status"] == "APPROVED"
        assert record["transition_allowed"] is True
        assert record["applied"] is False
        assert record["branch"] == "agent-control-foundation"
        assert record["head_sha"] == git_info.head_sha
        assert record["decision_path"] is not None
        assert record["bundle_path"] is not None

    def test_rejected_attempt_writes_bridge_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "READY")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(current_status="READY")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = apply_controller_decision(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            decision_path=decision_path,
            apply=False,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        record = _load_last_record(result.audit_path)
        assert record["mode"] == "bridge"
        assert record["transition_allowed"] is False
        assert record["applied"] is False

    def test_audit_payload_shape(self):
        payload = build_bridge_audit_payload(
            task_id="TASK-012",
            task_filename="TASK-012-sample-task.md",
            actor_role="controller",
            decision="APPROVE",
            target_status="APPROVED",
            transition_allowed=True,
            applied=False,
            branch="agent-control-foundation",
            head_sha="abc",
            decision_path=".agent_runner/decisions/decision.json",
            bundle_path=".agent_runner/review/bundle.json",
            bundle_pre_head="pre",
            bundle_post_head="post",
        )
        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "mode",
            "actor_role",
            "decision",
            "target_status",
            "transition_allowed",
            "applied",
            "branch",
            "head_sha",
            "decision_path",
            "bundle_path",
            "bundle_pre_head",
            "bundle_post_head",
        }
        assert set(payload.keys()) == expected_keys
        assert payload["mode"] == "bridge"


# ---------------------------------------------------------------------------
# No-Git-publication side effects
# ---------------------------------------------------------------------------


class TestNoGitPublicationSideEffects:
    def test_apply_does_not_invoke_git_mutation_commands(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        with patch(
            "advancore.agent_runner.git_info.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            main(
                [
                    "controller-decision",
                    "apply",
                    str(decision_path),
                    "--apply",
                ]
            )

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "checkout" not in args
            assert "reset" not in args

    def test_preview_does_not_stage_commit_push_merge(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        original_text = "# TASK-012 — Bridge Task\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path = tasks_dir / "TASK-012-sample-task.md"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-decision", "apply", str(decision_path)])

        assert code == 0
        assert task_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestBridgeCLI:
    def test_cli_apply_preview_returns_zero_for_allowed(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-decision", "apply", str(decision_path)])
        assert code == 0

    def test_cli_apply_explicit_apply_mutates_status_line(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            ["controller-decision", "apply", str(decision_path), "--apply"]
        )
        assert code == 0
        text = (tasks_dir / "TASK-012-sample-task.md").read_text(encoding="utf-8")
        assert "STATUS: APPROVED" in text

    def test_cli_apply_latest_uses_most_recent_decision(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "REVIEW")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        write_controller_decision(decision, decisions_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-decision", "apply"])
        assert code == 0

    def test_cli_apply_denied_returns_nonzero(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-012", "Bridge Task", "READY")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(current_status="READY")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-decision", "apply", str(decision_path)])
        assert code == 1


# Need MagicMock for subprocess patch; import here to avoid unused warning placement.
from unittest.mock import MagicMock  # noqa: E402
