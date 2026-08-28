"""Contract tests for controller-owned worker scope reservations."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading

import pytest

from advancore.agent_runner.scope_reservations import (
    ReservationStatus,
    ScopeReservationError,
    ScopeReservationService,
)


NOW = datetime(2026, 8, 28, 1, tzinfo=timezone.utc)


def _service(tmp_path: Path) -> tuple[ScopeReservationService, Path]:
    repository = tmp_path / "repo"
    repository.mkdir(parents=True, exist_ok=True)
    state = tmp_path / "controller" / "reservations.json"
    return ScopeReservationService(repository, state), state


def test_non_overlapping_scopes_persist_with_owner_only_permissions(tmp_path):
    service, state = _service(tmp_path)
    service.reserve("TASK-139", "kimi-swarm", ["tests/a.py", "advancore/a.py"], now=NOW)
    service.reserve("TASK-143", "gemini", ["advancore/b.py"], now=NOW)
    reloaded = ScopeReservationService(tmp_path / "repo", state)
    assert [item.task_id for item in reloaded.list_reservations(now=NOW)] == [
        "TASK-139",
        "TASK-143",
    ]
    assert state.stat().st_mode & 0o077 == 0
    assert state.with_suffix(".json.lock").stat().st_mode & 0o077 == 0
    assert state.parent.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["../a.py"],
        ["./a.py"],
        ["a/./b.py"],
        ["/tmp/a.py"],
        ["advancore/*.py"],
        ["a.py", "a.py"],
    ],
)
def test_invalid_scope_paths_fail_closed(tmp_path, paths):
    service, _ = _service(tmp_path)
    with pytest.raises(ScopeReservationError):
        service.reserve("TASK-139", "kimi", paths, now=NOW)


def test_invalid_identity_and_duplicate_task_fail_closed(tmp_path):
    service, _ = _service(tmp_path)
    with pytest.raises(ScopeReservationError):
        service.reserve("task-139", "kimi", ["a.py"], now=NOW)
    with pytest.raises(ScopeReservationError):
        service.reserve("TASK-139", "shell", ["a.py"], now=NOW)
    service.reserve("TASK-139", "kimi", ["a.py"], now=NOW)
    with pytest.raises(ScopeReservationError):
        service.reserve("TASK-139", "gemini", ["b.py"], now=NOW)


def test_exact_and_ancestor_overlaps_fail_closed(tmp_path):
    service, _ = _service(tmp_path)
    service.reserve("TASK-139", "kimi", ["advancore/agent_runner"], now=NOW)
    with pytest.raises(ScopeReservationError):
        service.reserve("TASK-140", "gemini", ["advancore/agent_runner/a.py"], now=NOW)
    with pytest.raises(ScopeReservationError):
        service.reserve("TASK-141", "codex", ["advancore/agent_runner"], now=NOW)


def test_case_and_hardlink_aliases_overlap_fail_closed(tmp_path):
    service, _ = _service(tmp_path)
    repository = tmp_path / "repo"
    shared = repository / "Shared.py"
    shared.write_text("shared\n", encoding="utf-8")
    alias = repository / "hardlink.py"
    os.link(shared, alias)

    service.reserve("TASK-139", "kimi", ["Shared.py"], now=NOW)
    with pytest.raises(ScopeReservationError, match="overlaps"):
        service.reserve("TASK-140", "gemini", ["shared.py"], now=NOW)
    with pytest.raises(ScopeReservationError, match="overlaps"):
        service.reserve("TASK-141", "codex", ["hardlink.py"], now=NOW)


def test_symlink_scope_alias_fails_closed(tmp_path):
    service, _ = _service(tmp_path)
    repository = tmp_path / "repo"
    (repository / "real").mkdir()
    (repository / "alias").symlink_to(repository / "real", target_is_directory=True)

    with pytest.raises(ScopeReservationError, match="symbolic-link alias"):
        service.reserve("TASK-139", "kimi", ["alias/a.py"], now=NOW)


def test_release_and_expiry_allow_later_reservation(tmp_path):
    service, _ = _service(tmp_path)
    service.reserve("TASK-139", "kimi", ["a.py"], now=NOW)
    released = service.release("TASK-139", now=NOW + timedelta(minutes=1))
    assert released.status == ReservationStatus.RELEASED
    service.reserve("TASK-140", "gemini", ["a.py"], now=NOW + timedelta(minutes=2))

    service.reserve("TASK-141", "codex", ["b.py"], now=NOW + timedelta(minutes=3))
    later = NOW + timedelta(hours=4, minutes=3)
    service.reserve("TASK-142", "kimi-swarm", ["b.py"], now=later)
    states = {item.task_id: item.status for item in service.list_reservations(now=later)}
    assert states["TASK-141"] == ReservationStatus.RELEASED
    assert states["TASK-142"] == ReservationStatus.ACTIVE


def test_concurrent_overlap_allows_only_one_writer(tmp_path):
    service, _ = _service(tmp_path)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def reserve(task_id: str) -> None:
        barrier.wait()
        try:
            service.reserve(task_id, "gemini", ["shared.py"], now=NOW)
            outcomes.append("reserved")
        except ScopeReservationError:
            outcomes.append("blocked")

    first = threading.Thread(target=reserve, args=("TASK-139",))
    second = threading.Thread(target=reserve, args=("TASK-140",))
    first.start()
    second.start()
    first.join()
    second.join()
    assert sorted(outcomes) == ["blocked", "reserved"]


def test_corrupt_nested_oversized_future_and_in_repo_state_fail_closed(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    original_mode = repository.stat().st_mode
    with pytest.raises(ScopeReservationError):
        ScopeReservationService(repository, repository / "state.json")
    with pytest.raises(ScopeReservationError, match="dot segment"):
        ScopeReservationService(
            repository,
            tmp_path / "controller" / ".." / "repo" / "reservations.json",
        )
    assert repository.stat().st_mode == original_mode

    service, state = _service(tmp_path)
    state.parent.mkdir(mode=0o700)
    state.write_text("[" * 1200, encoding="utf-8")
    state.chmod(0o600)
    with pytest.raises(ScopeReservationError):
        service.list_reservations(now=NOW)

    state.write_text("x" * (257 * 1024), encoding="utf-8")
    with pytest.raises(ScopeReservationError):
        service.list_reservations(now=NOW)

    state.write_text(
        json.dumps(
            [
                {
                    "task_id": "TASK-139",
                    "worker": "kimi",
                    "paths": ["a.py"],
                    "status": "ACTIVE",
                    "reserved_at": (NOW + timedelta(hours=1)).isoformat(),
                    "expires_at": (NOW + timedelta(hours=2)).isoformat(),
                    "released_at": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    state.chmod(0o600)
    with pytest.raises(ScopeReservationError):
        service.list_reservations(now=NOW)


def test_state_contains_only_bounded_operational_metadata(tmp_path):
    service, state = _service(tmp_path)
    service.reserve("TASK-139", "kimi", ["advancore/a.py"], now=NOW)
    raw = state.read_text(encoding="utf-8")
    for forbidden in ("prompt", "command", "stdout", "stderr", "credential"):
        assert forbidden not in raw.lower()


def test_persisted_overlap_and_future_release_fail_closed(tmp_path):
    service, state = _service(tmp_path)
    state.parent.mkdir(mode=0o700)
    base = {
        "worker": "kimi",
        "status": "ACTIVE",
        "reserved_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=4)).isoformat(),
        "released_at": None,
    }
    state.write_text(
        json.dumps(
            [
                {**base, "task_id": "TASK-139", "paths": ["advancore"]},
                {
                    **base,
                    "task_id": "TASK-140",
                    "worker": "gemini",
                    "paths": ["advancore/a.py"],
                },
            ]
        ),
        encoding="utf-8",
    )
    state.chmod(0o600)
    with pytest.raises(ScopeReservationError, match="scopes overlap"):
        service.list_reservations(now=NOW)

    released = {
        **base,
        "task_id": "TASK-139",
        "paths": ["a.py"],
        "status": "RELEASED",
        "released_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    state.write_text(json.dumps([released]), encoding="utf-8")
    state.chmod(0o600)
    with pytest.raises(ScopeReservationError, match="timing is invalid"):
        service.list_reservations(now=NOW)


def test_swapped_state_parent_and_hardlinked_lock_fail_closed(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    controller = tmp_path / "controller"
    controller.mkdir(mode=0o700)
    state = controller / "reservations.json"
    service = ScopeReservationService(repository, state)

    real_controller = tmp_path / "real-controller"
    controller.rename(real_controller)
    controller.symlink_to(real_controller, target_is_directory=True)
    with pytest.raises(ScopeReservationError):
        service.list_reservations(now=NOW)

    controller.unlink()
    real_controller.rename(controller)
    protected = tmp_path / "protected.txt"
    protected.write_text("owner data", encoding="utf-8")
    protected.chmod(0o600)
    os.link(protected, state.with_suffix(".json.lock"))
    with pytest.raises(ScopeReservationError, match="lock is unsafe"):
        service.list_reservations(now=NOW)
    assert protected.read_text(encoding="utf-8") == "owner data"


def test_backward_reservation_timestamp_fails_without_corrupting_state(tmp_path):
    service, _ = _service(tmp_path)
    service.reserve("TASK-139", "kimi", ["a.py"], now=NOW)

    with pytest.raises(ScopeReservationError, match="moved backward"):
        service.reserve(
            "TASK-140", "gemini", ["b.py"], now=NOW - timedelta(minutes=1)
        )
    assert [item.task_id for item in service.list_reservations(now=NOW)] == [
        "TASK-139"
    ]


def test_fifo_state_file_fails_without_blocking(tmp_path):
    service, state = _service(tmp_path)
    state.parent.mkdir(mode=0o700)
    os.mkfifo(state, mode=0o600)

    with pytest.raises(ScopeReservationError, match="state file is unsafe"):
        service.list_reservations(now=NOW)
