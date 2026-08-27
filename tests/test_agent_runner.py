"""Tests for the local agent runner foundation.

These tests are fully isolated: they use temporary directories and mock Git,
subprocess, and worker interactions so they do not depend on the state of the
real repository or on Kimi Code being installed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from advancore.agent_runner import (
    DryRunWorkerAdapter,
    KimiWorkerAdapter,
    WorkerAdapter,
    WorkerResult,
    build_worker_instruction,
    discover_tasks,
    execute,
    find_task,
    parse_task,
    plan,
    validate,
)
import json

from advancore.agent_runner.audit import (
    AUDIT_FILENAME,
    AuditWriteError,
    build_audit_payload,
    default_audit_dir,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.runner import RunnerStatus, verify_post_worker
from advancore.agent_runner.task import Task, TaskError
from advancore.agent_runner.validation import (
    OwnerReworkEvidence,
    ReworkValidationPhase,
    capture_owner_rework_evidence,
    validate_owner_rework_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_task(
    tasks_dir: Path,
    task_id: str,
    title: str,
    status: str,
    filename: str | None = None,
    content: str | None = None,
) -> Path:
    """Write a minimal task file and return its path."""
    filename = filename or f"{task_id}-sample-task.md"
    path = tasks_dir / filename
    body = content if content is not None else "Do the thing."
    path.write_text(
        f"# {task_id} — {title}\n\nSTATUS: {status}\n\n## Objective\n\n{body}\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------


def test_phase_aware_owner_rework_evidence_uses_real_git(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "feature/rework"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", "../remote.git"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(".agent_runner/\n", encoding="utf-8")
    tasks = repo / "tasks"
    tasks.mkdir()
    task_path = _write_task(tasks, "TASK-038", "Rework", "READY")
    source = repo / "bounded.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/feature/rework", head],
        cwd=repo,
        check=True,
    )
    source.write_text("value = 2\n", encoding="utf-8")
    task_path.write_text(
        task_path.read_text().replace("STATUS: READY", "STATUS: REVIEW"),
        encoding="utf-8",
    )
    evidence_dir = repo / ".agent_runner" / "evidence"
    evidence_dir.mkdir(parents=True)
    bundle_path = evidence_dir / "bundle.json"
    handoff_path = evidence_dir / "handoff.json"
    decision_path = evidence_dir / "decision.json"
    bundle_path.write_text("bundle", encoding="utf-8")
    handoff_path.write_text("handoff", encoding="utf-8")
    decision_path.write_text("decision", encoding="utf-8")
    artifact_hash = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    scope = ["bounded.py", f"tasks/{task_path.name}"]
    evidence = capture_owner_rework_evidence(
        repo,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        run_id="run-038",
        review_bundle_id=artifact_hash(bundle_path),
        review_bundle_path=str(bundle_path),
        handoff_id=artifact_hash(handoff_path),
        handoff_path=str(handoff_path),
        decision_id=artifact_hash(decision_path),
        decision_path=str(decision_path),
        allowed_scope=scope,
        owner_note="Refresh after editing.",
    )
    assert isinstance(evidence, OwnerReworkEvidence)

    wrong_lifecycle = execute(
        tasks,
        "TASK-038",
        worker=DryRunWorkerAdapter(),
        rework_evidence=evidence,
    )
    assert wrong_lifecycle.status == RunnerStatus.FAILED
    assert "requires task status REWORK" in " ".join(wrong_lifecycle.messages)

    task_path.write_text(
        task_path.read_text().replace("STATUS: REVIEW", "STATUS: REWORK"),
        encoding="utf-8",
    )
    baseline = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.BASELINE,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        run_id="run-038",
        allowed_scope=scope,
    )
    assert baseline

    bundle_path.write_text("mutated", encoding="utf-8")
    stale_bundle = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.BASELINE,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        allowed_scope=scope,
    )
    assert not stale_bundle
    assert "review_bundle_id" in stale_bundle.messages[0]
    bundle_path.write_text("bundle", encoding="utf-8")

    lifecycle_only = task_path.read_text(encoding="utf-8")
    task_path.write_text(lifecycle_only + "\nunauthorized = true\n", encoding="utf-8")
    task_mutated = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.BASELINE,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        allowed_scope=scope,
    )
    assert not task_mutated
    assert "normalized_task_hash" in task_mutated.messages[0]
    task_path.write_text(lifecycle_only, encoding="utf-8")

    source.write_text("value = 3\n", encoding="utf-8")
    changed_baseline = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.BASELINE,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        allowed_scope=scope,
    )
    terminal = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.TERMINAL,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        allowed_scope=scope,
    )
    assert not changed_baseline
    assert "binary_diff_hash" in changed_baseline.messages[0]
    assert terminal

    (repo / "unexpected.txt").write_text("no\n", encoding="utf-8")
    unexpected = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.TERMINAL,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        allowed_scope=scope,
    )
    assert not unexpected
    assert "ambiguous Git state" in unexpected.messages[0]

    (repo / "unexpected.txt").unlink()
    subprocess.run(
        ["git", "remote", "set-url", "origin", "../changed.git"],
        cwd=repo,
        check=True,
    )
    remote_changed = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.TERMINAL,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        allowed_scope=scope,
    )
    assert not remote_changed
    assert "remote_config_hash" in remote_changed.messages[0]

    subprocess.run(
        ["git", "remote", "set-url", "origin", "../remote.git"],
        cwd=repo,
        check=True,
    )
    with pytest.raises(ValueError, match="unsafe repository path"):
        capture_owner_rework_evidence(
            repo,
            task_id="TASK-038",
            task_path="../escape.md",
            run_id="run-038",
            review_bundle_id=artifact_hash(bundle_path),
            review_bundle_path=str(bundle_path),
            handoff_id=artifact_hash(handoff_path),
            handoff_path=str(handoff_path),
            decision_id=artifact_hash(decision_path),
            decision_path=str(decision_path),
            allowed_scope=scope,
        )
    subprocess.run(["git", "add", "bounded.py"], cwd=repo, check=True)
    staged = validate_owner_rework_evidence(
        evidence,
        repo,
        phase=ReworkValidationPhase.TERMINAL,
        task_id="TASK-038",
        task_path=f"tasks/{task_path.name}",
        allowed_scope=scope,
    )
    assert not staged
    assert "ambiguous Git state" in staged.messages[0]


class TestTaskParsing:
    def test_ready_task_is_parsed_correctly(self, tmp_path: Path):
        path = _write_task(tmp_path, "TASK-001", "Sample Ready Task", "READY")

        task = parse_task(path)

        assert task.task_id == "TASK-001"
        assert task.title == "Sample Ready Task"
        assert task.status == "READY"
        assert task.filename == "TASK-001-sample-task.md"
        assert task.path == path

    def test_missing_status_fails_safely(self, tmp_path: Path):
        path = tmp_path / "TASK-001-no-status.md"
        path.write_text("# TASK-001 — No Status\n\nNo status line here.\n")

        with pytest.raises(TaskError, match="No STATUS line"):
            parse_task(path)

    def test_missing_title_fails_safely(self, tmp_path: Path):
        path = tmp_path / "TASK-001-no-title.md"
        path.write_text("STATUS: READY\n\nNo title.\n")

        with pytest.raises(TaskError, match="No title/ID"):
            parse_task(path)

    def test_id_mismatch_between_filename_and_title_fails(self, tmp_path: Path):
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Mismatch",
            "READY",
            filename="TASK-002-mismatch.md",
        )

        with pytest.raises(TaskError, match="Task ID mismatch"):
            parse_task(path)

    def test_bad_filename_pattern_fails(self, tmp_path: Path):
        path = tmp_path / "not-a-task.md"
        path.write_text("# TASK-001 — Bad\n\nSTATUS: READY\n")

        with pytest.raises(TaskError, match="Filename does not match"):
            parse_task(path)


# ---------------------------------------------------------------------------
# Task discovery and selection
# ---------------------------------------------------------------------------


class TestTaskDiscoveryAndSelection:
    def test_discover_tasks_skips_unparseable_files(self, tmp_path: Path):
        _write_task(tmp_path, "TASK-001", "Ready", "READY")
        (tmp_path / "TASK-002-bad.md").write_text("no status")

        tasks = discover_tasks(tmp_path)

        assert len(tasks) == 1
        assert tasks[0].task_id == "TASK-001"

    def test_find_task_by_id(self, tmp_path: Path):
        _write_task(tmp_path, "TASK-001", "One", "READY")
        _write_task(tmp_path, "TASK-002", "Two", "READY")

        task = find_task(tmp_path, "TASK-002")

        assert task.task_id == "TASK-002"
        assert task.title == "Two"

    def test_find_task_by_path(self, tmp_path: Path):
        _write_task(tmp_path, "TASK-001", "One", "READY")

        task = find_task(tmp_path, "TASK-001-sample-task.md")

        assert task.task_id == "TASK-001"

    def test_find_task_path_rejects_traversal_and_symlink_escape(self, tmp_path: Path):
        outside = tmp_path.parent / "TASK-001-outside.md"
        _write_task(
            tmp_path.parent,
            "TASK-001",
            "Outside",
            "READY",
            filename=outside.name,
        )
        link = tmp_path / "TASK-001-link.md"
        link.symlink_to(outside)

        with pytest.raises(TaskError, match="not found"):
            find_task(tmp_path, "../TASK-001-outside.md")
        with pytest.raises(TaskError, match="not found"):
            find_task(tmp_path, link.name)

    def test_find_task_unknown_raises(self, tmp_path: Path):
        with pytest.raises(TaskError, match="not found"):
            find_task(tmp_path, "TASK-999")

    def test_find_task_ambiguous_raises(self, tmp_path: Path):
        _write_task(
            tmp_path,
            "TASK-001",
            "One",
            "READY",
            filename="TASK-001-one.md",
        )
        _write_task(
            tmp_path,
            "TASK-001",
            "One Again",
            "READY",
            filename="TASK-001-two.md",
        )

        with pytest.raises(TaskError, match="ambiguous"):
            find_task(tmp_path, "TASK-001")


# ---------------------------------------------------------------------------
# Status gate
# ---------------------------------------------------------------------------


class TestStatusGate:
    def _task(self, tmp_path: Path, status: str) -> Task:
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Status Test",
            status,
            filename=f"TASK-001-{status.lower()}.md",
        )
        return parse_task(path)

    def test_ready_is_executable(self, tmp_path: Path):
        task = self._task(tmp_path, "READY")
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is True

    def test_rework_is_executable(self, tmp_path: Path):
        task = self._task(tmp_path, "REWORK")
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is True

    @pytest.mark.parametrize(
        "status",
        ["DRAFT", "REVIEW", "APPROVED", "BLOCKED", "IN_PROGRESS"],
    )
    def test_non_executable_statuses_are_rejected(self, tmp_path: Path, status: str):
        task = self._task(tmp_path, status)
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is False
        assert status in " ".join(result.messages)


# ---------------------------------------------------------------------------
# Branch gate
# ---------------------------------------------------------------------------


class TestBranchGate:
    def test_non_main_branch_passes(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "agent-control-foundation", is_clean=True)
        assert result.ok is True
        assert any("not 'main'" in msg for msg in result.messages)

    def test_main_branch_fails(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "main", is_clean=True)
        assert result.ok is False
        assert any("main" in msg for msg in result.messages)


# ---------------------------------------------------------------------------
# Working-tree gate
# ---------------------------------------------------------------------------


class TestWorkingTreeGate:
    def test_clean_tree_passes(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "feature-branch", is_clean=True)
        assert result.ok is True

    def test_dirty_tree_fails(self, tmp_path: Path):
        task = parse_task(
            _write_task(tmp_path, "TASK-001", "Ready", "READY")
        )
        result = validate(task, "feature-branch", is_clean=False)
        assert result.ok is False
        assert any("uncommitted" in msg for msg in result.messages)


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------


class TestPromptGeneration:
    def test_instruction_references_agents_md_and_one_task_path(self):
        instruction = build_worker_instruction(
            "tasks/TASK-005-local-agent-runner-foundation.md"
        )

        assert "Read AGENTS.md" in instruction
        assert instruction.count("tasks/") == 1
        assert "tasks/TASK-005-local-agent-runner-foundation.md" in instruction
        assert "Execute" in instruction
        assert "completion report" in instruction

    def test_instruction_contains_approval_gate(self):
        instruction = build_worker_instruction("tasks/TASK-001.md")

        assert "Do not commit" in instruction
        assert "until explicitly approved" in instruction

    def test_instruction_does_not_embed_full_task_spec(self, tmp_path: Path):
        long_content = "Business context: " + "x " * 500
        path = _write_task(
            tmp_path,
            "TASK-001",
            "Long Task",
            "READY",
            content=long_content,
        )

        instruction = build_worker_instruction(f"tasks/{path.name}")

        assert "Business context" not in instruction
        assert len(instruction) < 500


# ---------------------------------------------------------------------------
# Worker adapter boundary
# ---------------------------------------------------------------------------


@dataclass
class FakeWorkerAdapter(WorkerAdapter):
    """Test-only worker adapter that records invocations and returns canned output."""

    name_value: str = "fake"
    return_success: bool = True
    return_message: str = "fake worker ran"
    recorded: list[tuple[str, Path]] | None = None

    @property
    def name(self) -> str:
        return self.name_value

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return ["fake-worker", instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        if self.recorded is None:
            self.recorded = []
        self.recorded.append((instruction, working_dir))
        return WorkerResult(
            success=self.return_success,
            command=self.build_command(instruction, working_dir),
            message=self.return_message,
        )


class TestWorkerAdapterBoundary:
    def test_dry_run_adapter_never_executes(self):
        adapter = DryRunWorkerAdapter()
        result = adapter.run("instruction", Path("/tmp"))

        assert result.success is True
        assert "not be launched" in result.message
        assert adapter.build_command("x", Path("/tmp")) == []

    def test_kimi_adapter_builds_safe_prompt_command(self):
        adapter = KimiWorkerAdapter()
        command = adapter.build_command("do work", Path("/tmp"))

        assert command == ["kimi", "--prompt", "do work"]
        assert "--auto" not in command
        assert "--yolo" not in command

    def test_fake_adapter_can_be_used_in_tests(self, tmp_path: Path):
        fake = FakeWorkerAdapter()
        result = fake.run("instruction", tmp_path)

        assert result.success is True
        assert fake.recorded == [("instruction", tmp_path)]

    def test_worker_failure_is_controlled(self, tmp_path: Path):
        fake = FakeWorkerAdapter(return_success=False, return_message="boom")
        result = fake.run("instruction", tmp_path)

        assert result.success is False
        assert result.message == "boom"

    def test_kimi_adapter_reports_missing_executable(self, tmp_path: Path):
        adapter = KimiWorkerAdapter(executable="definitely-not-kimi")
        result = adapter.run("instruction", tmp_path)

        assert result.success is False
        assert "not found in PATH" in result.message

    def test_kimi_adapter_prefers_path_executable(self, tmp_path: Path):
        adapter = KimiWorkerAdapter(implementation_worker=False)
        with patch(
            "advancore.agent_runner.worker.shutil.which", return_value="/bin/kimi"
        ), patch("advancore.agent_runner.worker._kimi_usage_preflight") as preflight, patch(
            "advancore.agent_runner.worker.subprocess.run"
        ) as launched:
            preflight.return_value = (None, None, None)
            launched.return_value = subprocess.CompletedProcess([], 0, "", "")
            result = adapter.run("instruction", tmp_path)

        assert result.success is True
        assert launched.call_args.args[0][0] == "/bin/kimi"

    def test_kimi_adapter_uses_fixed_owner_home_fallback(self, tmp_path: Path):
        owner_home = tmp_path / "owner"
        fixed_kimi = owner_home / ".kimi-code" / "bin" / "kimi"
        fixed_kimi.parent.mkdir(parents=True)
        fixed_kimi.write_text("#!/bin/sh\n", encoding="utf-8")
        fixed_kimi.chmod(0o700)
        adapter = KimiWorkerAdapter(implementation_worker=False)
        with patch(
            "advancore.agent_runner.worker.shutil.which", return_value=None
        ), patch(
            "advancore.agent_runner.worker.pwd.getpwuid",
            return_value=SimpleNamespace(pw_dir=str(owner_home)),
        ), patch("advancore.agent_runner.worker._kimi_usage_preflight") as preflight, patch(
            "advancore.agent_runner.worker.subprocess.run"
        ) as launched:
            preflight.return_value = (None, None, None)
            launched.return_value = subprocess.CompletedProcess([], 0, "", "")
            result = adapter.run("instruction", tmp_path)

        assert result.success is True
        assert launched.call_args.args[0][0] == str(fixed_kimi)

    def test_kimi_adapter_rejects_unsafe_fixed_fallback(self, tmp_path: Path):
        owner_home = tmp_path / "owner"
        fixed_kimi = owner_home / ".kimi-code" / "bin" / "kimi"
        fixed_kimi.parent.mkdir(parents=True)
        target = tmp_path / "other-kimi"
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(0o700)
        fixed_kimi.symlink_to(target)
        adapter = KimiWorkerAdapter()
        with patch(
            "advancore.agent_runner.worker.shutil.which", return_value=None
        ), patch(
            "advancore.agent_runner.worker.pwd.getpwuid",
            return_value=SimpleNamespace(pw_dir=str(owner_home)),
        ):
            result = adapter.run("instruction", tmp_path)

        assert result.success is False
        assert "not found in PATH" in result.message


# ---------------------------------------------------------------------------
# Runner plan / execute
# ---------------------------------------------------------------------------


def _patch_git_info(
    repo_root: Path,
    branch: str,
    clean: bool,
    head_sha: str = "pre000000000000000000000000000000000000",
):
    """Return a patch target that replaces ``get_git_info`` with a fake."""

    def _fake_get_git_info(cwd=None):
        return GitInfo(
            repo_root=repo_root,
            current_branch=branch,
            head_sha=head_sha,
            is_clean=clean,
            status_lines=[] if clean else ["?? some-file.py"],
        )

    return patch(
        "advancore.agent_runner.runner.get_git_info",
        side_effect=_fake_get_git_info,
    )


class TestRunnerPlan:
    def test_plan_succeeds_for_valid_ready_task(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "agent-control-foundation", True):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.PLANNING
        assert result.task.task_id == "TASK-001"
        assert result.validation.ok is True
        assert "Read AGENTS.md" in result.worker_instruction
        assert result.worker_command == []

    def test_plan_fails_on_main_branch(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "main", True):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.FAILED
        assert "main" in " ".join(result.messages)

    def test_plan_fails_on_dirty_tree(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "feature-branch", False):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.FAILED
        assert "uncommitted" in " ".join(result.messages)

    def test_plan_fails_for_non_ready_status(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Draft Task", "DRAFT")

        with _patch_git_info(repo_root, "feature-branch", True):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.FAILED
        assert "DRAFT" in " ".join(result.messages)

    def test_plan_does_not_launch_subprocess(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "feature-branch", True):
            with patch("advancore.agent_runner.worker.subprocess.run") as mock_run:
                result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.PLANNING
        mock_run.assert_not_called()

    def test_plan_does_not_run_git_mutation_commands(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with patch(
            "advancore.agent_runner.git_info.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=str(repo_root) + "\nagent-control-foundation\n",
                stderr="",
            )
            plan(tasks_dir, "TASK-001")

        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "reset" not in args
            assert "checkout" not in args
            assert "merge" not in args
            assert "push" not in args
            assert "commit" not in args


class TestRunnerExecute:
    def test_execute_with_fake_worker_awaits_approval(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        fake = FakeWorkerAdapter()

        with _patch_git_info(repo_root, "feature-branch", True):
            result = execute(tasks_dir, "TASK-001", worker=fake)

        assert result.status == RunnerStatus.AWAITING_APPROVAL
        assert fake.recorded
        assert "approval" in " ".join(result.messages).lower()

    def test_execute_with_failing_worker_reports_failure(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        fake = FakeWorkerAdapter(return_success=False, return_message="worker error")

        with _patch_git_info(repo_root, "feature-branch", True):
            result = execute(tasks_dir, "TASK-001", worker=fake)

        assert result.status == RunnerStatus.WORKER_FAILED
        assert "worker error" in " ".join(result.messages)

    def test_execute_does_not_launch_worker_when_validation_fails(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        fake = FakeWorkerAdapter()

        with _patch_git_info(repo_root, "main", True):
            result = execute(tasks_dir, "TASK-001", worker=fake)

        assert result.status == RunnerStatus.FAILED
        assert fake.recorded is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_plan_returns_zero_for_valid_task(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.runner.get_git_info",
            lambda cwd=None: GitInfo(
                repo_root=repo_root,
                current_branch="feature-branch",
                head_sha="abc1230000000000000000000000000000000000",
                is_clean=True,
                status_lines=[],
            ),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["plan", "TASK-001"])
        assert code == 0

    def test_cli_plan_returns_nonzero_for_failed_validation(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.runner.get_git_info",
            lambda cwd=None: GitInfo(
                repo_root=repo_root,
                current_branch="main",
                head_sha="def4560000000000000000000000000000000000",
                is_clean=True,
                status_lines=[],
            ),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["plan", "TASK-001"])
        assert code == 1


# ---------------------------------------------------------------------------
# Post-worker verification
# ---------------------------------------------------------------------------


def _git_info(
    repo_root: Path,
    branch: str = "agent-control-foundation",
    head_sha: str = "abc1230000000000000000000000000000000000",
    clean: bool = True,
    status_lines: list[str] | None = None,
) -> GitInfo:
    """Build a ``GitInfo`` snapshot for tests."""
    return GitInfo(
        repo_root=repo_root,
        current_branch=branch,
        head_sha=head_sha,
        is_clean=clean,
        status_lines=status_lines or [],
    )


def _sequence_git_info(*snapshots: GitInfo):
    """Return a callable that yields successive GitInfo snapshots on each call."""
    iterator = iter(snapshots)

    def _fake(cwd=None):
        return next(iterator)

    return _fake


def _patch_sequence_git_info(*snapshots: GitInfo):
    """Patch ``get_git_info`` to return *snapshots* in order."""
    return patch(
        "advancore.agent_runner.runner.get_git_info",
        side_effect=_sequence_git_info(*snapshots),
    )


class TestPostWorkerVerification:
    def test_passes_when_branch_and_head_unchanged(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        verification = verify_post_worker(pre, post)

        assert verification.ok is True
        assert "branch 'agent-control-foundation' unchanged" in verification.messages[0]
        assert "HEAD abc12300 unchanged" in verification.messages[1]
        assert verification.changed_paths == []

    def test_fails_on_head_movement(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")

        verification = verify_post_worker(pre, post)

        assert verification.ok is False
        assert "HEAD moved" in " ".join(verification.messages)

    def test_fails_on_branch_movement(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        pre = _git_info(repo_root, branch="feature-branch")
        post = _git_info(repo_root, branch="other-branch")

        verification = verify_post_worker(pre, post)

        assert verification.ok is False
        assert "branch changed" in " ".join(verification.messages)

    def test_fails_when_post_branch_is_main(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        pre = _git_info(repo_root, branch="feature-branch")
        post = _git_info(repo_root, branch="main")

        verification = verify_post_worker(pre, post)

        assert verification.ok is False
        assert "post-worker branch is 'main'" in " ".join(verification.messages)

    def test_surfaces_changed_paths(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M advancore/agent_runner/runner.py", "?? new-file.txt"],
        )

        verification = verify_post_worker(pre, post)

        assert verification.ok is True
        assert verification.changed_paths == [
            "advancore/agent_runner/runner.py",
            "new-file.txt",
        ]


class TestRunnerPostWorkerVerification:
    def test_execute_awaits_approval_with_changed_paths(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M changed.py"],
        )

        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.AWAITING_APPROVAL
        assert result.post_verification is not None
        assert result.post_verification.ok is True
        assert "changed.py" in result.post_verification.changed_paths
        assert any("PASS" in msg for msg in result.messages)

    def test_execute_blocks_approval_on_head_movement(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")

        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.POST_WORKER_VERIFICATION_FAILED
        assert result.post_verification.ok is False
        assert "Approval is blocked" in " ".join(result.messages)

    def test_execute_blocks_approval_on_branch_movement(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        pre = _git_info(repo_root, branch="feature-branch")
        post = _git_info(repo_root, branch="other-branch")

        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.POST_WORKER_VERIFICATION_FAILED
        assert result.post_verification.ok is False

    def test_worker_failure_is_distinct_from_verification_failure(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        # Worker succeeds, but repository verification fails.
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")
        fake = FakeWorkerAdapter(return_success=True)
        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-001", worker=fake)
        assert result.worker_result.success is True
        assert result.status == RunnerStatus.POST_WORKER_VERIFICATION_FAILED

        # Worker fails, but repository verification passes.
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        fake = FakeWorkerAdapter(return_success=False, return_message="worker error")
        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-001", worker=fake)
        assert result.worker_result.success is False
        assert result.status == RunnerStatus.WORKER_FAILED
        assert result.post_verification.ok is True


# ---------------------------------------------------------------------------
# Audit records
# ---------------------------------------------------------------------------


class TestAuditRecords:
    def _load_last_record(self, audit_path: Path) -> dict:
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lines[-1])

    def test_plan_writes_audit_record(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "feature-branch", True):
            result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.PLANNING
        assert result.audit_path is not None
        assert result.audit_path.exists()
        assert result.audit_write_ok is True
        record = self._load_last_record(result.audit_path)
        assert record["mode"] == "plan"
        assert record["task_id"] == "TASK-001"
        assert record["task_filename"] == "TASK-001-sample-task.md"
        assert record["final_status"] == "planning"
        assert record["worker_success"] is None
        assert record["post_verification_ok"] is None
        assert record["post_head"] is None

    def test_execute_writes_audit_record_with_post_verification(
        self, tmp_path: Path
    ):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M changed.py"],
        )

        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.AWAITING_APPROVAL
        assert result.audit_path is not None
        record = self._load_last_record(result.audit_path)
        assert record["mode"] == "execute"
        assert record["post_verification_ok"] is True
        assert record["worker_success"] is True
        assert record["changed_paths"] == ["changed.py"]
        assert record["pre_head"] == pre.head_sha
        assert record["post_head"] == post.head_sha

    def test_audit_record_contains_only_safe_fields(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(
            tasks_dir,
            "TASK-001",
            "Ready Task",
            "READY",
            content="Business secret: password=abc token=xyz",
        )

        with _patch_git_info(repo_root, "feature-branch", True):
            result = plan(tasks_dir, "TASK-001")

        record = self._load_last_record(result.audit_path)
        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "mode",
            "worker_type",
            "branch",
            "pre_head",
            "post_head",
            "pre_validation_ok",
            "worker_success",
            "post_verification_ok",
            "final_status",
            "changed_paths",
        }
        assert set(record.keys()) == expected_keys
        raw = json.dumps(record)
        assert "password" not in raw.lower()
        assert "token" not in raw.lower()
        assert "secret" not in raw.lower()
        assert "Business secret" not in raw

    def test_audit_write_failure_is_reported(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-001", "Ready Task", "READY")

        with _patch_git_info(repo_root, "feature-branch", True):
            with patch(
                "advancore.agent_runner.runner.write_audit_record"
            ) as mock_write:
                mock_write.side_effect = AuditWriteError("disk full")
                result = plan(tasks_dir, "TASK-001")

        assert result.status == RunnerStatus.PLANNING
        assert result.audit_write_ok is False
        assert "disk full" in " ".join(result.messages)

    def test_audit_payload_helper_returns_expected_shape(self):
        payload = build_audit_payload(
            task_id="TASK-001",
            task_filename="TASK-001.md",
            mode="execute",
            worker_type="dry-run",
            branch="feature",
            pre_head="pre",
            post_head="post",
            pre_validation_ok=True,
            worker_success=True,
            post_verification_ok=True,
            final_status="awaiting_approval",
            changed_paths=["a.py"],
        )
        assert payload["task_id"] == "TASK-001"
        assert payload["mode"] == "execute"
        assert payload["changed_paths"] == ["a.py"]
        assert "timestamp" in payload
