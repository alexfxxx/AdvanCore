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
    MAX_WORKER_INPUT_BYTES,
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


def test_noncanonical_case_task_reference_is_blocked(tmp_path: Path):
    instruction = _task(tmp_path, "Normal content.").replace("tasks/", "Tasks/")
    with patch("advancore.agent_runner.worker.shutil.which") as which:
        result = CodexWorkerAdapter().run(instruction, tmp_path)
    assert result.terminal_reason == "credential_access_required"
    which.assert_not_called()


@pytest.mark.parametrize(
    "replacement",
    ["tasks/./TASK-053-data-boundary.md", "TASK-053-data-boundary.md"],
)
def test_noncanonical_structural_task_reference_is_blocked(
    tmp_path: Path, replacement: str
):
    instruction = _task(tmp_path, "Normal content.").replace(
        "tasks/TASK-053-data-boundary.md", replacement
    )
    with patch("advancore.agent_runner.worker.shutil.which") as which:
        result = CodexWorkerAdapter().run(instruction, tmp_path)
    assert result.terminal_reason == "credential_access_required"
    which.assert_not_called()


@pytest.mark.parametrize(
    "credential",
    [
        "DATABASE_URL=postgresql://person:private-value@database.example/app",
        "GITHUB_TOKEN=ordinary-looking-private-value",
        "SERVICE_PASSWORD: private-value",
    ],
)
def test_common_credential_forms_in_task_are_blocked(
    tmp_path: Path, credential: str
):
    instruction = _task(tmp_path, credential)
    with patch("advancore.agent_runner.worker.shutil.which") as which:
        result = CodexWorkerAdapter().run(instruction, tmp_path)
    assert result.terminal_reason == "credential_access_required"
    assert "private-value" not in result.message
    which.assert_not_called()


@pytest.mark.parametrize(
    "placeholder",
    ["GITHUB_TOKEN=<redacted>", "API_KEY=${API_KEY}", "PASSWORD=placeholder"],
)
def test_explicit_placeholders_do_not_create_false_credential_match(
    tmp_path: Path, placeholder: str
):
    instruction = _task(tmp_path, placeholder)
    with patch("advancore.agent_runner.worker.shutil.which", return_value=None):
        result = CodexWorkerAdapter().run(instruction, tmp_path)
    assert result.terminal_reason != "credential_access_required"


def test_oversized_direct_instruction_is_blocked(tmp_path: Path):
    instruction = "x" * (MAX_WORKER_INPUT_BYTES + 1)
    with patch("advancore.agent_runner.worker.shutil.which") as which:
        result = CodexPlannerAdapter().run(instruction, tmp_path)
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
    for protected in (
        repo / ".env",
        repo / ".ssh",
        Path.home() / ".config" / "gh",
        Path.home() / ".git-credentials",
        Path.home() / ".config" / "git" / "credentials",
    ):
        assert str(protected) in profile


def test_codex_planner_receives_minimal_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "controller-secret")
    with patch("advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/codex"), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process"
    ) as bounded:
        CodexPlannerAdapter().run("safe proposal", tmp_path)
    command = bounded.call_args.args[0]
    environment = bounded.call_args.kwargs["environment"]
    assert command[0] == "/usr/bin/codex"
    assert environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert "DATABASE_URL" not in environment
