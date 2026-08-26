import json
from pathlib import Path

import pytest

from advancore.agent_runner.auto_pipeline import ProviderFailure
from advancore.agent_runner.failover import (
    FailoverError,
    advance_failover_checkpoint,
    load_failover_checkpoint,
    save_failover_checkpoint,
    start_failover_checkpoint,
)
from advancore.agent_runner.worker_registry import WorkerRole
from advancore.agent_runner.worker_routing import (
    WorkerAvailability,
    WorkerAvailabilityEvidence,
)


FINGERPRINT = "a" * 64


def available(worker):
    return WorkerAvailabilityEvidence(worker, WorkerAvailability.AVAILABLE)


def started():
    return start_failover_checkpoint(
        run_id="FAILOVER-task084",
        task_id="TASK-084",
        branch="task-084-safe-failover-resume",
        role=WorkerRole.IMPLEMENTATION,
        repository_fingerprint=FINGERPRINT,
        evidence=(available("kimi-swarm"), available("codex")),
    )


def test_start_selects_primary_and_advance_selects_one_distinct_fallback():
    first = started()
    assert first.selected_worker == "kimi-swarm"
    second = advance_failover_checkpoint(
        first,
        failed_worker="kimi-swarm",
        failure=ProviderFailure.QUOTA_OR_CAPACITY,
        repository_fingerprint=FINGERPRINT,
        evidence=(available("kimi-swarm"), available("codex")),
    )
    assert second.selected_worker == "codex"
    assert second.attempted_workers == ("kimi-swarm",)
    assert second.last_failure == ProviderFailure.QUOTA_OR_CAPACITY


def test_unknown_failure_changed_fingerprint_and_wrong_worker_block():
    checkpoint = started()
    kwargs = dict(
        failed_worker="kimi-swarm",
        failure=ProviderFailure.QUOTA_OR_CAPACITY,
        repository_fingerprint=FINGERPRINT,
        evidence=(available("codex"),),
    )
    with pytest.raises(FailoverError, match="does not match"):
        advance_failover_checkpoint(checkpoint, **{**kwargs, "failed_worker": "codex"})
    with pytest.raises(FailoverError, match="fingerprint changed"):
        advance_failover_checkpoint(
            checkpoint, **{**kwargs, "repository_fingerprint": "b" * 64}
        )
    with pytest.raises(FailoverError, match="not eligible"):
        advance_failover_checkpoint(
            checkpoint, **{**kwargs, "failure": ProviderFailure.UNKNOWN}
        )


def test_second_failure_exhausts_bounded_route_without_repeat():
    second = advance_failover_checkpoint(
        started(),
        failed_worker="kimi-swarm",
        failure=ProviderFailure.EXECUTABLE_UNAVAILABLE,
        repository_fingerprint=FINGERPRINT,
        evidence=(available("codex"),),
    )
    with pytest.raises(FailoverError, match="limit is exhausted"):
        advance_failover_checkpoint(
            second,
            failed_worker="codex",
            failure=ProviderFailure.AUTHENTICATION_UNAVAILABLE,
            repository_fingerprint=FINGERPRINT,
            evidence=(available("kimi-swarm"), available("codex")),
        )


def test_candidate_cannot_start_or_become_fallback():
    with pytest.raises(FailoverError, match="No safe initial"):
        start_failover_checkpoint(
            run_id="FAILOVER-gemini",
            task_id="TASK-084",
            branch="feature",
            role="implementation",
            repository_fingerprint=FINGERPRINT,
            evidence=(available("gemini"),),
        )


def test_checkpoint_round_trip_is_strict_bounded_and_secret_free(tmp_path):
    checkpoint = advance_failover_checkpoint(
        started(),
        failed_worker="kimi-swarm",
        failure=ProviderFailure.QUOTA_OR_CAPACITY,
        repository_fingerprint=FINGERPRINT,
        evidence=(available("codex"),),
    )
    path = save_failover_checkpoint(checkpoint, tmp_path / "state")
    assert load_failover_checkpoint(checkpoint.run_id, path.parent) == checkpoint
    payload = path.read_text(encoding="utf-8").lower()
    for forbidden in ("prompt", "stdout", "stderr", "environment", "credential"):
        assert forbidden not in payload
    assert path.stat().st_mode & 0o077 == 0

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(FailoverError, match="invalid"):
        load_failover_checkpoint(checkpoint.run_id, path.parent)


@pytest.mark.parametrize("attempted", ["codex", ["unknown-worker"]])
def test_malformed_attempt_history_fails_closed(tmp_path, attempted):
    path = save_failover_checkpoint(started(), tmp_path / "state")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["attempted_workers"] = attempted
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(FailoverError, match="invalid"):
        load_failover_checkpoint("FAILOVER-task084", path.parent)


def test_duplicate_failover_evidence_is_rejected():
    with pytest.raises(FailoverError, match="Duplicate"):
        advance_failover_checkpoint(
            started(),
            failed_worker="kimi-swarm",
            failure=ProviderFailure.QUOTA_OR_CAPACITY,
            repository_fingerprint=FINGERPRINT,
            evidence=(available("codex"), available("codex")),
        )


def test_symlink_state_paths_fail_closed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(FailoverError, match="unsafe"):
        save_failover_checkpoint(started(), link)

    real = tmp_path / "real"
    path = save_failover_checkpoint(started(), real)
    outside = tmp_path / "outside.json"
    outside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(FailoverError, match="unavailable"):
        load_failover_checkpoint("FAILOVER-task084", real)


def test_symlink_state_directory_is_rejected_before_resolution(tmp_path):
    real = tmp_path / "real-state"
    save_failover_checkpoint(started(), real)
    link = tmp_path / "linked-state"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(FailoverError, match="unavailable"):
        load_failover_checkpoint("FAILOVER-task084", link)
