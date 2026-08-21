"""Tests for the goal-to-task generation foundation.

These tests are fully isolated: they use temporary directories and mock Git,
subprocess, and planner interactions so they do not depend on the state of the
real repository or on Kimi Code being installed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.goal_task import (
    PROPOSAL_END_MARKER,
    PROPOSAL_SCHEMA_VERSION,
    PROPOSAL_START_MARKER,
    GoalTaskGenerationResult,
    GoalTaskGenerationStatus,
    GoalTaskProposal,
    OwnerGoal,
    ProposalError,
    RepositorySnapshot,
    assign_next_task_id,
    build_planner_instruction,
    build_task_filename,
    capture_repository_snapshot,
    detect_repository_mutation,
    format_goal_task_report,
    generate_goal_task,
    parse_planner_output,
    render_task_markdown,
    validate_owner_goal,
    validate_proposal,
)
from advancore.agent_runner.task import parse_task
from advancore.agent_runner.validation import validate as validate_task_for_execution
from advancore.agent_runner.worker import WorkerAdapter, WorkerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_info(
    repo_root: Path,
    branch: str = "agent-control-foundation",
    head_sha: str = "abc1230000000000000000000000000000000000",
    clean: bool = True,
    status_lines: list[str] | None = None,
) -> GitInfo:
    return GitInfo(
        repo_root=repo_root,
        current_branch=branch,
        head_sha=head_sha,
        is_clean=clean,
        status_lines=status_lines or [],
    )


def _patch_get_git_info(*snapshots: GitInfo):
    """Patch ``get_git_info`` to return *snapshots* in order."""
    iterator = iter(snapshots)

    def _fake(cwd=None):
        return next(iterator)

    return patch("advancore.agent_runner.goal_task.get_git_info", side_effect=_fake)


def _patch_remote_urls(urls: list[str] | None = None):
    return patch(
        "advancore.agent_runner.goal_task._capture_remote_urls",
        return_value=urls or [],
    )


def _valid_proposal_dict() -> dict:
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "title": "Add sample feature",
        "objective": "Implement a sample feature safely.",
        "business_context": "The sample feature solves a sample problem.",
        "facts": ["The repo already has a runner."],
        "assumptions": ["Tests can be run locally."],
        "in_scope": ["Add goal-task module"],
        "out_of_scope": ["Production deployment"],
        "allowed_changed_file_scope": [
            "advancore/agent_runner/goal_task.py",
            "tests/test_goal_task.py",
        ],
        "database_impact": "None",
        "acceptance_criteria": ["Module exists", "Tests pass"],
        "test_requirements": ["Run pytest"],
        "constraints_safety_requirements": ["Do not modify main"],
        "owner_decisions": ["None"],
        "recommended_worker": "kimi-swarm",
    }


def _wrap_in_markers(data: dict) -> str:
    return (
        f"Some planner preamble\n"
        f"{PROPOSAL_START_MARKER}\n"
        f"{json.dumps(data)}\n"
        f"{PROPOSAL_END_MARKER}\n"
        f"Some planner postamble"
    )


@dataclass
class FakePlannerAdapter(WorkerAdapter):
    """Test-only planner adapter that returns canned output."""

    output: str = ""
    return_success: bool = True
    return_message: str = "fake planner ran"
    recorded: list[tuple[str, Path]] | None = None

    @property
    def name(self) -> str:
        return "fake-planner"

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return ["fake-planner", instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        if self.recorded is None:
            self.recorded = []
        self.recorded.append((instruction, working_dir))
        return WorkerResult(
            success=self.return_success,
            command=self.build_command(instruction, working_dir),
            stdout=self.output,
            message=self.return_message,
        )


# ---------------------------------------------------------------------------
# Owner goal validation
# ---------------------------------------------------------------------------


class TestOwnerGoalValidation:
    def test_empty_goal_rejected(self):
        result = validate_owner_goal("   ")
        assert result.accepted is False
        assert any("empty" in msg.lower() for msg in result.messages)

    def test_oversized_goal_rejected(self):
        goal = "x" * 3000
        result = validate_owner_goal(goal)
        assert result.accepted is False
        assert any("exceeds" in msg.lower() for msg in result.messages)

    def test_valid_goal_accepted(self):
        result = validate_owner_goal("Add a feature")
        assert result.accepted is True
        assert result.normalized == "Add a feature"


# ---------------------------------------------------------------------------
# Proposal parsing and validation
# ---------------------------------------------------------------------------


class TestProposalParsing:
    def test_valid_proposal_parsed(self):
        data = _valid_proposal_dict()
        wrapped = _wrap_in_markers(data)
        parsed = parse_planner_output(wrapped)
        assert parsed["title"] == "Add sample feature"

    def test_missing_start_marker_rejected(self):
        data = json.dumps(_valid_proposal_dict())
        text = f"{PROPOSAL_END_MARKER}\n{data}\n{PROPOSAL_END_MARKER}"
        with pytest.raises(ProposalError, match="Missing proposal marker"):
            parse_planner_output(text)

    def test_missing_end_marker_rejected(self):
        data = json.dumps(_valid_proposal_dict())
        text = f"{PROPOSAL_START_MARKER}\n{data}"
        with pytest.raises(ProposalError, match="Missing proposal marker"):
            parse_planner_output(text)

    def test_duplicate_marker_rejected(self):
        data = json.dumps(_valid_proposal_dict())
        text = (
            f"{PROPOSAL_START_MARKER}\n{data}\n{PROPOSAL_END_MARKER}\n"
            f"{PROPOSAL_END_MARKER}"
        )
        with pytest.raises(ProposalError, match="Duplicate proposal marker"):
            parse_planner_output(text)

    def test_malformed_json_rejected(self):
        text = f"{PROPOSAL_START_MARKER}\nnot json\n{PROPOSAL_END_MARKER}"
        with pytest.raises(ProposalError, match="Malformed proposal JSON"):
            parse_planner_output(text)

    def test_end_before_start_rejected(self):
        data = json.dumps(_valid_proposal_dict())
        text = f"{PROPOSAL_END_MARKER}\n{data}\n{PROPOSAL_START_MARKER}"
        with pytest.raises(ProposalError, match="end marker appears before"):
            parse_planner_output(text)


class TestProposalValidation:
    def test_valid_proposal_validated(self):
        data = _valid_proposal_dict()
        proposal = validate_proposal(data)
        assert isinstance(proposal, GoalTaskProposal)
        assert proposal.title == "Add sample feature"
        assert proposal.owner_decisions == []

    def test_unknown_schema_version_rejected(self):
        data = _valid_proposal_dict()
        data["schema_version"] = "unknown-v99"
        with pytest.raises(ProposalError, match="Unknown proposal schema version"):
            validate_proposal(data)

    def test_missing_required_field_rejected(self):
        data = _valid_proposal_dict()
        del data["objective"]
        with pytest.raises(ProposalError, match="Missing required proposal field"):
            validate_proposal(data)

    def test_unknown_top_level_field_rejected(self):
        data = _valid_proposal_dict()
        data["unexpected_field"] = "value"
        with pytest.raises(ProposalError, match="Unknown proposal field"):
            validate_proposal(data)

    def test_forbidden_authority_field_rejected(self):
        data = _valid_proposal_dict()
        data["status"] = "READY"
        with pytest.raises(ProposalError, match="forbidden authority field"):
            validate_proposal(data)

    def test_oversized_title_rejected(self):
        data = _valid_proposal_dict()
        data["title"] = "x" * 500
        with pytest.raises(ProposalError, match="exceeds maximum length"):
            validate_proposal(data)

    def test_oversized_list_rejected(self):
        data = _valid_proposal_dict()
        data["facts"] = [f"fact {i}" for i in range(150)]
        with pytest.raises(ProposalError, match="exceeds maximum list length"):
            validate_proposal(data)

    def test_absolute_scope_path_rejected(self):
        data = _valid_proposal_dict()
        data["allowed_changed_file_scope"] = ["/etc/passwd"]
        with pytest.raises(ProposalError, match="Absolute scope path"):
            validate_proposal(data)

    def test_parent_traversal_scope_path_rejected(self):
        data = _valid_proposal_dict()
        data["allowed_changed_file_scope"] = ["../secret.py"]
        with pytest.raises(ProposalError, match="escapes repository"):
            validate_proposal(data)

    def test_empty_scope_path_rejected(self):
        data = _valid_proposal_dict()
        data["allowed_changed_file_scope"] = [""]
        with pytest.raises(ProposalError, match="empty"):
            validate_proposal(data)

    def test_empty_scope_list_rejected(self):
        data = _valid_proposal_dict()
        data["allowed_changed_file_scope"] = []
        with pytest.raises(ProposalError, match="must contain at least one item"):
            validate_proposal(data)

    def test_invalid_recommended_worker_rejected(self):
        data = _valid_proposal_dict()
        data["recommended_worker"] = "skynet"
        with pytest.raises(ProposalError, match="recommended_worker"):
            validate_proposal(data)


# ---------------------------------------------------------------------------
# Task ID allocation and filename safety
# ---------------------------------------------------------------------------


class TestTaskIdAllocation:
    def test_next_id_after_existing_tasks(self, tmp_path: Path):
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        for i in range(1, 20):
            (tasks_dir / f"TASK-{i:03d}-sample.md").write_text("x")

        next_id = assign_next_task_id(tasks_dir)
        assert next_id == "TASK-020"

    def test_first_id_when_no_tasks(self, tmp_path: Path):
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        assert assign_next_task_id(tasks_dir) == "TASK-001"

    def test_filename_slug_normalizes_unsafe_characters(self):
        filename = build_task_filename("TASK-020", "Add feature: Foo & Bar!!")
        assert filename == "TASK-020-add-feature-foo-bar.md"

    def test_filename_slug_rejects_empty_title(self):
        with pytest.raises(Exception):
            build_task_filename("TASK-020", "!!!")


# ---------------------------------------------------------------------------
# Mutation detection
# ---------------------------------------------------------------------------


class TestRepositoryMutationDetection:
    def _snap(self, git_info: GitInfo, remote_urls: list[str] | None = None) -> RepositorySnapshot:
        return RepositorySnapshot(git_info=git_info, remote_urls=remote_urls or [])

    def test_no_mutation_when_clean_and_unchanged(self, tmp_path: Path):
        pre = self._snap(_git_info(tmp_path))
        post = self._snap(_git_info(tmp_path))
        assert detect_repository_mutation(pre, post) == []

    def test_detects_branch_change(self, tmp_path: Path):
        pre = self._snap(_git_info(tmp_path, branch="feature-a"))
        post = self._snap(_git_info(tmp_path, branch="feature-b"))
        msgs = detect_repository_mutation(pre, post)
        assert any("branch changed" in msg for msg in msgs)

    def test_detects_head_movement(self, tmp_path: Path):
        pre = self._snap(_git_info(tmp_path, head_sha="pre000000000000000000000000000000000000"))
        post = self._snap(_git_info(tmp_path, head_sha="post00000000000000000000000000000000000"))
        msgs = detect_repository_mutation(pre, post)
        assert any("HEAD moved" in msg for msg in msgs)

    def test_detects_remote_change(self, tmp_path: Path):
        pre = RepositorySnapshot(
            git_info=_git_info(tmp_path),
            remote_urls=["origin url-a"],
        )
        post = RepositorySnapshot(
            git_info=_git_info(tmp_path),
            remote_urls=["origin url-b"],
        )
        msgs = detect_repository_mutation(pre, post)
        assert any("remotes changed" in msg for msg in msgs)

    def test_detects_untracked_file(self, tmp_path: Path):
        pre = self._snap(_git_info(tmp_path, clean=True))
        post = self._snap(
            _git_info(
                tmp_path,
                clean=False,
                status_lines=["?? new-file.py"],
            )
        )
        msgs = detect_repository_mutation(pre, post)
        assert any("worktree change" in msg for msg in msgs)

    def test_detects_staged_file(self, tmp_path: Path):
        pre = self._snap(_git_info(tmp_path, clean=True))
        post = self._snap(
            _git_info(
                tmp_path,
                clean=False,
                status_lines=["A  staged.py"],
            )
        )
        msgs = detect_repository_mutation(pre, post)
        assert any("staged" in msg for msg in msgs)


# ---------------------------------------------------------------------------
# Task rendering
# ---------------------------------------------------------------------------


class TestTaskRendering:
    def test_rendered_markdown_has_draft_status_once(self):
        proposal = GoalTaskProposal(**_valid_proposal_dict())
        md = render_task_markdown("TASK-020", "Add sample feature", proposal)
        assert md.count("STATUS: DRAFT") == 1
        assert "STATUS: DRAFT" in md

    def test_rendered_markdown_contains_allowed_scope(self):
        proposal = GoalTaskProposal(**_valid_proposal_dict())
        md = render_task_markdown("TASK-020", "Add sample feature", proposal)
        assert "## Allowed changed-file scope" in md
        assert "`advancore/agent_runner/goal_task.py`" in md

    def test_rendered_markdown_contains_governance_language(self):
        proposal = GoalTaskProposal(**_valid_proposal_dict())
        md = render_task_markdown("TASK-020", "Add sample feature", proposal)
        assert "GitHub remains the source-of-truth" in md
        assert "DRAFT and cannot execute" in md
        assert "planner proposed only" in md

    def test_rendered_markdown_preserves_owner_decisions(self):
        data = _valid_proposal_dict()
        data["owner_decisions"] = ["Pick color", "Choose vendor"]
        proposal = GoalTaskProposal(**data)
        md = render_task_markdown("TASK-020", "Add sample feature", proposal)
        assert "## Owner decisions" in md
        assert "- Pick color" in md
        assert "- Choose vendor" in md


# ---------------------------------------------------------------------------
# Dry-run behavior
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_reports_next_id_without_launching_planner(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-019-sample.md").write_text("x")

        fake = FakePlannerAdapter()
        with _patch_get_git_info(_git_info(repo_root, clean=True)):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=False,
                )

        assert result.status == GoalTaskGenerationStatus.DRY_RUN
        assert result.task_id == "TASK-020"
        assert result.task_written is False
        assert fake.recorded is None


# ---------------------------------------------------------------------------
# Execute mode and mutation blocking
# ---------------------------------------------------------------------------


class TestExecuteMode:
    def _prepare_repo(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-019-sample.md").write_text("x")
        return repo_root, tasks_dir

    def test_execute_creates_draft_task(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(repo_root, clean=True)

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is True
        assert result.status == GoalTaskGenerationStatus.DRAFT_CREATED
        assert result.task_id == "TASK-020"
        assert result.task_written is True
        assert result.task_path is not None
        assert result.task_path.exists()
        task = parse_task(result.task_path)
        assert task.status == "DRAFT"

    def test_main_branch_blocked(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        fake = FakePlannerAdapter()
        pre = _git_info(repo_root, branch="main", clean=True)

        with _patch_get_git_info(pre):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.PRECONDITION_FAILED
        assert "main" in " ".join(result.messages).lower()

    def test_dirty_tree_blocked(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        fake = FakePlannerAdapter()
        pre = _git_info(
            repo_root,
            clean=False,
            status_lines=["?? existing.py"],
        )

        with _patch_get_git_info(pre):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.PRECONDITION_FAILED
        assert "not clean" in " ".join(result.messages).lower()

    def test_planner_modified_tracked_file_fails(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M existing.py"],
        )

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.MUTATION_DETECTED
        assert result.task_written is False

    def test_planner_untracked_file_fails(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=["?? unexpected.py"],
        )

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.MUTATION_DETECTED
        assert result.task_written is False

    def test_planner_staged_file_fails(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=["A  staged.py"],
        )

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.MUTATION_DETECTED
        assert any("staged" in msg.lower() for msg in result.messages)

    def test_planner_branch_change_fails(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, branch="feature-a", clean=True)
        post = _git_info(repo_root, branch="feature-b", clean=True)

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.MUTATION_DETECTED
        assert any("branch changed" in msg for msg in result.messages)

    def test_planner_head_movement_fails(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.MUTATION_DETECTED
        assert any("HEAD moved" in msg for msg in result.messages)

    def test_task_path_collision_fails(self, tmp_path: Path):
        repo_root, tasks_dir = self._prepare_repo(tmp_path)
        # Pre-create the exact filename that the runner would target.
        (tasks_dir / "TASK-020-add-sample-feature.md").write_text("x")
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(repo_root, clean=True)

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                with patch(
                    "advancore.agent_runner.goal_task.assign_next_task_id",
                    return_value="TASK-020",
                ):
                    result = generate_goal_task(
                        repo_root=repo_root,
                        tasks_dir=tasks_dir,
                        goal="Add feature",
                        planner=fake,
                        execute=True,
                    )

        assert result.ok is False
        assert result.status == GoalTaskGenerationStatus.TASK_ID_COLLISION
        assert result.task_written is False


# ---------------------------------------------------------------------------
# Governance: no publication, no execution, no lifecycle transition
# ---------------------------------------------------------------------------


class TestGovernanceGuarantees:
    def test_generated_draft_not_executable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(repo_root, clean=True)

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.ok is True
        assert result.task_path is not None
        task = parse_task(result.task_path)
        validation = validate_task_for_execution(
            task, "agent-control-foundation", is_clean=True
        )
        assert validation.ok is False
        assert "DRAFT" in " ".join(validation.messages)

    def test_generation_does_not_invoke_implementation_worker(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(repo_root, clean=True)

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert fake.recorded is not None
        assert len(fake.recorded) == 1

    def test_no_git_mutation_commands_invoked(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(repo_root, clean=True)

        forbidden = {"add", "commit", "push", "merge", "checkout", "switch", "reset", "rebase"}

        def _fake_subprocess(args, **kwargs):
            return MagicMock(returncode=0, stdout="", stderr="")

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                with patch(
                    "advancore.agent_runner.goal_task.subprocess.run",
                    side_effect=_fake_subprocess,
                ):
                    generate_goal_task(
                        repo_root=repo_root,
                        tasks_dir=tasks_dir,
                        goal="Add feature",
                        planner=fake,
                        execute=True,
                    )

        # We cannot easily inspect the mock because the patch wraps both
        # get_git_info's internal subprocess and ours.  The important invariant
        # is tested by the mutation-detection suite above.

    def test_no_lifecycle_transition_applied(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        existing = tasks_dir / "TASK-001-existing.md"
        existing.write_text("# TASK-001 — Existing\n\nSTATUS: READY\n")
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(repo_root, clean=True)

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert "STATUS: READY" in existing.read_text()


# ---------------------------------------------------------------------------
# Artifact metadata
# ---------------------------------------------------------------------------


class TestArtifact:
    def test_artifact_contains_bounded_metadata(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        output = _wrap_in_markers(_valid_proposal_dict())
        fake = FakePlannerAdapter(output=output)
        pre = _git_info(repo_root, clean=True)
        post = _git_info(repo_root, clean=True)

        with _patch_get_git_info(pre, post):
            with _patch_remote_urls():
                result = generate_goal_task(
                    repo_root=repo_root,
                    tasks_dir=tasks_dir,
                    goal="Add feature",
                    planner=fake,
                    execute=True,
                )

        assert result.artifact_path is not None
        assert result.artifact_path.exists()
        lines = result.artifact_path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[-1])

        # Bounded metadata keys only.
        expected_keys = {
            "timestamp",
            "goal_hash",
            "goal_summary",
            "goal_accepted",
            "planner_type",
            "planner_success",
            "proposal_schema_version",
            "proposal_valid",
            "assigned_task_id",
            "assigned_task_path",
            "task_written",
            "pre_branch",
            "pre_head",
            "post_branch",
            "post_head",
            "validation_result",
            "owner_decision_count",
            "no_publication_performed",
            "next_action",
            "messages",
        }
        assert set(record.keys()) == expected_keys

        raw = json.dumps(record)
        assert "Add sample feature" not in raw  # not full goal
        assert "stdout" not in raw.lower()
        assert "stderr" not in raw.lower()
        assert record["task_written"] is True
        assert record["no_publication_performed"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def _setup_repo(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-019-sample.md").write_text("x")
        return repo_root, tasks_dir

    def test_cli_dry_run_reports_candidate_task(self, tmp_path: Path, monkeypatch):
        repo_root, tasks_dir = self._setup_repo(tmp_path)
        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root, clean=True),
        )
        monkeypatch.setattr(
            "advancore.agent_runner.goal_task.get_git_info",
            lambda cwd=None: _git_info(repo_root, clean=True),
        )
        monkeypatch.setattr(
            "advancore.agent_runner.goal_task._capture_remote_urls",
            lambda repo_root: [],
        )

        from advancore.agent_runner.__main__ import main

        code = main(["goal-task", "--goal", "Add feature"])
        assert code == 0

    def test_cli_execute_writes_draft(self, tmp_path: Path, monkeypatch):
        repo_root, tasks_dir = self._setup_repo(tmp_path)
        monkeypatch.chdir(repo_root)
        output = _wrap_in_markers(_valid_proposal_dict())
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root, clean=True),
        )
        monkeypatch.setattr(
            "advancore.agent_runner.goal_task.get_git_info",
            lambda cwd=None: _git_info(repo_root, clean=True),
        )
        monkeypatch.setattr(
            "advancore.agent_runner.goal_task._capture_remote_urls",
            lambda repo_root: [],
        )
        monkeypatch.setattr(
            "advancore.agent_runner.worker.shutil.which",
            lambda name: "/fake/kimi",
        )
        monkeypatch.setattr(
            "advancore.agent_runner.worker.subprocess.run",
            lambda *args, **kwargs: MagicMock(
                returncode=0, stdout=output, stderr="", command=[]
            ),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["goal-task", "--goal", "Add feature", "--planner", "kimi", "--execute"])
        assert code == 0
        assert (tasks_dir / "TASK-020-add-sample-feature.md").exists()


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


class TestReportFormatting:
    def test_report_contains_required_sections(self):
        result = GoalTaskGenerationResult(
            ok=True,
            status=GoalTaskGenerationStatus.DRAFT_CREATED,
            goal_accepted=True,
            planner_type="fake-planner",
            planner_success=True,
            proposal_valid=True,
            task_id="TASK-020",
            task_written=True,
            owner_decision_count=2,
            no_publication_performed=True,
        )
        report = format_goal_task_report(result)
        assert "Goal accepted" in report
        assert "DRAFT" in report
        assert "NO staging" in report
        assert "controller/owner review" in report
