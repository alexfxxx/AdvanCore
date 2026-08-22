"""Tests for the controller handoff queue.

These tests verify that a valid review bundle can be turned into a bounded
local handoff request, that a matching controller decision can be reconciled
back to that request, and that every failure mode fails closed without mutating
task files, Git state, or lifecycle state.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner.audit import build_handoff_audit_payload
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    ControllerDecisionError,
    build_controller_decision,
    default_decisions_dir,
    find_latest_decision,
    load_controller_decision,
    serialize_controller_decision,
    write_controller_decision,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoff,
    ControllerHandoffError,
    ControllerHandoffWriteError,
    HandoffState,
    build_controller_handoff,
    default_handoff_dir,
    find_latest_handoff,
    format_handoff_summary,
    load_controller_handoff,
    reconcile_controller_handoff,
    write_controller_handoff,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.review_bundle import (
    ControllerAction,
    ReviewBundle,
    ReviewBundleError,
    load_review_bundle,
    write_review_bundle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(
    *,
    task_id: str = "TASK-013",
    task_filename: str = "TASK-013-controller-handoff-queue-foundation.md",
    branch: str = "agent-control-foundation",
    pre_head: str = "pre000000000000000000000000000000000000",
    post_head: str | None = "post00000000000000000000000000000000000",
    recommended_action: str = ControllerAction.REVIEW.value,
    runner_status: str = "awaiting_approval",
) -> ReviewBundle:
    return ReviewBundle(
        timestamp="2026-08-21T00:00:00+00:00",
        task_id=task_id,
        task_filename=task_filename,
        previous_status="REVIEW",
        current_status="REVIEW",
        branch=branch,
        pre_head=pre_head,
        post_head=post_head,
        runner_status=runner_status,
        worker_type="kimi",
        worker_success=True,
        post_verification_ok=True,
        post_verification_messages=["PASS: branch unchanged"],
        changed_paths=["advancore/agent_runner/controller_handoff.py"],
        diff_summary={"total": 1, "counts": {"modified": 1}},
        audit_path=".agent_runner/audit/runner.jsonl",
        recommended_action=recommended_action,
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
# Request creation
# ---------------------------------------------------------------------------


class TestHandoffRequestCreation:
    def test_valid_bundle_creates_waiting_decision_request(self, tmp_path: Path):
        bundle_path = tmp_path / ".agent_runner" / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle()

        handoff = build_controller_handoff(bundle_path, bundle)

        assert handoff.state == HandoffState.WAITING_DECISION.value
        assert handoff.task_id == "TASK-013"
        assert handoff.task_filename == "TASK-013-controller-handoff-queue-foundation.md"

    def test_request_contains_correct_metadata(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle()

        handoff = build_controller_handoff(
            bundle_path,
            bundle,
            git_info=_git_info(tmp_path, head_sha=bundle.pre_head),
            repo_root=tmp_path,
        )

        assert handoff.bundle_path == str(bundle_path.relative_to(tmp_path))
        assert handoff.bundle_branch == "agent-control-foundation"
        assert handoff.bundle_pre_head == "pre000000000000000000000000000000000000"
        assert handoff.bundle_post_head == "post00000000000000000000000000000000000"
        assert handoff.bundle_recommended_action == ControllerAction.REVIEW.value
        assert handoff.request_version == "1"
        assert handoff.request_id.startswith("CHR-")

    def test_request_excludes_sensitive_and_full_content_fields(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle()
        bundle.messages = ["password=secret token=abc transcript: lots of output"]

        handoff = build_controller_handoff(bundle_path, bundle)
        raw = json.dumps(handoff.__dict__, default=str).lower()

        assert "password" not in raw
        assert "token" not in raw
        assert "transcript" not in raw
        assert "stdout" not in raw
        assert "stderr" not in raw
        assert "business secret" not in raw


# ---------------------------------------------------------------------------
# Prepare validation failures
# ---------------------------------------------------------------------------


class TestHandoffPrepareValidation:
    def test_missing_review_bundle_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "missing.json"

        with pytest.raises(ReviewBundleError):
            load_review_bundle(bundle_path)

    def test_malformed_review_bundle_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bad.json"
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_text("not valid json", encoding="utf-8")

        with pytest.raises(ReviewBundleError):
            load_review_bundle(bundle_path)

    def test_missing_bundle_task_id_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle(task_id=None)

        with pytest.raises(ControllerHandoffError, match="missing required handoff field: task_id"):
            build_controller_handoff(bundle_path, bundle)

    def test_missing_bundle_task_filename_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle(task_filename=None)

        with pytest.raises(
            ControllerHandoffError, match="missing required handoff field: task_filename"
        ):
            build_controller_handoff(bundle_path, bundle)

    def test_missing_bundle_branch_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle(branch=None)

        with pytest.raises(ControllerHandoffError, match="missing required handoff field: branch"):
            build_controller_handoff(bundle_path, bundle)

    def test_missing_bundle_pre_head_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle(pre_head=None)

        with pytest.raises(
            ControllerHandoffError, match="missing required handoff field: pre_head"
        ):
            build_controller_handoff(bundle_path, bundle)

    @pytest.mark.parametrize("action", ["APPROVED", "MERGE", "COMMIT", "UNKNOWN"])
    def test_unsupported_recommended_action_is_rejected(self, tmp_path: Path, action: str):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle(recommended_action=action)

        with pytest.raises(ControllerHandoffError, match="Unsupported review-bundle recommended"):
            build_controller_handoff(bundle_path, bundle)

    def test_current_branch_mismatch_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle = _make_bundle(branch="feature-branch")
        git_info = _git_info(tmp_path, branch="agent-control-foundation")

        with pytest.raises(ControllerHandoffError, match="Branch mismatch"):
            build_controller_handoff(bundle_path, bundle, git_info=git_info)


# ---------------------------------------------------------------------------
# Serialization / persistence
# ---------------------------------------------------------------------------


class TestHandoffSerialization:
    def test_write_and_load_roundtrip(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        handoff_dir = tmp_path / ".agent_runner" / "controller_handoff"
        bundle = _make_bundle()
        handoff = build_controller_handoff(bundle_path, bundle)

        path = write_controller_handoff(handoff, handoff_dir)

        assert path.exists()
        assert path.parent == handoff_dir
        loaded = load_controller_handoff(path)
        assert loaded.request_id == handoff.request_id
        assert loaded.state == HandoffState.WAITING_DECISION.value

    def test_load_invalid_file_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        with pytest.raises(ControllerHandoffError):
            load_controller_handoff(path)

    def test_write_failure_is_reported(self, tmp_path: Path):
        handoff_dir = tmp_path / ".agent_runner" / "controller_handoff"
        handoff = build_controller_handoff(tmp_path / "review" / "bundle.json", _make_bundle())

        with patch("advancore.agent_runner.controller_handoff.Path.write_text") as mock_write:
            mock_write.side_effect = OSError("disk full")
            with pytest.raises(ControllerHandoffWriteError, match="disk full"):
                write_controller_handoff(handoff, handoff_dir)

    def test_find_latest_handoff(self, tmp_path: Path):
        handoff_dir = tmp_path / "handoffs"
        handoff1 = build_controller_handoff(tmp_path / "b1.json", _make_bundle())
        path1 = write_controller_handoff(handoff1, handoff_dir)
        handoff2 = build_controller_handoff(tmp_path / "b2.json", _make_bundle())
        path2 = write_controller_handoff(handoff2, handoff_dir)

        latest = find_latest_handoff(handoff_dir)
        assert latest == path2


# ---------------------------------------------------------------------------
# Reconciliation happy path
# ---------------------------------------------------------------------------


class TestHandoffReconciliation:
    def test_valid_matching_decision_reconciles(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(
            bundle_path, bundle, repo_root=repo_root
        )
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is True
        assert result.handoff is not None
        assert result.handoff.state == HandoffState.DECISION_RECEIVED.value
        assert result.handoff.decision == "APPROVE"
        assert result.handoff.decision_path is not None

        reloaded = load_controller_handoff(request_path)
        assert reloaded.state == HandoffState.DECISION_RECEIVED.value
        assert reloaded.decision == "APPROVE"

    def test_reconcile_does_not_mutate_lifecycle_state(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        original_text = "# TASK-013 — Handoff\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path = tasks_dir / "TASK-013-controller-handoff-queue-foundation.md"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert task_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Reconciliation authority and linkage validation
# ---------------------------------------------------------------------------


class TestReconciliationAuthority:
    def test_worker_actor_decision_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        # Build a valid controller decision, then tamper with the actor role.
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision.actor_role = "worker"
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "worker cannot act" in " ".join(result.messages).lower()

    def test_task_id_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        wrong_bundle = _make_bundle(task_id="TASK-999")
        decision = build_controller_decision(
            bundle_path,
            wrong_bundle,
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
            repo_root=repo_root,
        )
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "task id mismatch" in " ".join(result.messages).lower()

    def test_task_filename_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        wrong_bundle = _make_bundle(task_filename="TASK-013-other.md")
        decision = build_controller_decision(
            bundle_path,
            wrong_bundle,
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
            repo_root=repo_root,
        )
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "filename mismatch" in " ".join(result.messages).lower()

    def test_bundle_reference_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        other_bundle_path = review_dir / "other.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        other_bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        decision = _make_decision(other_bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "review-bundle reference mismatch" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# Missing / malformed decision record
# ---------------------------------------------------------------------------


class TestReconciliationDecisionLoading:
    def test_missing_decision_record_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        handoff_dir = default_handoff_dir(repo_root)
        handoff_dir.mkdir(parents=True)
        handoff = build_controller_handoff(
            repo_root / "review" / "bundle.json", _make_bundle()
        )
        request_path = write_controller_handoff(handoff, handoff_dir)
        missing_decision = repo_root / ".agent_runner" / "decisions" / "missing.json"

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=missing_decision,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "cannot load controller decision" in " ".join(result.messages).lower()

    def test_malformed_decision_record_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        handoff_dir = default_handoff_dir(repo_root)
        handoff_dir.mkdir(parents=True)
        handoff = build_controller_handoff(
            repo_root / "review" / "bundle.json", _make_bundle()
        )
        request_path = write_controller_handoff(handoff, handoff_dir)
        decisions_dir = repo_root / ".agent_runner" / "decisions"
        decisions_dir.mkdir(parents=True)
        decision_path = decisions_dir / "bad.json"
        decision_path.write_text("not valid json", encoding="utf-8")

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "cannot load controller decision" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# Idempotency and conflict protection
# ---------------------------------------------------------------------------


class TestReconciliationIdempotency:
    def test_same_decision_reconciliation_is_idempotent(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result1 = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result1.ok is True

        result2 = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result2.ok is True
        assert "already reconciled" in " ".join(result2.messages).lower()

    def test_different_decision_reconciliation_fails_closed(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        approve_decision = _make_decision(
            bundle_path, bundle, decision="APPROVE", repo_root=repo_root
        )
        rework_decision = _make_decision(
            bundle_path, bundle, decision="REWORK", repo_root=repo_root
        )
        decisions_dir = default_decisions_dir(repo_root)
        approve_path = write_controller_decision(approve_decision, decisions_dir)
        rework_path = write_controller_decision(rework_decision, decisions_dir)

        first = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=approve_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert first.ok is True

        second = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=rework_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert second.ok is False
        assert "already reconciled to a different decision" in " ".join(second.messages).lower()

        reloaded = load_controller_handoff(request_path)
        assert reloaded.decision == "APPROVE"


# ---------------------------------------------------------------------------
# Branch / HEAD consistency during reconciliation
# ---------------------------------------------------------------------------


class TestReconciliationEvidenceConsistency:
    def test_branch_evidence_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(branch="feature-branch")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(
            bundle_path, bundle, repo_root=repo_root
        )
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        # Decision built from a bundle with a different branch.
        decision = _make_decision(
            bundle_path, bundle, decision="APPROVE", repo_root=repo_root
        )
        # Tamper with the stored branch evidence to simulate inconsistency.
        decision.bundle_branch = "other-branch"
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "branch evidence mismatch" in " ".join(result.messages).lower()

    def test_pre_head_evidence_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        handoff = build_controller_handoff(bundle_path, bundle, repo_root=repo_root)
        handoff_dir = default_handoff_dir(repo_root)
        request_path = write_controller_handoff(handoff, handoff_dir)

        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision.bundle_pre_head = "tampered0000000000000000000000000000000"
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        assert result.ok is False
        assert "pre head evidence mismatch" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# Read-only inspection
# ---------------------------------------------------------------------------


class TestHandoffReadOnlyInspection:
    def test_show_does_not_mutate_git_or_artifact(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        handoff_dir = default_handoff_dir(repo_root)
        handoff_dir.mkdir(parents=True)
        handoff = build_controller_handoff(
            repo_root / "review" / "bundle.json", _make_bundle()
        )
        request_path = write_controller_handoff(handoff, handoff_dir)
        original_text = request_path.read_text(encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        with patch("advancore.agent_runner.git_info.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            code = main(["controller-handoff", "show", str(request_path)])

        assert code == 0
        assert request_path.read_text(encoding="utf-8") == original_text
        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "checkout" not in args
            assert "reset" not in args

    def test_format_summary_is_human_readable(self, tmp_path: Path):
        handoff = build_controller_handoff(tmp_path / "review" / "bundle.json", _make_bundle())
        summary = format_handoff_summary(handoff)
        assert "Controller Handoff Request" in summary
        assert handoff.request_id in summary
        assert HandoffState.WAITING_DECISION.value in summary


# ---------------------------------------------------------------------------
# Audit behavior
# ---------------------------------------------------------------------------


class TestHandoffAudit:
    def test_prepare_writes_audit_record(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-handoff", "prepare", str(bundle_path)])
        assert code == 0

        audit_path = repo_root / ".agent_runner" / "audit" / "runner.jsonl"
        assert audit_path.exists()
        record = _load_last_record(audit_path)
        assert record["mode"] == "handoff_prepare"
        assert record["task_id"] == "TASK-013"
        assert record["state"] == HandoffState.WAITING_DECISION.value
        assert record["request_id"].startswith("CHR-")

    def test_reconcile_writes_audit_record(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        main(["controller-handoff", "prepare", str(bundle_path)])

        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        code = main(
            [
                "controller-handoff",
                "reconcile",
                str(find_latest_handoff(default_handoff_dir(repo_root))),
                str(decision_path),
            ]
        )
        assert code == 0

        audit_path = repo_root / ".agent_runner" / "audit" / "runner.jsonl"
        record = _load_last_record(audit_path)
        assert record["mode"] == "handoff_reconcile"
        assert record["state"] == HandoffState.DECISION_RECEIVED.value
        assert record["decision"] == "APPROVE"

    def test_audit_payload_shape(self):
        payload = build_handoff_audit_payload(
            task_id="TASK-013",
            task_filename="TASK-013.md",
            request_id="CHR-abc",
            mode="handoff_reconcile",
            state=HandoffState.DECISION_RECEIVED.value,
            bundle_path=".agent_runner/review/bundle.json",
            bundle_branch="agent-control-foundation",
            bundle_pre_head="pre",
            bundle_post_head="post",
            decision_path=".agent_runner/decisions/decision.json",
            decision="APPROVE",
            branch="agent-control-foundation",
            head_sha="abc",
        )
        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "request_id",
            "mode",
            "state",
            "bundle_path",
            "bundle_branch",
            "bundle_pre_head",
            "bundle_post_head",
            "decision_path",
            "decision",
            "branch",
            "head_sha",
        }
        assert set(payload.keys()) == expected_keys


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestHandoffCLI:
    def test_cli_prepare_creates_handoff(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-handoff", "prepare", str(bundle_path)])
        assert code == 0

        handoff_dir = default_handoff_dir(repo_root)
        assert any(handoff_dir.glob("*.json"))

    def test_cli_prepare_worker_actor_bundle_is_rejected(self, tmp_path: Path, monkeypatch):
        # Bundle recommended action cannot be APPROVED; this tests unsupported action rejection.
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle(recommended_action="APPROVED")
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-handoff", "prepare", str(bundle_path)])
        assert code != 0

    def test_cli_reconcile_matching_decision(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        main(["controller-handoff", "prepare", str(bundle_path)])

        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        code = main(
            [
                "controller-handoff",
                "reconcile",
                str(find_latest_handoff(default_handoff_dir(repo_root))),
                str(decision_path),
            ]
        )
        assert code == 0

    def test_cli_reconcile_worker_decision_returns_nonzero(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        main(["controller-handoff", "prepare", str(bundle_path)])

        # Build a valid controller decision, then tamper with the actor role.
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision.actor_role = "worker"
        decisions_dir = default_decisions_dir(repo_root)
        decision_path = write_controller_decision(decision, decisions_dir)

        code = main(
            [
                "controller-handoff",
                "reconcile",
                str(find_latest_handoff(default_handoff_dir(repo_root))),
                str(decision_path),
            ]
        )
        assert code != 0

    def test_cli_prepare_does_not_mutate_git_publication_state(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle = _make_bundle()
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        with patch("advancore.agent_runner.git_info.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            main(["controller-handoff", "prepare", str(bundle_path)])

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "checkout" not in args
            assert "reset" not in args
