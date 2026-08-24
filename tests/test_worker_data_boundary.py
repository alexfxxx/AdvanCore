"""Fail-closed worker data-boundary tests for TASK-053."""

from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner.worker import (
    CodexPlannerAdapter,
    CodexWorkerAdapter,
    KimiSwarmWorkerAdapter,
    KimiWorkerAdapter,
    build_worker_instruction,
    _isolate_kimi_command,
)


def _task(repo: Path, body: str) -> str:
    tasks = repo / "tasks"
    tasks.mkdir()
    path = tasks / "TASK-053-data-boundary.md"
    path.write_text(
        "# TASK-053 — Data boundary\n\nSTATUS: READY\n\n" + body,
        encoding="utf-8",
    )
    return build_worker_instruction("tasks/TASK-053-data-boundary.md")


@pytest.mark.parametrize(
    "adapter",
    [KimiWorkerAdapter(), KimiSwarmWorkerAdapter(), CodexWorkerAdapter(), CodexPlannerAdapter()],
)
def test_likely_credential_in_referenced_task_blocks_before_launch(
    tmp_path: Path, adapter
):
    instruction = _task(tmp_path, "Temporary token: ghp_abcdefghijklmnopqrstuvwxyz123456")
    with patch("advancore.agent_runner.worker.shutil.which") as which:
        result = adapter.run(instruction, tmp_path)
    assert not result.success
    assert result.terminal_reason == "credential_access_required"
    assert "ghp_" not in result.message
    which.assert_not_called()


def test_normal_governed_task_is_not_misclassified(tmp_path: Path):
    instruction = _task(tmp_path, "No credential access is authorized.")
    with patch("advancore.agent_runner.worker.shutil.which", return_value=None):
        result = CodexWorkerAdapter().run(instruction, tmp_path)
    assert result.terminal_reason != "credential_access_required"


def test_symlinked_task_is_blocked(tmp_path: Path):
    outside = tmp_path.parent / "outside-task.md"
    outside.write_text("# outside", encoding="utf-8")
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "TASK-053-data-boundary.md").symlink_to(outside)
    instruction = build_worker_instruction("tasks/TASK-053-data-boundary.md")
    with patch("advancore.agent_runner.worker.shutil.which") as which:
        result = CodexWorkerAdapter().run(instruction, tmp_path)
    assert result.terminal_reason == "credential_access_required"
    which.assert_not_called()


def test_kimi_profile_denies_reading_common_credential_locations(tmp_path: Path):
    repo = tmp_path.resolve()
    state = repo / "state"
    scratch = repo / "scratch"
    state.mkdir()
    scratch.mkdir()
    service = type("Usage", (), {"protected_state_root": state})()
    command = _isolate_kimi_command(["kimi"], service, repo, scratch)
    profile = command[2]
    assert "deny file-read" in profile
    for protected in (repo / ".env", repo / ".ssh", Path.home() / ".config" / "gh"):
        assert str(protected) in profile
