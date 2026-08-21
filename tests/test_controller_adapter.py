"""Tests for the controller adapter boundary.

These tests verify that the controller-adapter boundary consumes a validated
handoff request, returns a bounded adapter result, delegates decision
reconciliation to TASK-013, and fails closed on every unsupported or unsafe
condition without mutating task files, Git state, or lifecycle state.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner.controller_adapter import (
    AdapterResultState,
    ControllerAdapterInput,
    ControllerAdapterResult,
    FakeControllerAdapter,
    ManualControllerAdapter,
    dispatch_controller_adapter,
    format_adapter_result,
    get_controller_adapter,
    inspect_controller_adapter_status,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    build_controller_decision,
    default_decisions_dir,
    find_latest_decision,
    serialize_controller_decision,
    write_controller_decision,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoff,
    HandoffState,
    build_controller_handoff,
    default_handoff_dir,
    find_latest_handoff,
    load_controller_handoff,
    write_controller_handoff,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.lifecycle import ActorRole
from advancore.agent_runner.review_bundle import (
    ControllerAction,
    ReviewBundle,
    write_review_bundle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(
    *,
    task_id: str = "TASK-014",
    task_filename: str = "TASK-014-controller-adapter-boundary-foundation.md",
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
        changed_paths=["advancore/agent_runner/controller_adapter.py"],
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


def _prepare_handoff(
    repo_root: Path,
    *,
    bundle: ReviewBundle | None = None,
    state: str = HandoffState.WAITING_DECISION.value,
    decision_path: str | None = None,
    decision: str | None = None,
) -> tuple[Path, ReviewBundle, ControllerHandoff]:
    review_dir = repo_root / ".agent_runner" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    bundle = bundle or _make_bundle()
    bundle_path = write_review_bundle(bundle, review_dir)

    handoff = build_controller_handoff(
        bundle_path, bundle, repo_root=repo_root, git_info=_git_info(repo_root)
    )
    handoff.state = state
    handoff.decision_path = decision_path
    handoff.decision = decision
    handoff_path = write_controller_handoff(handoff, default_handoff_dir(repo_root))
    return bundle_path, bundle, handoff_path


def _load_last_record(audit_path: Path) -> dict:
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_manual_adapter_is_registered(self):
        adapter = get_controller_adapter("manual")
        assert adapter is not None
        assert adapter.name == "manual"

    def test_unknown_adapter_lookup_returns_none(self):
        assert get_controller_adapter("openai") is None


# ---------------------------------------------------------------------------
# Manual adapter behavior
# ---------------------------------------------------------------------------


class TestManualAdapter:
    def test_waiting_decision_returns_pending(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, bundle, _ = _prepare_handoff(repo_root)
        adapter = ManualControllerAdapter()
        result = adapter.dispatch(
            ControllerAdapterInput(
                request_path=request_path,
                handoff=build_controller_handoff(request_path, bundle),
                repo_root=repo_root,
            )
        )
        assert result.state == AdapterResultState.PENDING.value
        assert result.adapter_name == "manual"
        assert result.decision_path is None

    def test_manual_adapter_never_creates_approve(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, bundle, _ = _prepare_handoff(
            repo_root, bundle=_make_bundle(recommended_action=ControllerAction.REVIEW.value)
        )
        adapter = ManualControllerAdapter()
        result = adapter.dispatch(
            ControllerAdapterInput(
                request_path=request_path,
                handoff=build_controller_handoff(request_path, bundle),
                repo_root=repo_root,
            )
        )
        assert result.state != AdapterResultState.DECISION_RECEIVED.value
        assert "APPROVE" not in " ".join(result.messages)

    def test_blocked_handoff_returns_blocked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(
            repo_root, state=HandoffState.BLOCKED.value
        )
        handoff = load_controller_handoff(handoff_path)
        adapter = ManualControllerAdapter()
        result = adapter.dispatch(
            ControllerAdapterInput(
                request_path=handoff_path,
                handoff=handoff,
                repo_root=repo_root,
            )
        )
        assert result.state == AdapterResultState.BLOCKED.value

    def test_unsupported_handoff_state_returns_blocked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, bundle, _ = _prepare_handoff(repo_root)
        handoff = build_controller_handoff(request_path, bundle)
        handoff.state = "UNKNOWN_STATE"
        adapter = ManualControllerAdapter()
        result = adapter.dispatch(
            ControllerAdapterInput(
                request_path=request_path,
                handoff=handoff,
                repo_root=repo_root,
            )
        )
        assert result.state == AdapterResultState.BLOCKED.value

    def test_reconciled_handoff_returns_decision_received(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(
            repo_root,
            state=HandoffState.DECISION_RECEIVED.value,
            decision_path=".agent_runner/decisions/decision.json",
            decision="APPROVE",
        )
        handoff = load_controller_handoff(handoff_path)
        adapter = ManualControllerAdapter()
        result = adapter.dispatch(
            ControllerAdapterInput(
                request_path=handoff_path,
                handoff=handoff,
                repo_root=repo_root,
            )
        )
        assert result.state == AdapterResultState.DECISION_RECEIVED.value
        assert result.decision == "APPROVE"


# ---------------------------------------------------------------------------
# Bounded input policy
# ---------------------------------------------------------------------------


class TestBoundedInputPolicy:
    def test_adapter_input_excludes_full_content_fields(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, bundle, _ = _prepare_handoff(repo_root)
        bundle.messages = ["password=secret token=abc transcript: lots of output"]
        handoff = build_controller_handoff(request_path, bundle)
        adapter = ManualControllerAdapter()
        result = adapter.dispatch(
            ControllerAdapterInput(
                request_path=request_path,
                handoff=handoff,
                repo_root=repo_root,
            )
        )
        raw = json.dumps(result.__dict__, default=str).lower()
        assert "password" not in raw
        assert "token" not in raw
        assert "transcript" not in raw
        assert "stdout" not in raw
        assert "stderr" not in raw


# ---------------------------------------------------------------------------
# Orchestration dispatch
# ---------------------------------------------------------------------------


class TestDispatchOrchestration:
    def test_dispatch_waiting_decision_returns_pending(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.PENDING.value
        assert result.adapter_name == "manual"
        assert result.request_path == str(handoff_path)

    def test_missing_handoff_request_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        missing = repo_root / ".agent_runner" / "controller_handoff" / "missing.json"
        result = dispatch_controller_adapter(
            handoff_target=missing,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert "cannot load handoff request" in " ".join(result.messages).lower()

    def test_malformed_handoff_request_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        handoff_dir = default_handoff_dir(repo_root)
        handoff_dir.mkdir(parents=True)
        bad_path = handoff_dir / "bad.json"
        bad_path.write_text("not valid json", encoding="utf-8")
        result = dispatch_controller_adapter(
            handoff_target=bad_path,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert "cannot load handoff request" in " ".join(result.messages).lower()

    def test_unknown_adapter_name_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter="nonexistent",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert "unknown controller adapter" in " ".join(result.messages).lower()

    def test_fake_adapter_with_matching_decision_reconciles(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        # The fake adapter returns a relative decision path; the orchestrator
        # resolves it against repo_root and reconciles through TASK-013 logic.
        decision_path = write_controller_decision(decision, decisions_dir)
        rel_decision_path = str(decision_path.relative_to(repo_root))

        fake_result = ControllerAdapterResult(
            adapter_name="fake",
            state=AdapterResultState.DECISION_RECEIVED.value,
            decision_path=rel_decision_path,
            decision="APPROVE",
            messages=["Fake adapter found decision"],
        )
        fake_adapter = FakeControllerAdapter(result=fake_result)

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter=fake_adapter,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.DECISION_RECEIVED.value
        assert result.reconciled is True
        assert result.decision == "APPROVE"

    def test_fake_adapter_with_worker_decision_is_blocked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        # Tamper with the actor role to simulate a worker-authored decision.
        decision.actor_role = "worker"
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        fake_result = ControllerAdapterResult(
            adapter_name="fake",
            state=AdapterResultState.DECISION_RECEIVED.value,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )
        fake_adapter = FakeControllerAdapter(result=fake_result)

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter=fake_adapter,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert result.reconciled is False
        assert "worker cannot act" in " ".join(result.messages).lower()

    def test_fake_adapter_with_task_mismatched_decision_is_blocked(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        wrong_bundle = _make_bundle(task_id="TASK-999")
        decision = _make_decision(bundle_path, wrong_bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        fake_result = ControllerAdapterResult(
            adapter_name="fake",
            state=AdapterResultState.DECISION_RECEIVED.value,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )
        fake_adapter = FakeControllerAdapter(result=fake_result)

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter=fake_adapter,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert "task id mismatch" in " ".join(result.messages).lower()

    def test_fake_adapter_with_bundle_reference_mismatch_is_blocked(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        other_bundle_path = bundle_path.parent / "other.json"
        other_bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision = _make_decision(other_bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        fake_result = ControllerAdapterResult(
            adapter_name="fake",
            state=AdapterResultState.DECISION_RECEIVED.value,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )
        fake_adapter = FakeControllerAdapter(result=fake_result)

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter=fake_adapter,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert "review-bundle reference mismatch" in " ".join(result.messages).lower()

    def test_unknown_adapter_result_state_is_blocked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        fake_result = ControllerAdapterResult(
            adapter_name="fake",
            state="WEIRD",
            messages=["Bad state"],
        )
        fake_adapter = FakeControllerAdapter(result=fake_result)

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter=fake_adapter,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert "unknown adapter result state" in " ".join(result.messages).lower()

    def test_adapter_exception_is_blocked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        fake_adapter = FakeControllerAdapter(exception=RuntimeError("boom"))

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter=fake_adapter,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.BLOCKED.value
        assert "failed" in " ".join(result.messages).lower()

    def test_already_reconciled_handoff_is_idempotent(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        decision_path = write_controller_decision(decision, decisions_dir)
        rel_decision_path = str(decision_path.relative_to(repo_root))

        # Prepare the handoff as already reconciled to the matching decision.
        _, _, handoff_path = _prepare_handoff(
            repo_root,
            bundle=bundle,
            state=HandoffState.DECISION_RECEIVED.value,
            decision_path=rel_decision_path,
            decision="APPROVE",
        )

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.DECISION_RECEIVED.value
        assert result.reconciled is True
        assert "already reconciled" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# Absence of side effects
# ---------------------------------------------------------------------------


class TestDispatchSideEffects:
    def test_dispatch_does_not_mutate_task_lifecycle(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        task_path = tasks_dir / "TASK-014-controller-adapter-boundary-foundation.md"
        original_text = "# TASK-014 — Adapter\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path.write_text(original_text, encoding="utf-8")

        request_path, _, handoff_path = _prepare_handoff(repo_root)

        dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert task_path.read_text(encoding="utf-8") == original_text

    def test_dispatch_does_not_mutate_git_publication_state(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        with patch("advancore.agent_runner.git_info.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            main(["controller-adapter", "dispatch", str(handoff_path)])

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "checkout" not in args
            assert "reset" not in args
            assert "remote" not in args


# ---------------------------------------------------------------------------
# Read-only status/inspection
# ---------------------------------------------------------------------------


class TestReadOnlyStatus:
    def test_status_waiting_decision_returns_pending(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        result = inspect_controller_adapter_status(
            handoff_target=handoff_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.PENDING.value
        assert result.adapter_name == "manual"
        assert result.audit_path is None

    def test_status_does_not_mutate_artifact(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        original_text = handoff_path.read_text(encoding="utf-8")

        inspect_controller_adapter_status(
            handoff_target=handoff_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert handoff_path.read_text(encoding="utf-8") == original_text

    def test_status_reconciled_handoff_returns_decision_received(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(
            repo_root,
            state=HandoffState.DECISION_RECEIVED.value,
            decision_path=".agent_runner/decisions/decision.json",
            decision="APPROVE",
        )
        result = inspect_controller_adapter_status(
            handoff_target=handoff_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.state == AdapterResultState.DECISION_RECEIVED.value
        assert result.decision == "APPROVE"


# ---------------------------------------------------------------------------
# Audit behavior
# ---------------------------------------------------------------------------


class TestAdapterAudit:
    def test_dispatch_writes_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        audit_path = repo_root / ".agent_runner" / "audit" / "runner.jsonl"
        assert audit_path.exists()
        record = _load_last_record(audit_path)
        assert record["mode"] == "controller_adapter"
        assert record["adapter_name"] == "manual"
        assert record["state"] == AdapterResultState.PENDING.value
        assert record["task_id"] == "TASK-014"

    def test_dispatch_with_decision_writes_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision_path = write_controller_decision(
            decision, default_decisions_dir(repo_root)
        )

        # Reconcile the handoff so its state becomes DECISION_RECEIVED.
        from advancore.agent_runner.controller_handoff import reconcile_controller_handoff
        reconcile_controller_handoff(
            request_path=handoff_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )

        audit_path = repo_root / ".agent_runner" / "audit" / "runner.jsonl"
        record = _load_last_record(audit_path)
        assert record["state"] == AdapterResultState.DECISION_RECEIVED.value
        assert record["reconciled"] is True

    def test_audit_write_failure_is_reported(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)

        def boom(*args, **kwargs):
            from advancore.agent_runner.audit import AuditWriteError
            raise AuditWriteError("disk full")

        monkeypatch.setattr(
            "advancore.agent_runner.controller_adapter.write_audit_record", boom
        )

        result = dispatch_controller_adapter(
            handoff_target=handoff_path,
            adapter="manual",
            repo_root=repo_root,
            git_info=_git_info(repo_root),
        )
        assert result.audit_write_ok is False
        assert result.audit_write_error is not None
        assert "disk full" in result.audit_write_error


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestFormatting:
    def test_format_adapter_result_is_human_readable(self):
        result = ControllerAdapterResult(
            adapter_name="manual",
            state=AdapterResultState.PENDING.value,
            task_id="TASK-014",
            request_path=".agent_runner/controller_handoff/request.json",
            bundle_path=".agent_runner/review/bundle.json",
            messages=["Waiting for decision"],
        )
        text = format_adapter_result(result)
        assert "Controller Adapter Result" in text
        assert "manual" in text
        assert "PENDING" in text
        assert "TASK-014" in text


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestControllerAdapterCLI:
    def test_cli_dispatch_manual_returns_pending(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-adapter", "dispatch", str(handoff_path)])
        assert code == 0

    def test_cli_dispatch_unknown_adapter_returns_nonzero(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(
            ["controller-adapter", "dispatch", str(handoff_path), "--adapter", "openai"]
        )
        assert code != 0

    def test_cli_status_is_read_only(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)
        original_text = handoff_path.read_text(encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-adapter", "status", str(handoff_path)])
        assert code == 0
        assert handoff_path.read_text(encoding="utf-8") == original_text

    def test_cli_dispatch_latest_uses_latest_handoff(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        request_path, _, handoff_path = _prepare_handoff(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-adapter", "dispatch", "latest"])
        assert code == 0
