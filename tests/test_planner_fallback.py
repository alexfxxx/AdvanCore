"""Governed proposal-planner boundary and fallback tests (TASK-028)."""

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner.worker import (
    CodexPlannerAdapter,
    WorkerError,
    build_planner_adapter,
    validate_planner_policy,
    WorkerAdapter,
    WorkerResult,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.goal_task import (
    PROPOSAL_END_MARKER,
    PROPOSAL_SCHEMA_VERSION,
    PROPOSAL_START_MARKER,
    GoalTaskGenerationStatus,
    RepositorySnapshot,
    generate_goal_task,
)
from advancore.agent_runner.orchestration import (
    OrchestrationConfig,
    _new_checkpoint,
)


def test_codex_planner_argv_is_fixed_ephemeral_and_read_only(tmp_path: Path):
    command = CodexPlannerAdapter(timeout_seconds=30).build_command("one prompt", tmp_path)
    assert command == [
        "codex", "--ask-for-approval", "never", "exec", "--ephemeral",
        "--sandbox", "read-only", "--cd", str(tmp_path.resolve()), "one prompt",
    ]
    joined = " ".join(command)
    assert "workspace-write" not in joined
    assert "danger-full-access" not in joined
    assert "--config" not in command


def test_registered_kimi_planners_are_proposal_only_and_bounded():
    for name in ("kimi", "kimi-swarm"):
        planner = build_planner_adapter(name, timeout_seconds=17)
        assert planner.name == name
        assert planner.implementation_worker is False
        assert planner.timeout_seconds == 17


@pytest.mark.parametrize(
    ("primary", "fallback"),
    [("dry-run", "codex"), ("kimi", "dry-run"), ("kimi", "kimi")],
)
def test_unsafe_planner_fallback_policy_is_rejected(primary: str, fallback: str):
    with pytest.raises(WorkerError):
        validate_planner_policy(primary, fallback)


def test_explicit_single_fallback_policy_is_accepted():
    validate_planner_policy("kimi-swarm", "codex")


@dataclass
class _Planner(WorkerAdapter):
    planner_name: str
    result: WorkerResult
    calls: int = 0
    timeout_seconds: int = 23

    @property
    def name(self) -> str:
        return self.planner_name

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return [self.planner_name, instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        self.calls += 1
        return self.result


def _snapshot(repo: Path, *, clean: bool = True) -> RepositorySnapshot:
    return RepositorySnapshot(
        GitInfo(
            repo_root=repo,
            current_branch="agent-control-foundation",
            head_sha="a" * 40,
            is_clean=clean,
            status_lines=[] if clean else ["?? planner-write.txt"],
        ),
        ["origin https://example.invalid/repo.git"],
    )


def _proposal() -> str:
    payload = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "title": "Fallback proposal",
        "objective": "Validate bounded planner fallback.",
        "business_context": "Planner availability must not block governance.",
        "facts": ["The runner constructs tasks."],
        "assumptions": ["Local planners are configured externally."],
        "in_scope": ["Add deterministic validation."],
        "out_of_scope": ["Deployment."],
        "allowed_changed_file_scope": ["tests/test_planner_fallback.py"],
        "database_impact": "None",
        "acceptance_criteria": ["Fallback is explicit."],
        "test_requirements": ["Run pytest."],
        "constraints_safety_requirements": ["Do not modify main."],
        "owner_decisions": ["None"],
        "recommended_worker": "codex",
    }
    return f"{PROPOSAL_START_MARKER}\n{json.dumps(payload)}\n{PROPOSAL_END_MARKER}"


def _run_generation(
    tmp_path: Path,
    primary: _Planner,
    fallback: _Planner,
    snapshots: list[RepositorySnapshot],
):
    repo = tmp_path / "repo"
    tasks = repo / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "TASK-027-existing.md").write_text("# TASK-027 — Existing\n\nSTATUS: APPROVED\n")
    with patch(
        "advancore.agent_runner.goal_task.capture_repository_snapshot",
        side_effect=snapshots,
    ):
        return generate_goal_task(
            repo_root=repo,
            tasks_dir=tasks,
            goal="Create one governed fallback validation task",
            planner=primary,
            fallback_planner=fallback,
            execute=True,
        )


def test_clean_quota_failure_uses_exactly_one_fallback_and_runner_writes_draft(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    primary = _Planner("kimi-swarm", WorkerResult(False, message="quota exhausted"))
    fallback = _Planner("codex", WorkerResult(True, stdout=_proposal()))
    result = _run_generation(
        tmp_path, primary, fallback, [_snapshot(repo), _snapshot(repo), _snapshot(repo)]
    )
    assert result.status == GoalTaskGenerationStatus.DRAFT_CREATED
    assert result.fallback_used and result.terminal_planner == "codex"
    assert result.failure_classification == "QUOTA_OR_CAPACITY"
    assert primary.calls == fallback.calls == 1
    assert result.task_path and "STATUS: DRAFT" in result.task_path.read_text()


def test_primary_mutation_blocks_fallback_and_task_write(tmp_path: Path):
    repo = tmp_path / "repo"
    primary = _Planner("kimi", WorkerResult(False, message="quota exhausted"))
    fallback = _Planner("codex", WorkerResult(True, stdout=_proposal()))
    result = _run_generation(
        tmp_path, primary, fallback, [_snapshot(repo), _snapshot(repo, clean=False)]
    )
    assert result.status == GoalTaskGenerationStatus.MUTATION_DETECTED
    assert primary.calls == 1 and fallback.calls == 0
    assert not result.task_written


@pytest.mark.parametrize("reason", ["timeout", "cancelled"])
def test_timeout_or_cancellation_never_falls_back(tmp_path: Path, reason: str):
    repo = tmp_path / "repo"
    primary = _Planner(
        "kimi", WorkerResult(False, message=reason, terminal_reason=reason)
    )
    fallback = _Planner("codex", WorkerResult(True, stdout=_proposal()))
    result = _run_generation(
        tmp_path, primary, fallback, [_snapshot(repo), _snapshot(repo)]
    )
    assert result.status == GoalTaskGenerationStatus.PLANNER_FAILED
    assert result.failure_classification == reason.upper()
    assert fallback.calls == 0 and not result.task_written


def test_malformed_fallback_proposal_stops_without_third_hop(tmp_path: Path):
    repo = tmp_path / "repo"
    primary = _Planner("kimi", WorkerResult(False, message="not authenticated"))
    fallback = _Planner("codex", WorkerResult(True, stdout="not a proposal"))
    result = _run_generation(
        tmp_path, primary, fallback, [_snapshot(repo), _snapshot(repo), _snapshot(repo)]
    )
    assert result.status == GoalTaskGenerationStatus.PROPOSAL_REJECTED
    assert primary.calls == fallback.calls == 1
    assert not result.task_written


def test_checkpoint_persists_planner_policy_and_bounded_evidence(tmp_path: Path):
    repo = tmp_path / "repo"
    config = OrchestrationConfig(
        goal="bounded", planner="kimi-swarm", fallback_planner="codex",
        planner_timeout_seconds=321,
    )
    git_info = GitInfo(
        repo_root=repo, current_branch="agent-control-foundation",
        head_sha="a" * 40, is_clean=True, status_lines=[],
    )
    with patch("advancore.agent_runner.orchestration.get_git_info", return_value=git_info):
        checkpoint = _new_checkpoint(config, repo)
    checkpoint.terminal_planner = "codex"
    checkpoint.planner_failure_classification = "QUOTA_OR_CAPACITY"
    checkpoint.planner_integrity_ok = True
    checkpoint.planner_recovery_evidence = ["branch_unchanged=True"]
    assert checkpoint.planner == "kimi-swarm"
    assert checkpoint.fallback_planner == "codex"
    assert checkpoint.planner_timeout_seconds == 321
    assert checkpoint.terminal_planner == "codex"
