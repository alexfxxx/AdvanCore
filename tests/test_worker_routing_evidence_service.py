from advancore.agent_runner.worker_registry import WorkerApprovalState
from advancore.agent_runner.worker_routing import WorkerAvailability
from advancore.services.worker_health_service import (
    WorkerHealthState,
    WorkerHealthSummary,
)
from advancore.services.worker_routing_evidence_service import (
    WorkerRoutingEvidenceService,
    WorkerSwitchingStatusService,
    health_to_routing_evidence,
)
from datetime import datetime, timedelta, timezone
import json


def summary(worker, state, approval=WorkerApprovalState.APPROVED):
    return WorkerHealthSummary(worker, worker, approval, state)


def test_known_kimi_health_maps_exactly_without_probe():
    for health, expected in (
        (WorkerHealthState.AVAILABLE, WorkerAvailability.AVAILABLE),
        (WorkerHealthState.PAUSED, WorkerAvailability.PAUSED),
        (WorkerHealthState.STALE, WorkerAvailability.STALE),
        (WorkerHealthState.UNAVAILABLE, WorkerAvailability.UNAVAILABLE),
    ):
        result = health_to_routing_evidence(summary("kimi-swarm", health))
        assert result.worker == "kimi-swarm"
        assert result.state == expected


def test_codex_launch_check_is_not_misreported_as_available():
    result = health_to_routing_evidence(
        summary("codex", WorkerHealthState.CHECKED_AT_LAUNCH)
    )
    assert result.state == WorkerAvailability.UNAVAILABLE


def test_approved_gemini_can_become_available_from_explicit_health():
    result = health_to_routing_evidence(summary("gemini", WorkerHealthState.AVAILABLE))
    assert result.state == WorkerAvailability.AVAILABLE


def test_health_failure_becomes_bounded_unavailable_evidence():
    class Health:
        def get_status(self, worker):
            raise RuntimeError("provider credential traceback")

    service = WorkerRoutingEvidenceService(Health())
    assert service.get("kimi-swarm").state == WorkerAvailability.UNAVAILABLE
    assert service.get("gemini").state == WorkerAvailability.UNAVAILABLE


def test_many_is_ordered_and_rejects_duplicates():
    class Health:
        def get_status(self, worker):
            state = (
                WorkerHealthState.AVAILABLE
                if worker == "kimi-swarm"
                else WorkerHealthState.CHECKED_AT_LAUNCH
            )
            return summary(worker, state)

    service = WorkerRoutingEvidenceService(Health())
    evidence = service.get_many(("kimi-swarm", "codex"))
    assert [item.worker for item in evidence] == ["kimi-swarm", "codex"]

    import pytest

    with pytest.raises(ValueError, match="invalid"):
        service.get_many(("codex", "codex"))


def test_switch_status_reads_only_recent_genuine_bounded_handoffs(tmp_path):
    now = datetime(2026, 8, 26, 5, 0, tzinfo=timezone.utc)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    path = tmp_path / "controller" / "worker-switches.jsonl"
    path.parent.mkdir(parents=True)
    records = []
    for index in range(7):
        records.append(
            {
                "timestamp": (now - timedelta(hours=index)).isoformat(),
                "terminal_worker": "gemini",
                "automatic_handoffs": [
                    {
                        "previous_worker": "kimi-swarm",
                        "next_worker": "gemini",
                        "reason": (
                            "executable",
                            "authentication",
                            "limit_or_quota",
                            "capacity",
                        )[index % 4],
                    }
                ],
            }
        )
    records.extend(
        [
            {
                "timestamp": (now - timedelta(days=8)).isoformat(),
                "terminal_worker": "codex",
                "automatic_handoffs": [
                    {
                        "previous_worker": "gemini",
                        "next_worker": "codex",
                        "reason": "capacity",
                    }
                ],
            },
            {
                "timestamp": now.isoformat(),
                "terminal_worker": "gemini",
                "route_preview": True,
            },
            {
                "timestamp": now.isoformat(),
                "terminal_worker": "gemini",
                "automatic_handoffs": [
                    {
                        "previous_worker": "kimi-swarm",
                        "next_worker": "gemini",
                        "reason": "raw token=/repo/path",
                    }
                ],
            },
        ]
    )
    path.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
    path.chmod(0o600)

    status = WorkerSwitchingStatusService(
        repo_root, lambda: now, evidence_path=path
    ).get_status()
    assert status.selected_worker == "gemini"
    assert len(status.handoffs) == 5
    assert {item.reason for item in status.handoffs} == {
        "executable",
        "authentication",
        "limit_or_quota",
        "capacity",
    }
    assert "token" not in repr(status).lower() and "/repo" not in repr(status)


def test_missing_malformed_or_preview_evidence_is_neutral(tmp_path):
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    path = tmp_path / "controller" / "worker-switches.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "not-json\n"
        + json.dumps({"timestamp": now.isoformat(), "route_preview": True}),
        encoding="utf-8",
    )
    path.chmod(0o600)
    status = WorkerSwitchingStatusService(
        repo_root, lambda: now, evidence_path=path
    ).get_status()
    assert status.selected_worker is None
    assert status.handoffs == ()


def test_expired_selection_is_not_presented_as_current(tmp_path):
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    path = tmp_path / "controller" / "worker-switches.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "timestamp": (now - timedelta(days=8)).isoformat(),
                "terminal_worker": "codex",
                "automatic_handoffs": [],
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)

    status = WorkerSwitchingStatusService(
        repo_root, lambda: now, evidence_path=path
    ).get_status()
    assert status.selected_worker is None
    assert status.handoffs == ()


def test_workspace_receipt_cannot_forge_controller_switching_status(tmp_path):
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    repo_root = tmp_path / "repo"
    local_receipt = repo_root / ".agent_runner" / "auto" / "auto_pipeline.jsonl"
    local_receipt.parent.mkdir(parents=True)
    local_receipt.write_text(
        json.dumps(
            {
                "timestamp": now.isoformat(),
                "terminal_worker": "codex",
                "automatic_handoffs": [
                    {
                        "previous_worker": "gemini",
                        "next_worker": "codex",
                        "reason": "capacity",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    controller_path = tmp_path / "controller" / "worker-switches.jsonl"

    status = WorkerSwitchingStatusService(
        repo_root, lambda: now, evidence_path=controller_path
    ).get_status()

    assert status.selected_worker is None
    assert status.handoffs == ()


def test_switching_status_rejects_workspace_and_insecure_controller_paths(tmp_path):
    import pytest

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    with pytest.raises(ValueError, match="outside the workspace"):
        WorkerSwitchingStatusService(
            repo_root,
            evidence_path=repo_root / ".agent_runner" / "forged.jsonl",
        )

    insecure = tmp_path / "controller" / "worker-switches.jsonl"
    insecure.parent.mkdir()
    insecure.write_text("", encoding="utf-8")
    insecure.chmod(0o644)
    assert WorkerSwitchingStatusService(
        repo_root, evidence_path=insecure
    ).get_status().handoffs == ()
