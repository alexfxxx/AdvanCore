"""Governed worker fallback boundary tests (TASK-022)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner import (
    AutoPipelineStatus,
    CodexWorkerAdapter,
    OrchestrationCheckpoint,
    OrchestrationConfig,
    OrchestrationError,
    ProviderFailure,
    WorkerError,
    WorkerResult,
    build_worker_adapter,
    build_worker_instruction,
    classify_provider_failure,
    load_checkpoint,
    save_checkpoint,
    run_auto_pipeline,
    validate_worker_policy,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.runner import PostWorkerVerification, RunnerResult, RunnerStatus


class _Worker:
    def __init__(self, name: str):
        self.name = name

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return []

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        raise AssertionError("execute is mocked")


def _git(repo: Path, status: list[str] | None = None) -> GitInfo:
    return GitInfo(repo, "agent-control-foundation", "a" * 40, not status, status or [])


def _runner(repo: Path, worker: str, success: bool, message: str, status=None) -> RunnerResult:
    pre = _git(repo)
    post = _git(repo, status)
    return RunnerResult(
        status=RunnerStatus.AWAITING_APPROVAL if success else RunnerStatus.WORKER_FAILED,
        git_info=post, pre_git_info=pre, post_git_info=post, worker_type=worker,
        worker_result=WorkerResult(success, message=message),
        post_verification=PostWorkerVerification(not status, changed_paths=[]),
    )


def _task_dir(tmp_path: Path) -> Path:
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "TASK-022-test.md").write_text(
        "# TASK-022 — test\n\nSTATUS: READY\n\n## Allowed changed-file scope\n\n1. `only.py`\n",
        encoding="utf-8",
    )
    return tasks


def test_codex_missing_executable_is_bounded(tmp_path: Path):
    with patch("advancore.agent_runner.worker.shutil.which", return_value=None):
        result = CodexWorkerAdapter().run("bounded", tmp_path)
    assert not result.success
    assert result.stdout is None and result.stderr is None
    assert "not found in PATH" in result.message


def test_codex_argv_is_fixed_safe_and_argv_only(tmp_path: Path):
    instruction = "one bounded prompt; $(never-shell-expand)"
    command = CodexWorkerAdapter().build_command(instruction, tmp_path)
    assert command == [
        "codex", "--ask-for-approval", "never", "exec", "--ephemeral",
        "--sandbox", "workspace-write", "--cd", str(tmp_path.resolve()), instruction,
    ]
    forbidden = {
        "--dangerously-bypass-approvals-and-sandbox", "danger-full-access",
        "--add-dir", "--search", "--config", "cloud", "remote",
    }
    assert forbidden.isdisjoint(command)


def test_registry_builds_only_code_owned_adapters():
    assert build_worker_adapter("codex").name == "codex"
    with pytest.raises(WorkerError, match="Unknown"):
        build_worker_adapter("/tmp/arbitrary --command")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Worker executable 'kimi' not found in PATH", ProviderFailure.EXECUTABLE_UNAVAILABLE),
        ("provider quota exhausted", ProviderFailure.QUOTA_OR_CAPACITY),
        ("429 rate limit", ProviderFailure.QUOTA_OR_CAPACITY),
        ("authentication unavailable", ProviderFailure.AUTHENTICATION_UNAVAILABLE),
        ("implementation crashed", ProviderFailure.UNKNOWN),
    ],
)
def test_provider_failure_classification(message: str, expected: ProviderFailure):
    assert classify_provider_failure(WorkerResult(False, message=message)) == expected


def test_default_has_no_fallback():
    assert OrchestrationConfig().fallback_worker is None


def test_explicit_kimi_to_codex_policy_is_accepted():
    validate_worker_policy("kimi-swarm", "codex")


@pytest.mark.parametrize(
    ("primary", "fallback"),
    [("kimi", "kimi"), ("kimi", "dry-run"), ("dry-run", "codex"), ("kimi", "unknown")],
)
def test_unsafe_fallback_policies_fail_closed(primary: str, fallback: str):
    with pytest.raises(WorkerError):
        validate_worker_policy(primary, fallback)


def test_instruction_has_scope_and_worker_role_separation():
    instruction = build_worker_instruction("tasks/TASK-022.md", ["only.py"])
    assert "Allowed changed-file scope:\n- only.py" in instruction
    for prohibition in ("Do not commit", "decide/approve", "DRAFT to READY", "finalize"):
        assert prohibition in instruction


def test_checkpoint_persists_fallback_and_bounded_content(tmp_path: Path):
    checkpoint = OrchestrationCheckpoint(
        schema_version="advancore-orchestration-v1", run_id="ORCH-fallback",
        goal_hash="abcd", goal_summary="bounded", planner="dry-run",
        worker="kimi-swarm", fallback_worker="codex", controller="manual",
        repair_attempts=0, max_rework=0, apply=True, phase="TASK_EXECUTION",
    )
    path = save_checkpoint(checkpoint, tmp_path)
    loaded = load_checkpoint("ORCH-fallback", tmp_path)
    assert loaded.worker == "kimi-swarm" and loaded.fallback_worker == "codex"
    raw = path.read_text(encoding="utf-8").lower()
    assert "stdout" not in raw and "stderr" not in raw and "credential" not in raw


def test_orchestration_rejects_unknown_or_duplicate_fallback():
    with pytest.raises(OrchestrationError):
        OrchestrationConfig(worker="kimi", fallback_worker="kimi")
    with pytest.raises(OrchestrationError):
        OrchestrationConfig(worker="kimi", fallback_worker="not-registered")


def test_clean_provider_failure_invokes_explicit_fallback_and_verification(tmp_path: Path):
    tasks = _task_dir(tmp_path)
    primary = _runner(tmp_path, "kimi", False, "quota exhausted")
    terminal = _runner(tmp_path, "codex", True, "ok")
    with patch("advancore.agent_runner.auto_pipeline.execute", side_effect=[primary, terminal]) as execute_mock, patch(
        "advancore.agent_runner.auto_pipeline._remote_fingerprint", return_value=("origin x",)
    ), patch("advancore.agent_runner.auto_pipeline.detect_staged_paths", return_value=[]), patch(
        "advancore.agent_runner.auto_pipeline._run_verification_sequence", side_effect=lambda result, *args: result
    ) as verify_mock:
        result = run_auto_pipeline(tasks, "TASK-022", _Worker("kimi"), fallback_worker=_Worker("codex"))
    assert execute_mock.call_count == 2 and verify_mock.call_count == 1
    assert result.primary_worker == "kimi" and result.terminal_worker == "codex"
    assert result.fallback_attempt and result.fallback_attempt.integrity_ok
    assert any("kimi -> codex" in message for message in result.messages)


@pytest.mark.parametrize("message", ["unexpected worker crash", "malformed output"])
def test_unknown_failure_never_falls_back(tmp_path: Path, message: str):
    tasks = _task_dir(tmp_path)
    primary = _runner(tmp_path, "kimi", False, message)
    with patch("advancore.agent_runner.auto_pipeline.execute", return_value=primary) as execute_mock, patch(
        "advancore.agent_runner.auto_pipeline._remote_fingerprint", return_value=("origin x",)
    ), patch("advancore.agent_runner.auto_pipeline.detect_staged_paths", return_value=[]):
        result = run_auto_pipeline(tasks, "TASK-022", _Worker("kimi"), fallback_worker=_Worker("codex"))
    assert execute_mock.call_count == 1
    assert result.status == AutoPipelineStatus.WORKER_FAILED
    assert result.fallback_attempt.failure == ProviderFailure.UNKNOWN


def test_primary_worktree_mutation_blocks_fallback(tmp_path: Path):
    tasks = _task_dir(tmp_path)
    primary = _runner(tmp_path, "kimi", False, "quota exhausted", ["?? only.py"])
    with patch("advancore.agent_runner.auto_pipeline.execute", return_value=primary) as execute_mock, patch(
        "advancore.agent_runner.auto_pipeline._remote_fingerprint", return_value=("origin x",)
    ), patch("advancore.agent_runner.auto_pipeline.detect_staged_paths", return_value=[]):
        result = run_auto_pipeline(tasks, "TASK-022", _Worker("kimi"), fallback_worker=_Worker("codex"))
    assert execute_mock.call_count == 1
    assert not result.fallback_attempt.integrity_ok
    assert result.status == AutoPipelineStatus.WORKER_FAILED
