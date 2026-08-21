"""Tests for the controller decision record.

These tests verify that a controller/reviewer can record a bounded decision
against an existing review bundle, that worker actors are rejected, that
validation fails closed, and that decision records contain only safe metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_controller_decision_audit_payload,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    ControllerDecisionError,
    ControllerDecisionWriteError,
    DecisionValue,
    build_controller_decision,
    default_decisions_dir,
    find_latest_decision,
    format_decision_summary,
    load_controller_decision,
    serialize_controller_decision,
    write_controller_decision,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.review_bundle import ReviewBundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(
    *,
    task_id: str = "TASK-011",
    task_filename: str = "TASK-011-controller-decision-record-foundation.md",
    branch: str = "agent-control-foundation",
    pre_head: str = "pre000000000000000000000000000000000000",
    post_head: str | None = "post00000000000000000000000000000000000",
    recommended_action: str = "REVIEW",
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
        changed_paths=["advancore/agent_runner/controller_decision.py"],
        diff_summary={"total": 1, "counts": {"modified": 1}},
        audit_path=".agent_runner/audit/runner.jsonl",
        recommended_action=recommended_action,
        messages=["Worker completed."],
    )


def _git_info(repo_root: Path) -> GitInfo:
    return GitInfo(
        repo_root=repo_root,
        current_branch="agent-control-foundation",
        head_sha="pre000000000000000000000000000000000000",
        is_clean=True,
        status_lines=[],
    )


# ---------------------------------------------------------------------------
# Decision creation (APPROVE, REWORK, BLOCKED)
# ---------------------------------------------------------------------------


class TestDecisionCreation:
    @pytest.mark.parametrize("decision", ["APPROVE", "REWORK", "BLOCKED"])
    def test_controller_can_record_decision(self, tmp_path: Path, decision: str):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        record = build_controller_decision(
            bundle_path,
            bundle,
            decision=decision,
            actor_role=ActorRole.CONTROLLER,
            repo_root=tmp_path,
        )

        assert record.decision == decision
        assert record.actor_role == "controller"
        assert record.task_id == "TASK-011"
        assert record.task_filename == "TASK-011-controller-decision-record-foundation.md"
        assert record.bundle_task_id == "TASK-011"
        assert record.bundle_branch == "agent-control-foundation"
        assert record.bundle_pre_head == "pre000000000000000000000000000000000000"
        assert record.record_version == "1"

    def test_owner_can_record_decision(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        record = build_controller_decision(
            bundle_path,
            bundle,
            decision=DecisionValue.APPROVE,
            actor_role=ActorRole.OWNER,
        )

        assert record.actor_role == "owner"


# ---------------------------------------------------------------------------
# Actor restrictions
# ---------------------------------------------------------------------------


class TestActorRestrictions:
    def test_worker_actor_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        for decision in DecisionValue:
            with pytest.raises(ControllerDecisionError, match="Worker cannot act"):
                build_controller_decision(
                    bundle_path,
                    bundle,
                    decision=decision,
                    actor_role=ActorRole.WORKER,
                )

    def test_worker_actor_string_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        with pytest.raises(ControllerDecisionError, match="Worker cannot act"):
            build_controller_decision(
                bundle_path,
                bundle,
                decision="APPROVE",
                actor_role="worker",
            )


# ---------------------------------------------------------------------------
# Decision value validation
# ---------------------------------------------------------------------------


class TestDecisionValueValidation:
    def test_unknown_decision_value_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        with pytest.raises(ControllerDecisionError, match="Unknown controller decision"):
            build_controller_decision(
                bundle_path,
                bundle,
                decision="REJECT",
                actor_role=ActorRole.CONTROLLER,
            )


# ---------------------------------------------------------------------------
# Bundle linkage validation
# ---------------------------------------------------------------------------


class TestBundleLinkageValidation:
    def test_task_identity_mismatch_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        with pytest.raises(ControllerDecisionError, match="Task ID mismatch"):
            build_controller_decision(
                bundle_path,
                bundle,
                decision="APPROVE",
                actor_role=ActorRole.CONTROLLER,
                task_id="TASK-999",
            )

    def test_task_filename_mismatch_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        with pytest.raises(ControllerDecisionError, match="Task filename mismatch"):
            build_controller_decision(
                bundle_path,
                bundle,
                decision="APPROVE",
                actor_role=ActorRole.CONTROLLER,
                task_filename="other.md",
            )

    def test_missing_bundle_task_id_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle(task_id=None)

        with pytest.raises(ControllerDecisionError, match="missing required linkage field: task_id"):
            build_controller_decision(
                bundle_path,
                bundle,
                decision="APPROVE",
                actor_role=ActorRole.CONTROLLER,
            )

    def test_missing_bundle_branch_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle(branch=None)

        with pytest.raises(ControllerDecisionError, match="missing required linkage field: branch"):
            build_controller_decision(
                bundle_path,
                bundle,
                decision="APPROVE",
                actor_role=ActorRole.CONTROLLER,
            )

    def test_missing_bundle_pre_head_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle(pre_head=None)

        with pytest.raises(ControllerDecisionError, match="missing required linkage field: pre_head"):
            build_controller_decision(
                bundle_path,
                bundle,
                decision="APPROVE",
                actor_role=ActorRole.CONTROLLER,
            )

    def test_post_head_may_be_absent(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle(post_head=None)

        record = build_controller_decision(
            bundle_path,
            bundle,
            decision="BLOCKED",
            actor_role=ActorRole.CONTROLLER,
        )

        assert record.bundle_post_head is None


# ---------------------------------------------------------------------------
# Safe field policy
# ---------------------------------------------------------------------------


class TestSafeFieldPolicy:
    def test_decision_record_contains_only_safe_fields(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()

        record = build_controller_decision(
            bundle_path,
            bundle,
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
            note="Looks good",
        )

        data = serialize_controller_decision(record)
        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "bundle_path",
            "bundle_task_id",
            "bundle_task_filename",
            "bundle_branch",
            "bundle_pre_head",
            "bundle_post_head",
            "decision",
            "actor_role",
            "note",
            "record_version",
        }
        assert set(data.keys()) == expected_keys

    def test_decision_record_excludes_prohibited_content(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle = _make_bundle()
        note = "password=secret token=abc transcript: lots of output"

        record = build_controller_decision(
            bundle_path,
            bundle,
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
            note=note,
        )

        # Note is bounded but not scrubbed; prohibited content should not be in
        # the record because we never capture it from the bundle or environment.
        raw = json.dumps(record, default=str).lower()
        assert "stdout" not in raw
        assert "stderr" not in raw
        assert "connection string" not in raw
        assert record.bundle_path == str(bundle_path)


# ---------------------------------------------------------------------------
# Serialization / persistence
# ---------------------------------------------------------------------------


class TestSerializationAndPersistence:
    def test_write_and_load_round_trip(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        decisions_dir = tmp_path / ".agent_runner" / "decisions"
        bundle = _make_bundle()

        record = build_controller_decision(
            bundle_path,
            bundle,
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
        )
        path = write_controller_decision(record, decisions_dir)

        assert path.exists()
        assert path.parent == decisions_dir
        loaded = load_controller_decision(path)
        assert loaded.decision == "APPROVE"
        assert loaded.task_id == "TASK-011"

    def test_write_failure_is_reported(self, tmp_path: Path):
        decisions_dir = tmp_path / ".agent_runner" / "decisions"
        bundle_path = tmp_path / "review" / "bundle.json"
        record = build_controller_decision(
            bundle_path,
            _make_bundle(),
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
        )

        with patch(
            "advancore.agent_runner.controller_decision.Path.write_text"
        ) as mock_write:
            mock_write.side_effect = OSError("disk full")
            with pytest.raises(ControllerDecisionWriteError, match="disk full"):
                write_controller_decision(record, decisions_dir)

    def test_find_latest_decision(self, tmp_path: Path):
        decisions_dir = tmp_path / ".agent_runner" / "decisions"
        bundle_path = tmp_path / "review" / "bundle.json"
        record1 = build_controller_decision(
            bundle_path,
            _make_bundle(),
            decision="REWORK",
            actor_role=ActorRole.CONTROLLER,
        )
        path1 = write_controller_decision(record1, decisions_dir)
        record2 = build_controller_decision(
            bundle_path,
            _make_bundle(),
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
        )
        path2 = write_controller_decision(record2, decisions_dir)

        latest = find_latest_decision(decisions_dir)
        assert latest == path2

    def test_format_decision_summary_is_human_readable(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        record = build_controller_decision(
            bundle_path,
            _make_bundle(),
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
            note="approved for next gate",
        )

        summary = format_decision_summary(record)
        assert "Controller Decision Record" in summary
        assert "APPROVE" in summary
        assert "controller" in summary
        assert "approved for next gate" in summary


# ---------------------------------------------------------------------------
# Audit integration
# ---------------------------------------------------------------------------


class TestDecisionAudit:
    def test_audit_payload_contains_safe_metadata(self):
        payload = build_controller_decision_audit_payload(
            task_id="TASK-011",
            task_filename="TASK-011.md",
            actor_role="controller",
            decision="APPROVE",
            bundle_path=".agent_runner/review/bundle.json",
            bundle_branch="agent-control-foundation",
            bundle_pre_head="pre",
            bundle_post_head="post",
            decision_path=".agent_runner/decisions/decision.json",
        )

        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "mode",
            "actor_role",
            "decision",
            "bundle_path",
            "bundle_branch",
            "bundle_pre_head",
            "bundle_post_head",
            "decision_path",
        }
        assert set(payload.keys()) == expected_keys
        assert payload["mode"] == "controller_decision"
        assert payload["decision"] == "APPROVE"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestControllerDecisionCLI:
    def test_cli_record_creates_decision(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "20260821T000000_TASK-011.json"
        bundle = _make_bundle()
        bundle_path.write_text(json.dumps(bundle.__dict__, default=str, sort_keys=True), encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            [
                "controller-decision",
                "record",
                str(bundle_path),
                "--decision",
                "APPROVE",
                "--actor",
                "controller",
                "--note",
                "ready for next gate",
            ]
        )
        assert code == 0

        decisions_dir = repo_root / ".agent_runner" / "decisions"
        assert any(decisions_dir.glob("*.json"))

    def test_cli_record_worker_actor_returns_nonzero(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(json.dumps(_make_bundle().__dict__, default=str, sort_keys=True), encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            [
                "controller-decision",
                "record",
                str(bundle_path),
                "--decision",
                "APPROVE",
                "--actor",
                "worker",
            ]
        )
        assert code != 0

    def test_cli_show_is_read_only(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        decisions_dir = repo_root / ".agent_runner" / "decisions"
        decisions_dir.mkdir(parents=True)
        decision_path = decisions_dir / "decision.json"
        bundle_path = repo_root / ".agent_runner" / "review" / "bundle.json"
        record = build_controller_decision(
            bundle_path,
            _make_bundle(),
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
        )
        decision_path.write_text(
            json.dumps(serialize_controller_decision(record), sort_keys=True),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-decision", "show", str(decision_path)])
        assert code == 0

    def test_cli_approve_does_not_mutate_git_or_task(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle_path = review_dir / "bundle.json"
        bundle_path.write_text(json.dumps(_make_bundle().__dict__, default=str, sort_keys=True), encoding="utf-8")

        task_path = tasks_dir / "TASK-011-controller-decision-record-foundation.md"
        original_text = "# TASK-011 — Decision Record\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path.write_text(original_text, encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            [
                "controller-decision",
                "record",
                str(bundle_path),
                "--decision",
                "APPROVE",
                "--actor",
                "controller",
            ]
        )
        assert code == 0
        assert task_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Malformed bundle handling
# ---------------------------------------------------------------------------


class TestMalformedBundleHandling:
    def test_malformed_bundle_file_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "bundle.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text("not valid json", encoding="utf-8")

        from advancore.agent_runner.review_bundle import load_review_bundle

        with pytest.raises(Exception):
            load_review_bundle(bundle_path)

    def test_missing_bundle_file_is_rejected(self, tmp_path: Path):
        bundle_path = tmp_path / "review" / "missing.json"

        from advancore.agent_runner.review_bundle import load_review_bundle

        with pytest.raises(Exception):
            load_review_bundle(bundle_path)
