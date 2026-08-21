"""Tests for the controller transport-driver boundary.

These tests verify that the transport driver is a replaceable delivery layer
around the TASK-015 envelope contract, that the local filesystem driver is
bounded and fail-closed, and that the driver never assumes controller
authority or mutates lifecycle/Git/database state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner.controller_adapter import AdapterResultState
from advancore.agent_runner.controller_decision import (
    build_controller_decision,
    default_decisions_dir,
    write_controller_decision,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoff,
    HandoffState,
    build_controller_handoff,
    default_handoff_dir,
    load_controller_handoff,
    write_controller_handoff,
)
from advancore.agent_runner.controller_transport import (
    TRANSPORT_ENVELOPE_VERSION,
    TRANSPORT_REQUEST_SCHEMA,
    TRANSPORT_RESPONSE_SCHEMA,
    ControllerTransportRequest,
    ControllerTransportResponse,
    build_transport_request,
    build_transport_response,
    default_transport_dir,
    serialize_transport_request,
    serialize_transport_response,
    write_transport_request,
    write_transport_response,
)
from advancore.agent_runner.controller_transport_driver import (
    ControllerTransportDriverAmbiguousError,
    ControllerTransportDriverConflictError,
    ControllerTransportDriverError,
    ControllerTransportDriverNotFoundError,
    LocalFilesystemTransportDriver,
    default_driver_dirs,
    format_driver_view_summary,
    load_driver_request_by_id,
    write_driver_response,
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
    task_id: str = "TASK-016",
    task_filename: str = "TASK-016-controller-transport-driver-boundary-foundation.md",
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
        changed_paths=["advancore/agent_runner/controller_transport_driver.py"],
        diff_summary={"total": 1, "counts": {"modified": 1}},
        audit_path=".agent_runner/audit/runner.jsonl",
        recommended_action=recommended_action,
        messages=["Worker completed."],
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


def _build_request(repo_root: Path) -> tuple[ControllerTransportRequest, Path]:
    bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
    handoff = load_controller_handoff(handoff_path)
    request = build_transport_request(
        handoff_path=handoff_path,
        handoff=handoff,
        adapter_name="manual",
        adapter_type="local",
        repo_root=repo_root,
    )
    return request, handoff_path


def _build_response(
    request: ControllerTransportRequest,
    state: AdapterResultState = AdapterResultState.PENDING,
    *,
    decision_path: str | None = None,
    decision: str | None = None,
) -> ControllerTransportResponse:
    return build_transport_response(
        request,
        state,
        decision_path=decision_path,
        decision=decision,
    )


def _write_response(
    response: ControllerTransportResponse,
    inbox_dir: Path,
) -> Path:
    return write_driver_response(response, inbox_dir)


# ---------------------------------------------------------------------------
# Driver interface and local filesystem send
# ---------------------------------------------------------------------------


class TestLocalFilesystemDriverSend:
    def test_valid_request_send_succeeds(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)

        path = driver.send(request)

        assert path.exists()
        assert path.name.endswith("_request.json")
        assert "outbox" in str(path)

    def test_written_request_loads_back_identical(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)

        path = driver.send(request)
        loaded = load_driver_request_by_id(request.request_id, driver.outbox_dir)

        assert serialize_transport_request(loaded) == serialize_transport_request(
            request
        )

    def test_identical_resend_is_idempotent(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)

        path1 = driver.send(request)
        path2 = driver.send(request)

        assert path1 == path2
        assert len(list(driver.outbox_dir.glob("*_request.json"))) == 1

    def test_divergent_request_with_same_id_is_blocked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        request2 = build_transport_request(
            handoff_path=Path(".agent_runner/controller_handoff/other.json"),
            handoff=ControllerHandoff(
                request_version="1",
                request_id="CHR-other",
                timestamp="2026-08-21T00:00:00+00:00",
                task_id=request.task_id,
                task_filename=request.task_filename,
                bundle_path=".agent_runner/review/other.json",
                bundle_branch="agent-control-foundation",
                bundle_pre_head="pre2",
                bundle_post_head=None,
                bundle_recommended_action=ControllerAction.REVIEW.value,
                state=HandoffState.WAITING_DECISION.value,
            ),
            adapter_name="manual",
            repo_root=repo_root,
        )
        request2.request_id = request.request_id

        with pytest.raises(ControllerTransportDriverConflictError):
            driver.send(request2)

    def test_invalid_request_is_rejected_on_send(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        request.schema = "evil.schema"  # Invalid: unknown schema

        driver = LocalFilesystemTransportDriver(repo_root)
        with pytest.raises(ControllerTransportDriverError):
            driver.send(request)


# ---------------------------------------------------------------------------
# Driver receive
# ---------------------------------------------------------------------------


class TestLocalFilesystemDriverReceive:
    def test_valid_matching_response_received(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request, AdapterResultState.PENDING)
        _write_response(response, driver.inbox_dir)

        received = driver.receive(request)
        assert received.request_id == request.request_id
        assert received.result_state == AdapterResultState.PENDING.value

    def test_missing_response_raises_not_found(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        with pytest.raises(ControllerTransportDriverNotFoundError):
            driver.receive(request)

    def test_malformed_response_json_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        response_path = (
            driver.inbox_dir
            / f"20260821T000000_TASK-016_{request.request_id}_response.json"
        )
        response_path.write_text("not json", encoding="utf-8")

        with pytest.raises(ControllerTransportDriverError):
            driver.receive(request)

    def test_unknown_response_schema_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        response_path = (
            driver.inbox_dir
            / f"20260821T000000_TASK-016_{request.request_id}_response.json"
        )
        data = serialize_transport_response(_build_response(request))
        data["schema"] = "evil.schema"
        response_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

        with pytest.raises(ControllerTransportDriverError):
            driver.receive(request)

    def test_unknown_response_state_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request)
        data = serialize_transport_response(response)
        data["result_state"] = "WEIRD"
        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        response_path = (
            driver.inbox_dir
            / f"20260821T000000_TASK-016_{request.request_id}_response.json"
        )
        response_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

        with pytest.raises(ControllerTransportDriverError):
            driver.receive(request)

    def test_correlation_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request)
        data = serialize_transport_response(response)
        data["request_id"] = "CTE-other"
        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        response_path = (
            driver.inbox_dir
            / f"20260821T000000_TASK-016_{request.request_id}_response.json"
        )
        response_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

        with pytest.raises(ControllerTransportDriverError):
            driver.receive(request)

    def test_task_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request)
        data = serialize_transport_response(response)
        data["task_id"] = "TASK-999"
        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        response_path = (
            driver.inbox_dir
            / f"20260821T000000_TASK-016_{request.request_id}_response.json"
        )
        response_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

        with pytest.raises(ControllerTransportDriverError):
            driver.receive(request)

    def test_handoff_path_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request)
        data = serialize_transport_response(response)
        data["handoff_request_path"] = ".agent_runner/controller_handoff/other.json"
        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        response_path = (
            driver.inbox_dir
            / f"20260821T000000_TASK-016_{request.request_id}_response.json"
        )
        response_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

        with pytest.raises(ControllerTransportDriverError):
            driver.receive(request)

    def test_bundle_path_mismatch_is_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request)
        data = serialize_transport_response(response)
        data["review_bundle_path"] = ".agent_runner/review/other.json"
        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        response_path = (
            driver.inbox_dir
            / f"20260821T000000_TASK-016_{request.request_id}_response.json"
        )
        response_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

        with pytest.raises(ControllerTransportDriverError):
            driver.receive(request)

    def test_ambiguous_multiple_responses_rejected(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request, AdapterResultState.PENDING)
        _write_response(response, driver.inbox_dir)
        # Manually create a second response file for the same request id.
        driver.inbox_dir.mkdir(parents=True, exist_ok=True)
        second_path = (
            driver.inbox_dir
            / f"20260821T000001_TASK-016_{request.request_id}_response.json"
        )
        second_path.write_text(
            json.dumps(serialize_transport_response(response), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        with pytest.raises(ControllerTransportDriverAmbiguousError):
            driver.receive(request)


# ---------------------------------------------------------------------------
# Authority separation
# ---------------------------------------------------------------------------


class TestDriverAuthoritySeparation:
    def test_pending_response_creates_no_decision_authority(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request, AdapterResultState.PENDING)
        _write_response(response, driver.inbox_dir)

        received = driver.receive(request)
        assert received.result_state == AdapterResultState.PENDING.value
        assert received.decision_path is None
        assert received.decision is None

    def test_blocked_response_creates_no_decision_authority(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(request, AdapterResultState.BLOCKED)
        _write_response(response, driver.inbox_dir)

        received = driver.receive(request)
        assert received.result_state == AdapterResultState.BLOCKED.value
        assert received.decision_path is None
        assert received.decision is None

    def test_decision_received_alone_does_not_authorize_lifecycle_mutation(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        task_path = tasks_dir / "TASK-016-controller-transport-driver-boundary-foundation.md"
        original_text = "# TASK-016 — Driver\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path.write_text(original_text, encoding="utf-8")

        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        response = _build_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=".agent_runner/decisions/missing.json",
            decision="APPROVE",
        )
        _write_response(response, driver.inbox_dir)

        received = driver.receive(request)
        assert received.result_state == AdapterResultState.DECISION_RECEIVED.value
        assert received.decision == "APPROVE"
        # Task file must remain untouched by driver receive.
        assert task_path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


class TestDriverPathSafety:
    def test_driver_paths_stay_under_bounded_directory(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)

        path = driver.send(request)
        assert ".." not in str(path.relative_to(driver.outbox_dir))
        assert driver.outbox_dir.resolve() in path.resolve().parents

    def test_path_traversal_in_request_id_is_sanitized(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        request.request_id = "../etc/passwd"
        request.timestamp = "2026-08-21T00:00:00+00:00"
        driver = LocalFilesystemTransportDriver(repo_root)

        path = driver.send(request)
        assert ".." not in path.name
        assert "/" not in path.name
        assert "\\" not in path.name

    def test_symlink_escape_outside_transport_dir_is_rejected(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        outside = tmp_path / "outside"
        outside.mkdir()
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.outbox_dir.mkdir(parents=True, exist_ok=True)

        # Name the symlink so it matches the request-id glob pattern.
        link_path = driver.outbox_dir / f"evil_{request.request_id}_request.json"
        try:
            link_path.symlink_to(outside / "evil.json")
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        (outside / "evil.json").write_text(
            json.dumps(serialize_transport_request(request)), encoding="utf-8"
        )

        with pytest.raises(ControllerTransportDriverError):
            driver.show(request.request_id)


# ---------------------------------------------------------------------------
# Read-only inspection
# ---------------------------------------------------------------------------


class TestDriverShow:
    def test_show_is_read_only(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        path = driver.send(request)
        original_text = path.read_text(encoding="utf-8")

        view = driver.show(request.request_id)

        assert view.request_id == request.request_id
        assert view.request_path == path
        assert path.read_text(encoding="utf-8") == original_text

    def test_show_returns_response_when_present(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)
        response = _build_response(request, AdapterResultState.PENDING)
        response_path = _write_response(response, driver.inbox_dir)

        view = driver.show(request.request_id)

        assert view.response_path == response_path
        assert view.response is not None
        assert view.response.result_state == AdapterResultState.PENDING.value

    def test_show_formatting_is_human_readable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        view = driver.show(request.request_id)
        text = format_driver_view_summary(view)

        assert "Controller Transport Driver View" in text
        assert request.request_id in text


# ---------------------------------------------------------------------------
# Absence of side effects
# ---------------------------------------------------------------------------


class TestDriverSideEffects:
    def test_send_does_not_mutate_task_lifecycle(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        task_path = tasks_dir / "TASK-016-controller-transport-driver-boundary-foundation.md"
        original_text = "# TASK-016 — Driver\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path.write_text(original_text, encoding="utf-8")

        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        assert task_path.read_text(encoding="utf-8") == original_text

    def test_receive_does_not_mutate_git_or_lifecycle(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        task_path = tasks_dir / "TASK-016-controller-transport-driver-boundary-foundation.md"
        original_text = "# TASK-016 — Driver\n\nSTATUS: REVIEW\n\nBody.\n"
        task_path.write_text(original_text, encoding="utf-8")

        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)
        response = _build_response(request, AdapterResultState.DECISION_RECEIVED)
        _write_response(response, driver.inbox_dir)

        driver.receive(request)

        assert task_path.read_text(encoding="utf-8") == original_text

    def test_driver_uses_no_network_or_subprocess(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        # The driver module does not import socket/subprocess/urllib/requests.
        import ast
        import advancore.agent_runner.controller_transport_driver as driver_module

        source = driver_module.__file__
        assert source is not None
        tree = ast.parse(Path(source).read_text(encoding="utf-8"))
        banned = {"socket", "subprocess", "urllib", "requests", "http.client"}
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        assert imported & banned == set()


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestDriverCLI:
    def test_cli_driver_send_from_latest_handoff(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        _build_request(repo_root)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "driver-send"])
        assert code == 0

        outbox_dir, _ = default_driver_dirs(repo_root)
        assert any(outbox_dir.glob("*_request.json"))

    def test_cli_driver_receive_prints_response(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)
        response = _build_response(request, AdapterResultState.PENDING)
        _write_response(response, driver.inbox_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "driver-receive", request.request_id])
        assert code == 0

    def test_cli_driver_receive_missing_returns_nonzero(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "driver-receive", request.request_id])
        assert code != 0

    def test_cli_driver_show_is_read_only(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)
        path = driver.outbox_dir / driver._find_request_by_id(request.request_id).name
        original_text = path.read_text(encoding="utf-8")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["controller-transport", "driver-show", request.request_id])
        assert code == 0
        assert path.read_text(encoding="utf-8") == original_text


# ---------------------------------------------------------------------------
# Existing envelope reconciliation still delegated
# ---------------------------------------------------------------------------


class TestDriverReconciliationDelegation:
    def test_valid_decision_reference_requires_existing_reconciliation(
        self, tmp_path: Path
    ):
        # Driver receive returns the response; it does not reconcile. The
        # existing TASK-015 apply_transport_response helper remains the path
        # for decision reconciliation.
        repo_root = tmp_path / "repo"
        request, _ = _build_request(repo_root)
        driver = LocalFilesystemTransportDriver(repo_root)
        driver.send(request)

        bundle_path, bundle, handoff_path = _prepare_handoff(repo_root)
        decision = build_controller_decision(
            bundle_path,
            bundle,
            decision="APPROVE",
            actor_role=ActorRole.CONTROLLER,
            repo_root=repo_root,
        )
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        decision_path = write_controller_decision(decision, decisions_dir)

        response = _build_response(
            request,
            AdapterResultState.DECISION_RECEIVED,
            decision_path=str(decision_path.relative_to(repo_root)),
            decision="APPROVE",
        )
        _write_response(response, driver.inbox_dir)

        received = driver.receive(request)
        assert received.result_state == AdapterResultState.DECISION_RECEIVED.value
        assert received.decision_path is not None

        from advancore.agent_runner.controller_transport import apply_transport_response

        result = apply_transport_response(received, repo_root=repo_root, git_info=_git_info(repo_root))
        assert result.reconciled is True
        assert result.decision == "APPROVE"
