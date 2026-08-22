"""Tests for the controller transport envelope.

These tests verify that the transport envelope defines a versioned,
transport-neutral request/response contract around the existing TASK-014
controller-adapter boundary, that serialization and validation are
deterministic and fail-closed, and that response conversion delegates decision
validation/reconciliation to existing TASK-011/TASK-013/TASK-014 logic rather
than duplicating it.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner.audit import build_controller_transport_audit_payload
from advancore.agent_runner.controller_adapter import (
    AdapterResultState,
    ControllerAdapterResult,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecision,
    build_controller_decision,
    default_decisions_dir,
    find_latest_decision,
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
from advancore.agent_runner.controller_transport import (
    TRANSPORT_ENVELOPE_VERSION,
    TRANSPORT_REQUEST_SCHEMA,
    TRANSPORT_RESPONSE_SCHEMA,
    ControllerTransportError,
    ControllerTransportRequest,
    ControllerTransportResponse,
    ControllerTransportValidationError,
    ControllerTransportWriteError,
    apply_transport_response,
    build_transport_request,
    build_transport_response,
    convert_response_to_adapter_result,
    default_transport_dir,
    find_latest_transport_request,
    find_latest_transport_response,
    format_transport_request_summary,
    format_transport_response_summary,
    handoff_to_transport_request,
    load_transport_request,
    load_transport_response,
    validate_transport_request,
    validate_transport_response,
    write_transport_request,
    write_transport_response,
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
    task_id: str = "TASK-015",
    task_filename: str = "TASK-015-controller-transport-envelope-foundation.md",
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
        changed_paths=["advancore/agent_runner/controller_transport.py"],
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
) -> tuple[Path, ReviewBundle, Path]:
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
# Request envelope construction
# ---------------------------------------------------------------------------


class TestTransportRequestConstruction:
    def test_valid_handoff_creates_bounded_request_envelope(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        handoff = load_controller_handoff(handoff_path)

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=handoff,
            adapter_name="manual",
            repo_root=repo_root,
        )

        assert request.envelope_version == TRANSPORT_ENVELOPE_VERSION
        assert request.schema == TRANSPORT_REQUEST_SCHEMA
        assert request.task_id == "TASK-015"
        assert request.task_filename == "TASK-015-controller-transport-envelope-foundation.md"
        assert request.handoff_request_path == str(
            handoff_path.relative_to(repo_root)
        )
        assert request.handoff_request_id == handoff.request_id
        assert request.review_bundle_path == str(bundle_path.relative_to(repo_root))
        assert request.adapter_name == "manual"
        assert request.handoff_state == HandoffState.WAITING_DECISION.value

    def test_handoff_to_transport_request_alias(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        handoff = load_controller_handoff(handoff_path)

        request = handoff_to_transport_request(
            handoff_path=handoff_path,
            handoff=handoff,
            adapter_name="manual",
            adapter_type="local",
            repo_root=repo_root,
        )

        assert request.adapter_type == "local"
        assert request.handoff_request_id == handoff.request_id

    def test_request_excludes_full_content_and_secret_fields(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        handoff = load_controller_handoff(handoff_path)
        bundle.messages = ["password=secret token=abc transcript: lots of output"]

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=handoff,
            adapter_name="manual",
            repo_root=repo_root,
        )

        raw = json.dumps(serialize_dataclass(request), default=str).lower()
        assert "password" not in raw
        assert "token" not in raw
        assert "transcript" not in raw
        assert "stdout" not in raw
        assert "stderr" not in raw
        assert "secret" not in raw

    def test_missing_handoff_task_id_is_rejected(self, tmp_path: Path):
        handoff = ControllerHandoff(
            request_version="1",
            request_id="CHR-test",
            timestamp="2026-08-21T00:00:00+00:00",
            task_id="",
            task_filename="TASK-015.md",
            bundle_path=".agent_runner/review/bundle.json",
            bundle_branch="agent-control-foundation",
            bundle_pre_head="pre",
            bundle_post_head=None,
            bundle_recommended_action=ControllerAction.REVIEW.value,
            state=HandoffState.WAITING_DECISION.value,
        )

        with pytest.raises(ControllerTransportError, match="missing required transport field: task_id"):
            build_transport_request(
                tmp_path / "handoff.json", handoff, adapter_name="manual"
            )

    def test_unsupported_handoff_state_is_rejected(self, tmp_path: Path):
        handoff = ControllerHandoff(
            request_version="1",
            request_id="CHR-test",
            timestamp="2026-08-21T00:00:00+00:00",
            task_id="TASK-015",
            task_filename="TASK-015.md",
            bundle_path=".agent_runner/review/bundle.json",
            bundle_branch="agent-control-foundation",
            bundle_pre_head="pre",
            bundle_post_head=None,
            bundle_recommended_action=ControllerAction.REVIEW.value,
            state="WEIRD",
        )

        with pytest.raises(ControllerTransportError, match="Unsupported handoff state"):
            build_transport_request(
                tmp_path / "handoff.json", handoff, adapter_name="manual"
            )


# ---------------------------------------------------------------------------
# Request serialization / persistence
# ---------------------------------------------------------------------------


class TestTransportRequestSerialization:
    def test_write_and_load_roundtrip(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        handoff = load_controller_handoff(handoff_path)
        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=handoff,
            adapter_name="manual",
            repo_root=repo_root,
        )
        transport_dir = default_transport_dir(repo_root)

        path = write_transport_request(request, transport_dir)

        assert path.exists()
        loaded = load_transport_request(path)
        assert loaded.request_id == request.request_id
        assert loaded.task_id == request.task_id
        assert loaded.handoff_request_path == request.handoff_request_path
        assert loaded.review_bundle_path == request.review_bundle_path
        assert loaded.handoff_state == request.handoff_state

    def test_find_latest_request(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        transport_dir = default_transport_dir(repo_root)
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        handoff = load_controller_handoff(handoff_path)
        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=handoff,
            adapter_name="manual",
            repo_root=repo_root,
        )
        path1 = write_transport_request(request, transport_dir)
        path2 = write_transport_request(request, transport_dir)

        latest = find_latest_transport_request(transport_dir)
        assert latest == path2

    def test_load_invalid_request_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        with pytest.raises(ControllerTransportError):
            load_transport_request(path)

    def test_write_failure_is_reported(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        handoff = load_controller_handoff(handoff_path)
        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=handoff,
            adapter_name="manual",
            repo_root=repo_root,
        )
        transport_dir = default_transport_dir(repo_root)

        with patch("advancore.agent_runner.controller_transport.Path.write_text") as mock_write:
            mock_write.side_effect = OSError("disk full")
            with pytest.raises(ControllerTransportWriteError, match="disk full"):
                write_transport_request(request, transport_dir)


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


class TestTransportRequestValidation:
    def test_unknown_envelope_version_is_rejected(self):
        data = _valid_request_dict()
        data["envelope_version"] = "999"

        with pytest.raises(ControllerTransportValidationError, match="Unknown transport envelope version"):
            validate_transport_request(data)

    def test_unknown_schema_is_rejected(self):
        data = _valid_request_dict()
        data["schema"] = "evil.schema"

        with pytest.raises(ControllerTransportValidationError, match="Unknown transport envelope schema"):
            validate_transport_request(data)

    def test_missing_required_field_is_rejected(self):
        data = _valid_request_dict()
        del data["task_id"]

        with pytest.raises(ControllerTransportValidationError, match="missing required fields"):
            validate_transport_request(data)

    def test_unknown_handoff_state_is_rejected(self):
        data = _valid_request_dict()
        data["handoff_state"] = "APPROVED"

        with pytest.raises(ControllerTransportValidationError, match="Unknown handoff state"):
            validate_transport_request(data)

    def test_correlation_id_mismatch_is_rejected(self):
        data = _valid_request_dict()
        data["request_id"] = "CTE-mismatch"

        with pytest.raises(ControllerTransportValidationError, match="ID mismatch"):
            validate_transport_request(data, expected_request_id="CTE-expected")


# ---------------------------------------------------------------------------
# Response envelope construction and serialization
# ---------------------------------------------------------------------------


class TestTransportResponseConstruction:
    def test_build_response_from_request(self, tmp_path: Path):
        request = _valid_request()
        response = build_transport_response(
            request,
            AdapterResultState.PENDING,
            messages=["Waiting for controller"],
        )

        assert response.envelope_version == TRANSPORT_ENVELOPE_VERSION
        assert response.schema == TRANSPORT_RESPONSE_SCHEMA
        assert response.request_id == request.request_id
        assert response.task_id == request.task_id
        assert response.handoff_request_path == request.handoff_request_path
        assert response.review_bundle_path == request.review_bundle_path
        assert response.result_state == AdapterResultState.PENDING.value
        assert response.decision_path is None

    def test_decision_received_response_includes_decision_reference(self, tmp_path: Path):
        request = _valid_request()
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=".agent_runner/decisions/decision.json",
            decision="APPROVE",
        )

        assert response.result_state == AdapterResultState.DECISION_RECEIVED.value
        assert response.decision_path == ".agent_runner/decisions/decision.json"
        assert response.decision == "APPROVE"

    def test_unknown_response_state_is_rejected(self, tmp_path: Path):
        request = _valid_request()

        with pytest.raises(ControllerTransportError, match="Unknown transport response state"):
            build_transport_response(request, "WEIRD")


class TestTransportResponseSerialization:
    def test_write_and_load_roundtrip(self, tmp_path: Path):
        request = _valid_request()
        response = build_transport_response(
            request,
            AdapterResultState.PENDING,
        )
        transport_dir = default_transport_dir(tmp_path)

        path = write_transport_response(response, transport_dir)
        loaded = load_transport_response(path)

        assert loaded.request_id == response.request_id
        assert loaded.result_state == response.result_state
        assert loaded.handoff_request_path == response.handoff_request_path

    def test_find_latest_response(self, tmp_path: Path):
        request = _valid_request()
        response = build_transport_response(request, AdapterResultState.PENDING)
        transport_dir = default_transport_dir(tmp_path)
        path1 = write_transport_response(response, transport_dir)
        path2 = write_transport_response(response, transport_dir)

        latest = find_latest_transport_response(transport_dir)
        assert latest == path2

    def test_load_invalid_response_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        with pytest.raises(ControllerTransportError):
            load_transport_response(path)


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------


class TestTransportResponseValidation:
    def test_unknown_envelope_version_is_rejected(self):
        data = _valid_response_dict()
        data["envelope_version"] = "999"

        with pytest.raises(ControllerTransportValidationError, match="Unknown transport envelope version"):
            validate_transport_response(data)

    def test_unknown_schema_is_rejected(self):
        data = _valid_response_dict()
        data["schema"] = "evil.schema"

        with pytest.raises(ControllerTransportValidationError, match="Unknown transport envelope schema"):
            validate_transport_response(data)

    def test_unknown_response_state_is_rejected(self):
        data = _valid_response_dict()
        data["result_state"] = "WEIRD"

        with pytest.raises(ControllerTransportValidationError, match="Unknown transport response state"):
            validate_transport_response(data)

    def test_missing_required_field_is_rejected(self):
        data = _valid_response_dict()
        del data["result_state"]

        with pytest.raises(ControllerTransportValidationError, match="missing required fields"):
            validate_transport_response(data)

    def test_correlation_id_mismatch_is_rejected(self):
        data = _valid_response_dict()
        data["request_id"] = "CTE-mismatch"

        with pytest.raises(ControllerTransportValidationError, match="request ID mismatch"):
            validate_transport_response(data, expected_request_id="CTE-expected")

    def test_task_id_mismatch_is_rejected(self):
        data = _valid_response_dict()
        data["task_id"] = "TASK-999"

        with pytest.raises(ControllerTransportValidationError, match="task ID mismatch"):
            validate_transport_response(data, expected_task_id="TASK-015")

    def test_handoff_path_mismatch_is_rejected(self):
        data = _valid_response_dict()
        data["handoff_request_path"] = ".agent_runner/controller_handoff/other.json"

        with pytest.raises(ControllerTransportValidationError, match="handoff path mismatch"):
            validate_transport_response(
                data, expected_handoff_path=".agent_runner/controller_handoff/expected.json"
            )

    def test_bundle_path_mismatch_is_rejected(self):
        data = _valid_response_dict()
        data["review_bundle_path"] = ".agent_runner/review/other.json"

        with pytest.raises(ControllerTransportValidationError, match="bundle path mismatch"):
            validate_transport_response(
                data, expected_bundle_path=".agent_runner/review/expected.json"
            )


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


class TestTransportPathSafety:
    def test_traversal_in_handoff_path_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        request = _valid_request()
        request.handoff_request_path = "../outside.json"
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=".agent_runner/decisions/decision.json",
        )

        result = apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        assert result.state == AdapterResultState.BLOCKED.value
        assert "escapes repository root" in " ".join(result.messages).lower()

    def test_traversal_in_decision_path_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        request = _valid_request()
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path="../outside/decision.json",
        )

        result = apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        assert result.state == AdapterResultState.BLOCKED.value
        assert "escapes repository root" in " ".join(result.messages).lower()

    def test_request_id_with_traversal_is_sanitized(self, tmp_path: Path):
        request = _valid_request()
        request.request_id = "../etc/passwd"
        request.timestamp = "2026-08-21T00:00:00+00:00"
        transport_dir = default_transport_dir(tmp_path)

        path = write_transport_request(request, transport_dir)

        assert path.exists()
        assert ".." not in path.name
        assert "/" not in path.name
        assert "\\" not in path.name
        loaded = load_transport_request(path)
        assert loaded.request_id == "../etc/passwd"  # original value preserved


# ---------------------------------------------------------------------------
# Response conversion and authority separation
# ---------------------------------------------------------------------------


class TestTransportResponseConversion:
    def test_pending_response_creates_no_decision_authority(self, tmp_path: Path):
        request = _valid_request()
        response = build_transport_response(request, AdapterResultState.PENDING)

        result = convert_response_to_adapter_result(response)

        assert result.state == AdapterResultState.PENDING.value
        assert result.decision_path is None
        assert result.decision is None
        assert result.reconciled is False

    def test_blocked_response_creates_no_decision_authority(self, tmp_path: Path):
        request = _valid_request()
        response = build_transport_response(request, AdapterResultState.BLOCKED)

        result = convert_response_to_adapter_result(response)

        assert result.state == AdapterResultState.BLOCKED.value
        assert result.decision_path is None
        assert result.decision is None

    def test_decision_received_without_record_is_blocked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=".agent_runner/decisions/missing.json",
            decision="APPROVE",
        )

        result = apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        assert result.state == AdapterResultState.BLOCKED.value
        assert result.reconciled is False

    def test_valid_matching_decision_reconciles(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )

        result = apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        assert result.state == AdapterResultState.DECISION_RECEIVED.value
        assert result.reconciled is True
        assert result.decision == "APPROVE"

    def test_worker_authored_decision_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision.actor_role = "worker"
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )

        result = apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        assert result.state == AdapterResultState.BLOCKED.value
        assert result.reconciled is False
        assert "worker cannot act" in " ".join(result.messages).lower()

    def test_decision_with_mismatched_task_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        wrong_bundle = _make_bundle(task_id="TASK-999")
        decision = build_controller_decision(
            bundle_path,
            wrong_bundle,
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
            repo_root=repo_root,
        )
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )

        result = apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        assert result.state == AdapterResultState.BLOCKED.value
        assert "task id mismatch" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# Absence of side effects
# ---------------------------------------------------------------------------


class TestTransportSideEffects:
    def test_request_generation_does_not_mutate_task_lifecycle(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        task_path = tasks_dir / "TASK-015-controller-transport-envelope-foundation.md"
        original_text = "# TASK-015 — Envelope\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path.write_text(original_text, encoding="utf-8")

        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        handoff = load_controller_handoff(handoff_path)
        build_transport_request(
            handoff_path=handoff_path,
            handoff=handoff,
            adapter_name="manual",
            repo_root=repo_root,
        )

        assert task_path.read_text(encoding="utf-8") == original_text

    def test_request_generation_does_not_mutate_git_publication_state(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        with patch("advancore.agent_runner.git_info.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            main(["controller-transport", "request", str(handoff_path)])

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "checkout" not in args
            assert "reset" not in args
            assert "remote" not in args

    def test_read_only_show_does_not_mutate_artifact(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        transport_dir = default_transport_dir(repo_root)
        envelope_path = write_transport_request(request, transport_dir)
        original_text = envelope_path.read_text(encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "show", str(envelope_path)])

        assert code == 0
        assert envelope_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Audit behavior
# ---------------------------------------------------------------------------


class TestTransportAudit:
    def test_request_writes_audit_record(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "request", str(handoff_path)])
        assert code == 0

        audit_path = repo_root / ".agent_runner" / "audit" / "runner.jsonl"
        assert audit_path.exists()
        record = _load_last_record(audit_path)
        assert record["mode"] == "controller_transport"
        assert record["task_id"] == "TASK-015"
        assert record["request_id"].startswith("CTE-")

    def test_response_application_writes_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision_path = write_controller_decision(
            decision, default_decisions_dir(repo_root)
        )

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )

        apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        audit_path = repo_root / ".agent_runner" / "audit" / "runner.jsonl"
        record = _load_last_record(audit_path)
        assert record["mode"] == "controller_transport"
        assert record["state"] == AdapterResultState.DECISION_RECEIVED.value
        assert record["reconciled"] is True

    def test_audit_write_failure_is_reported(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(request, AdapterResultState.PENDING)

        def boom(*args, **kwargs):
            from advancore.agent_runner.audit import AuditWriteError
            raise AuditWriteError("disk full")

        monkeypatch.setattr(
            "advancore.agent_runner.controller_transport.write_audit_record", boom
        )

        result = apply_transport_response(
            response, repo_root=repo_root, git_info=_git_info(repo_root)
        )

        assert result.audit_write_ok is False
        assert result.audit_write_error is not None
        assert "disk full" in result.audit_write_error

    def test_audit_payload_shape(self):
        payload = build_controller_transport_audit_payload(
            task_id="TASK-015",
            task_filename="TASK-015.md",
            request_id="CTE-abc",
            state=AdapterResultState.DECISION_RECEIVED.value,
            request_path=".agent_runner/controller_handoff/request.json",
            bundle_path=".agent_runner/review/bundle.json",
            decision_path=".agent_runner/decisions/decision.json",
            decision="APPROVE",
            reconciled=True,
            branch="agent-control-foundation",
            head_sha="abc",
        )
        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "mode",
            "request_id",
            "state",
            "request_path",
            "bundle_path",
            "decision_path",
            "decision",
            "reconciled",
            "branch",
            "head_sha",
        }
        assert set(payload.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestTransportFormatting:
    def test_format_request_summary_is_human_readable(self, tmp_path: Path):
        request = _valid_request()
        text = format_transport_request_summary(request)
        assert "Controller Transport Request Envelope" in text
        assert request.request_id in text
        assert request.adapter_name in text

    def test_format_response_summary_is_human_readable(self, tmp_path: Path):
        request = _valid_request()
        response = build_transport_response(
            request, AdapterResultState.DECISION_RECEIVED, decision="APPROVE"
        )
        text = format_transport_response_summary(response)
        assert "Controller Transport Response Envelope" in text
        assert response.request_id in text
        assert "APPROVE" in text


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestTransportCLI:
    def test_cli_request_creates_envelope(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "request", str(handoff_path)])
        assert code == 0

        transport_dir = default_transport_dir(repo_root)
        assert any(transport_dir.glob("*_request.json"))

    def test_cli_show_request_is_read_only(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        envelope_path = write_transport_request(
            request, default_transport_dir(repo_root)
        )
        original_text = envelope_path.read_text(encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "show", str(envelope_path)])
        assert code == 0
        assert envelope_path.read_text(encoding="utf-8") == original_text

    def test_cli_validate_response_reconciles_matching_decision(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision_path = write_controller_decision(
            decision, default_decisions_dir(repo_root)
        )

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )
        response_path = write_transport_response(
            response, default_transport_dir(repo_root)
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "validate-response", str(response_path)])
        assert code == 0

    def test_cli_validate_response_worker_decision_returns_nonzero(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = _make_decision(bundle_path, bundle, repo_root=repo_root)
        decision.actor_role = "worker"
        decision_path = write_controller_decision(
            decision, default_decisions_dir(repo_root)
        )

        request = build_transport_request(
            handoff_path=handoff_path,
            handoff=load_controller_handoff(handoff_path),
            adapter_name="manual",
            repo_root=repo_root,
        )
        response = build_transport_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )
        response_path = write_transport_response(
            response, default_transport_dir(repo_root)
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "validate-response", str(response_path)])
        assert code != 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _valid_request() -> ControllerTransportRequest:
    return ControllerTransportRequest(
        envelope_version=TRANSPORT_ENVELOPE_VERSION,
        schema=TRANSPORT_REQUEST_SCHEMA,
        request_id="CTE-test123",
        timestamp="2026-08-21T00:00:00+00:00",
        task_id="TASK-015",
        task_filename="TASK-015-controller-transport-envelope-foundation.md",
        handoff_request_path=".agent_runner/controller_handoff/request.json",
        handoff_request_id="CHR-handoff123",
        review_bundle_path=".agent_runner/review/bundle.json",
        adapter_name="manual",
        adapter_type=None,
        bundle_branch="agent-control-foundation",
        bundle_pre_head="pre",
        bundle_post_head="post",
        bundle_recommended_action=ControllerAction.REVIEW.value,
        handoff_state=HandoffState.WAITING_DECISION.value,
    )


def _valid_request_dict() -> dict[str, object]:
    return {
        "envelope_version": TRANSPORT_ENVELOPE_VERSION,
        "schema": TRANSPORT_REQUEST_SCHEMA,
        "request_id": "CTE-test123",
        "timestamp": "2026-08-21T00:00:00+00:00",
        "task_id": "TASK-015",
        "task_filename": "TASK-015-controller-transport-envelope-foundation.md",
        "handoff_request_path": ".agent_runner/controller_handoff/request.json",
        "handoff_request_id": "CHR-handoff123",
        "review_bundle_path": ".agent_runner/review/bundle.json",
        "adapter_name": "manual",
        "adapter_type": None,
        "bundle_branch": "agent-control-foundation",
        "bundle_pre_head": "pre",
        "bundle_post_head": "post",
        "bundle_recommended_action": ControllerAction.REVIEW.value,
        "handoff_state": HandoffState.WAITING_DECISION.value,
        "messages": [],
    }


def _valid_response_dict() -> dict[str, object]:
    return {
        "envelope_version": TRANSPORT_ENVELOPE_VERSION,
        "schema": TRANSPORT_RESPONSE_SCHEMA,
        "request_id": "CTE-test123",
        "timestamp": "2026-08-21T00:00:00+00:00",
        "task_id": "TASK-015",
        "task_filename": "TASK-015-controller-transport-envelope-foundation.md",
        "handoff_request_path": ".agent_runner/controller_handoff/request.json",
        "review_bundle_path": ".agent_runner/review/bundle.json",
        "result_state": AdapterResultState.PENDING.value,
        "decision_path": None,
        "decision": None,
        "messages": [],
    }


def serialize_dataclass(obj) -> dict:
    """Return a JSON-serializable dict from a dataclass instance."""
    return asdict(obj) if hasattr(obj, "__dataclass_fields__") else obj
