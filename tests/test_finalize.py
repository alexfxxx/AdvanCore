"""Tests for controller-gated finalization and branch publication.

These tests verify that a separately valid controller ``APPROVE`` decision is
required before any lifecycle approval, staging, commit, or push; that evidence
is bound to the current task/branch/HEAD/change set; that exact path staging is
used; and that preview mode mutates nothing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner.audit import build_finalization_audit_payload
from advancore.agent_runner.controller_decision import (
    ActorRole,
    ControllerDecision,
    DecisionValue,
    build_controller_decision,
    default_decisions_dir,
    find_latest_decision,
    load_controller_decision,
    serialize_controller_decision,
    write_controller_decision,
)
from advancore.agent_runner.finalize import (
    FinalizationStatus,
    _build_commit_message,
    _extract_changed_paths,
    default_finalize_dir,
    format_finalization_result,
    run_finalization,
)
from advancore.agent_runner.review_bundle import ReviewBundle
from advancore.agent_runner.task import find_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command in *cwd* and return the completed process."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def _init_repo(repo_root: Path) -> None:
    """Initialize a Git repository with an initial commit on ``main``."""
    _run(["git", "init"], cwd=repo_root)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo_root)
    _run(["git", "config", "user.name", "Test User"], cwd=repo_root)
    gitignore = repo_root / ".gitignore"
    gitignore.write_text(".agent_runner/\n", encoding="utf-8")
    readme = repo_root / "README.md"
    readme.write_text("# repo\n", encoding="utf-8")
    _run(["git", "add", ".gitignore", "README.md"], cwd=repo_root)
    _run(["git", "commit", "-m", "init"], cwd=repo_root)


def _create_branch(repo_root: Path, branch: str) -> None:
    """Create and check out *branch* from the current HEAD."""
    _run(["git", "checkout", "-b", branch], cwd=repo_root)


def _write_task(
    tasks_dir: Path,
    task_id: str,
    title: str,
    status: str,
    filename: str | None = None,
) -> Path:
    """Write a minimal task file and return its path."""
    filename = filename or f"{task_id}-sample-task.md"
    path = tasks_dir / filename
    path.write_text(
        f"# {task_id} — {title}\n\nSTATUS: {status}\n\n## Objective\n\nDo the thing.\n",
        encoding="utf-8",
    )
    return path


def _make_bundle(
    *,
    task_id: str = "TASK-020",
    task_filename: str = "TASK-020-sample-task.md",
    branch: str = "feature",
    pre_head: str | None = None,
    post_head: str | None = None,
    changed_paths: list[str] | None = None,
) -> ReviewBundle:
    return ReviewBundle(
        timestamp="2026-08-21T00:00:00+00:00",
        task_id=task_id,
        task_filename=task_filename,
        previous_status="READY",
        current_status="READY",
        branch=branch,
        pre_head=pre_head or "pre000000000000000000000000000000000000",
        post_head=post_head or "post00000000000000000000000000000000000",
        runner_status="awaiting_approval",
        worker_type="kimi",
        worker_success=True,
        post_verification_ok=True,
        post_verification_messages=["PASS: branch unchanged"],
        changed_paths=changed_paths or ["advancore/agent_runner/finalize.py"],
        diff_summary={"total": 1, "counts": {"modified": 1}},
        audit_path=".agent_runner/audit/runner.jsonl",
        recommended_action="REVIEW",
        messages=["Worker completed."],
    )


def _make_decision(
    bundle_path: Path,
    bundle: ReviewBundle,
    *,
    decision: str = "APPROVE",
    actor_role: ActorRole = ActorRole.CONTROLLER,
    repo_root: Path | None = None,
) -> ControllerDecision:
    return build_controller_decision(
        bundle_path,
        bundle,
        decision=decision,
        actor_role=actor_role,
        repo_root=repo_root,
    )


def _current_head(repo_root: Path) -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    assert result.returncode == 0
    return result.stdout.strip()


def _setup_ready_repo(
    tmp_path: Path,
    *,
    branch: str = "feature",
    task_status: str = "READY",
    changed_paths: list[str] | None = None,
) -> tuple[Path, Path, Path, ReviewBundle, Path]:
    """Set up a ready-to-finalize repository and return relevant paths."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    _init_repo(repo_root)
    _create_branch(repo_root, branch)

    tasks_dir = repo_root / "tasks"
    tasks_dir.mkdir(parents=True)
    task_path = _write_task(tasks_dir, "TASK-020", "Finalize Task", task_status)
    _run(["git", "add", str(task_path.relative_to(repo_root))], cwd=repo_root)
    _run(["git", "commit", "-m", f"add {task_path.name}"], cwd=repo_root)

    review_dir = repo_root / ".agent_runner" / "review"
    review_dir.mkdir(parents=True)
    bundle_path = review_dir / "bundle.json"

    # Create the changed source files; these remain untracked/working-tree changes.
    changed = changed_paths or ["advancore/agent_runner/finalize.py"]
    for p in changed:
        target = repo_root / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# new\n", encoding="utf-8")

    post_head = _current_head(repo_root)

    bundle = _make_bundle(
        branch=branch,
        post_head=post_head,
        changed_paths=changed,
    )
    bundle_path.write_text(
        json.dumps(bundle.__dict__, default=str, sort_keys=True),
        encoding="utf-8",
    )

    return repo_root, tasks_dir, task_path, bundle, bundle_path


def _record_decision(
    bundle_path: Path,
    bundle: ReviewBundle,
    repo_root: Path,
    *,
    decision: str = "APPROVE",
    actor_role: ActorRole = ActorRole.CONTROLLER,
) -> Path:
    """Record a controller decision for *bundle* and return the path."""
    decision_record = _make_decision(
        bundle_path,
        bundle,
        decision=decision,
        actor_role=actor_role,
        repo_root=repo_root,
    )
    decisions_dir = default_decisions_dir(repo_root)
    decisions_dir.mkdir(parents=True, exist_ok=True)
    return write_controller_decision(decision_record, decisions_dir)


def _add_remote(repo_root: Path, branch: str) -> Path:
    """Create a bare upstream repo, add it as origin, and push the branch."""
    upstream = repo_root.parent / "origin.git"
    upstream.mkdir(parents=True)
    result = _run(["git", "init", "--bare"], cwd=upstream)
    assert result.returncode == 0, result.stderr
    result = _run(["git", "remote", "add", "origin", str(upstream)], cwd=repo_root)
    assert result.returncode == 0, result.stderr
    result = _run(["git", "push", "-u", "origin", branch], cwd=repo_root)
    assert result.returncode == 0, result.stderr
    result = _run(["git", "branch", "--set-upstream-to", f"origin/{branch}", branch], cwd=repo_root)
    assert result.returncode == 0, result.stderr
    return upstream


def _load_last_record(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_extract_changed_paths_strips_status_codes(self):
        lines = ["M  advancore/finalize.py", "?? tests/test_finalize.py"]
        assert _extract_changed_paths(lines) == [
            "advancore/finalize.py",
            "tests/test_finalize.py",
        ]

    def test_build_commit_message_uses_custom_when_safe(self):
        assert _build_commit_message("Title", "safe message") == "safe message"

    def test_build_commit_message_rejects_multiline_custom(self):
        assert _build_commit_message("Title", "line1\nline2") == "agent: Title"

    def test_build_commit_message_falls_back_to_task_title(self):
        assert _build_commit_message("My Task", None) == "agent: My Task"

    def test_build_commit_message_sanitizes_title(self):
        assert _build_commit_message("My $Task!", None) == "agent: My Task"


# ---------------------------------------------------------------------------
# Preview safety
# ---------------------------------------------------------------------------


class TestPreviewSafety:
    def test_preview_with_valid_evidence_reports_intended_actions(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is True
        assert result.status == FinalizationStatus.READY_TO_FINALIZE
        assert result.apply is False
        assert result.task_id == "TASK-020"
        assert result.lifecycle_states == ["READY", "IN_PROGRESS", "REVIEW", "APPROVED"]
        assert set(result.staged_paths) == {
            "advancore/agent_runner/finalize.py",
            "tasks/TASK-020-sample-task.md",
        }

    def test_preview_does_not_mutate_lifecycle_index_head_or_remote(
        self, tmp_path: Path
    ):
        repo_root, tasks_dir, task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        pre_head = _current_head(repo_root)
        pre_status = _run(["git", "status", "--porcelain"], cwd=repo_root).stdout
        pre_task_text = task_path.read_text(encoding="utf-8")

        run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert _current_head(repo_root) == pre_head
        assert _run(["git", "status", "--porcelain"], cwd=repo_root).stdout == pre_status
        assert task_path.read_text(encoding="utf-8") == pre_task_text


# ---------------------------------------------------------------------------
# Decision gates
# ---------------------------------------------------------------------------


class TestDecisionGates:
    def test_missing_decision_blocks_all_mutation(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        # No decision recorded.

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=tmp_path / "no-such-decision.json",
            apply=False,
        )

        assert result.ok is False
        assert result.status == FinalizationStatus.BLOCKED
        assert "cannot load controller decision" in " ".join(result.messages).lower()

    def test_worker_authored_approval_blocks_all_mutation(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        # Manually build a decision record with a worker actor to test finalizer
        # rejection (build_controller_decision itself rejects worker actors).
        decision = ControllerDecision(
            timestamp="2026-08-21T00:00:00+00:00",
            task_id=bundle.task_id,
            task_filename=bundle.task_filename,
            bundle_path=str(bundle_path),
            bundle_task_id=bundle.task_id,
            bundle_task_filename=bundle.task_filename,
            bundle_branch=bundle.branch,
            bundle_pre_head=bundle.pre_head or "",
            bundle_post_head=bundle.post_head,
            decision="APPROVE",
            actor_role="worker",
        )
        decisions_dir = default_decisions_dir(repo_root)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        decision_path = decisions_dir / "worker_decision.json"
        decision_path.write_text(
            json.dumps(serialize_controller_decision(decision), sort_keys=True),
            encoding="utf-8",
        )

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert "worker cannot act" in " ".join(result.messages).lower()

    @pytest.mark.parametrize("decision", ["REWORK", "BLOCKED"])
    def test_non_approve_decision_blocks_publication(
        self, tmp_path: Path, decision: str
    ):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(
            bundle_path, bundle, repo_root, decision=decision
        )

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert result.status == FinalizationStatus.DECISION_REJECTED
        assert "only APPROVE may finalize" in " ".join(result.messages)


# ---------------------------------------------------------------------------
# Evidence binding / staleness
# ---------------------------------------------------------------------------


class TestEvidenceBinding:
    def test_task_mismatch_blocks(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        bundle.task_id = "TASK-999"
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert "task id mismatch" in " ".join(result.messages).lower()

    def test_branch_mismatch_blocks(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        bundle.branch = "other-branch"
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert result.status == FinalizationStatus.STALE_EVIDENCE
        assert "branch mismatch" in " ".join(result.messages).lower()

    def test_head_mismatch_blocks(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        # Change HEAD after bundle post_head by amending the feature branch.
        dirty = repo_root / "advancore" / "agent_runner" / "finalize.py"
        dirty.write_text("# changed\n", encoding="utf-8")
        _run(["git", "add", "."], cwd=repo_root)
        _run(["git", "commit", "-m", "extra"], cwd=repo_root)
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert result.status == FinalizationStatus.STALE_EVIDENCE
        assert "head is stale" in " ".join(result.messages).lower()

    def test_changed_path_mismatch_blocks(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        # Add an extra file not in the approved scope.
        extra = repo_root / "extra.txt"
        extra.write_text("extra", encoding="utf-8")
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert result.status == FinalizationStatus.STALE_EVIDENCE
        assert "changed-path mismatch" in " ".join(result.messages).lower()

    def test_existing_staged_paths_at_start_block(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        _run(["git", "add", "advancore/agent_runner/finalize.py"], cwd=repo_root)
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert "existing staged paths" in " ".join(result.messages).lower()

    def test_main_branch_blocks(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, branch="main"
        )
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert "not permitted on the 'main' branch" in " ".join(result.messages)

    def test_no_changed_paths_blocks(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, changed_paths=[]
        )
        # Reset the changed file so there are truly no changes.
        target = repo_root / "advancore" / "agent_runner" / "finalize.py"
        target.unlink(missing_ok=True)
        _run(["git", "add", "-A"], cwd=repo_root)
        _run(["git", "commit", "-m", "remove"], cwd=repo_root)
        post_head = _current_head(repo_root)
        bundle.post_head = post_head
        bundle.changed_paths = []
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        assert result.ok is False
        assert "no verified changed paths" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# Lifecycle choreography
# ---------------------------------------------------------------------------


class TestLifecycleChoreography:
    def test_ready_task_transitions_through_all_states(self, tmp_path: Path):
        repo_root, tasks_dir, task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, task_status="READY"
        )
        _add_remote(repo_root, "feature")
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        if not result.ok:
            for m in result.messages:
                print("DEBUG:", m)

        assert result.ok is True
        assert result.lifecycle_states == ["READY", "IN_PROGRESS", "REVIEW", "APPROVED"]
        assert "STATUS: APPROVED" in task_path.read_text(encoding="utf-8")

    def test_in_progress_task_transitions_to_review_then_approved(
        self, tmp_path: Path
    ):
        repo_root, tasks_dir, task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, task_status="IN_PROGRESS"
        )
        _add_remote(repo_root, "feature")
        bundle.current_status = "IN_PROGRESS"
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.ok is True
        assert result.lifecycle_states == ["IN_PROGRESS", "REVIEW", "APPROVED"]
        assert "STATUS: APPROVED" in task_path.read_text(encoding="utf-8")

    def test_review_task_applies_controller_approval_only(self, tmp_path: Path):
        repo_root, tasks_dir, task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, task_status="REVIEW"
        )
        _add_remote(repo_root, "feature")
        bundle.current_status = "REVIEW"
        bundle_path.write_text(
            json.dumps(bundle.__dict__, default=str, sort_keys=True),
            encoding="utf-8",
        )
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.ok is True
        assert result.lifecycle_states == ["REVIEW", "APPROVED"]
        assert "STATUS: APPROVED" in task_path.read_text(encoding="utf-8")

    def test_ready_to_approved_does_not_skip_states(self, tmp_path: Path):
        repo_root, tasks_dir, task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, task_status="READY"
        )
        _add_remote(repo_root, "feature")
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        text = task_path.read_text(encoding="utf-8")
        # The lifecycle helper rewrites only the STATUS line, so we verify the
        # final state rather than intermediate file contents.
        assert "STATUS: APPROVED" in text


# ---------------------------------------------------------------------------
# Staging and commit integrity
# ---------------------------------------------------------------------------


class TestStagingAndCommit:
    def test_exact_explicit_git_add_is_used(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, changed_paths=["a.py", "b.py"]
        )
        (repo_root / "a.py").write_text("a", encoding="utf-8")
        (repo_root / "b.py").write_text("b", encoding="utf-8")
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        # Inspect the commit to confirm exactly the approved paths were added.
        diff = _run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=repo_root,
        )
        committed = set(diff.stdout.strip().splitlines())
        assert committed == {"a.py", "b.py", "tasks/TASK-020-sample-task.md"}

    def test_staged_path_mismatch_stops_before_commit(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, changed_paths=["a.py"]
        )
        (repo_root / "a.py").write_text("a", encoding="utf-8")
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        calls: list[int] = []

        def fake_staged_paths(cwd: Path) -> list[str]:
            calls.append(1)
            if len(calls) == 1:
                return []  # initial check passes
            return ["a.py", "b.py"]  # post-add check simulates an extra staged file

        with patch(
            "advancore.agent_runner.finalize._staged_paths", side_effect=fake_staged_paths
        ):
            result = run_finalization(
                repo_root=repo_root,
                tasks_dir=tasks_dir,
                task_id="TASK-020",
                decision_path=decision_path,
                apply=True,
            )

        assert result.ok is False
        assert "staged path mismatch" in " ".join(result.messages).lower()
        # No commit should have been created.
        assert _current_head(repo_root) == bundle.post_head

    def test_cached_diff_check_failure_stops_before_commit(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(
            tmp_path, changed_paths=["a.py"]
        )
        # Introduce trailing whitespace that git diff --check will reject.
        (repo_root / "a.py").write_text("a   \n", encoding="utf-8")
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.ok is False
        assert "whitespace errors" in " ".join(result.messages).lower()
        assert _current_head(repo_root) == bundle.post_head

    def test_commit_message_is_bounded(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            commit_message="controller: approved feature",
            apply=True,
        )

        log = _run(["git", "log", "-1", "--pretty=%B"], cwd=repo_root)
        assert log.stdout.strip() == "controller: approved feature"

    def test_exactly_one_commit_created_with_expected_parent(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")
        pre_head = _current_head(repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.commit_sha is not None
        parent = _run(["git", "rev-parse", f"{result.commit_sha}^"], cwd=repo_root)
        assert parent.stdout.strip() == pre_head

    def test_commit_contents_match_approved_paths(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        diff = _run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=repo_root,
        )
        committed = set(diff.stdout.strip().splitlines())
        assert committed == {
            "advancore/agent_runner/finalize.py",
            "tasks/TASK-020-sample-task.md",
        }

    def test_post_commit_dirty_tree_blocks_push(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        # Inject a post-commit dirty file by patching _porcelain_status so the
        # first two calls use real git status and the third (post-commit check)
        # reports an untracked file.
        from advancore.agent_runner import finalize as finalize_module

        original_porcelain = finalize_module._porcelain_status
        call_count: list[int] = []

        def dirty_after_commit(cwd: Path) -> list[str]:
            call_count.append(1)
            if len(call_count) <= 2:
                return original_porcelain(cwd)
            return ["?? dirty.txt"]

        with patch("advancore.agent_runner.finalize._porcelain_status", side_effect=dirty_after_commit):
            result = run_finalization(
                repo_root=repo_root,
                tasks_dir=tasks_dir,
                task_id="TASK-020",
                decision_path=decision_path,
                apply=True,
            )

        if result.status != FinalizationStatus.PUBLICATION_FAILED:
            for m in result.messages:
                print("DEBUG:", m)
        assert result.ok is False
        assert result.status == FinalizationStatus.PUBLICATION_FAILED
        assert "working tree is dirty after commit" in " ".join(result.messages).lower()


# ---------------------------------------------------------------------------
# Push restrictions
# ---------------------------------------------------------------------------


class TestPushRestrictions:
    def test_push_command_is_origin_current_branch(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.ok is True
        assert result.push_command == ["git", "push", "origin", "feature"]

    def test_successful_push_ends_synchronized_and_clean(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.ok is True
        assert result.status == FinalizationStatus.PUSHED
        local = _current_head(repo_root)
        remote = _run(["git", "rev-parse", "origin/feature"], cwd=repo_root)
        assert local == remote.stdout.strip()
        status = _run(["git", "status", "--porcelain"], cwd=repo_root)
        assert status.stdout.strip() == ""

    def test_force_push_flags_are_never_used(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        recorded: list[list[str]] = []
        original_run_git = None

        def capturing_run_git(args, cwd, *, check=False):
            recorded.append(args)
            return subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, check=check
            )

        with patch(
            "advancore.agent_runner.finalize._run_git", side_effect=capturing_run_git
        ):
            result = run_finalization(
                repo_root=repo_root,
                tasks_dir=tasks_dir,
                task_id="TASK-020",
                decision_path=decision_path,
                apply=True,
            )

        assert result.ok is True
        push_calls = [args for args in recorded if args[:2] == ["push", "origin"]]
        assert len(push_calls) == 1
        assert "--force" not in push_calls[0]
        assert "--force-with-lease" not in push_calls[0]
        assert "+" not in push_calls[0][-1]

    def test_upstream_mismatch_fails_closed(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")
        # Reset upstream to a different branch.
        _run(["git", "branch", "--unset-upstream", "feature"], cwd=repo_root)
        _run(["git", "branch", "--set-upstream-to=origin/main", "feature"], cwd=repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.ok is False
        assert "upstream mismatch" in " ".join(result.messages).lower()

    def test_publication_failure_reports_bounded_evidence(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        def failing_push(args, cwd, *, check=False):
            if args[:2] == ["push", "origin"]:
                return subprocess.CompletedProcess(
                    args=["git", *args],
                    returncode=1,
                    stdout="",
                    stderr="rejected: non-fast-forward",
                )
            return subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, check=check
            )

        with patch("advancore.agent_runner.finalize._run_git", side_effect=failing_push):
            result = run_finalization(
                repo_root=repo_root,
                tasks_dir=tasks_dir,
                task_id="TASK-020",
                decision_path=decision_path,
                apply=True,
            )

        assert result.ok is False
        assert result.status == FinalizationStatus.PUBLICATION_FAILED
        assert result.commit_sha is not None
        assert result.push_result is not None
        assert result.push_result["returncode"] == 1


# ---------------------------------------------------------------------------
# Audit and artifact
# ---------------------------------------------------------------------------


class TestAuditAndArtifact:
    def test_audit_payload_contains_safe_metadata(self):
        payload = build_finalization_audit_payload(
            task_id="TASK-020",
            task_filename="TASK-020.md",
            status="PUSHED",
            branch="feature",
            pre_head="pre",
            post_head="post",
            commit_sha="abc",
            decision_path=".agent_runner/decisions/d.json",
            bundle_path=".agent_runner/review/b.json",
            staged_paths=["a.py"],
            changed_paths=["a.py"],
            lifecycle_states=["READY", "APPROVED"],
            push_command=["git", "push", "origin", "feature"],
            push_result={"returncode": 0},
            messages=["ok"],
        )

        expected_keys = {
            "timestamp",
            "task_id",
            "task_filename",
            "status",
            "branch",
            "pre_head",
            "post_head",
            "commit_sha",
            "decision_path",
            "bundle_path",
            "staged_paths",
            "changed_paths",
            "lifecycle_states",
            "push_command",
            "push_result",
            "messages",
            "mode",
        }
        assert set(payload.keys()) == expected_keys
        assert payload["mode"] == "finalize"

    def test_finalize_writes_artifact_and_audit(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=True,
        )

        assert result.ok is True
        assert result.audit_path is not None
        assert result.audit_path.exists()

        artifact_path = default_finalize_dir(repo_root) / "finalize.jsonl"
        assert artifact_path.exists()
        record = _load_last_record(artifact_path)
        assert record["mode"] == "finalize"
        assert record["task_id"] == "TASK-020"
        assert record["status"] == "PUSHED"
        assert "transcript" not in str(record).lower()
        assert "password" not in str(record).lower()

    def test_format_finalization_result_is_human_readable(self, tmp_path: Path):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)

        result = run_finalization(
            repo_root=repo_root,
            tasks_dir=tasks_dir,
            task_id="TASK-020",
            decision_path=decision_path,
            apply=False,
        )

        summary = format_finalization_result(result)
        assert "Controller-Gated Finalization" in summary
        assert "READY_TO_FINALIZE" in summary
        assert "TASK-020" in summary


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestFinalizeCLI:
    def test_cli_preview_returns_zero_for_allowed(self, tmp_path: Path, monkeypatch):
        repo_root, tasks_dir, _task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        monkeypatch.chdir(repo_root)

        from advancore.agent_runner.__main__ import main

        code = main(
            [
                "finalize",
                "TASK-020",
                "--decision",
                str(decision_path),
            ]
        )
        assert code == 0

    def test_cli_apply_mutates_task_and_pushes(
        self, tmp_path: Path, monkeypatch
    ):
        repo_root, tasks_dir, task_path, bundle, bundle_path = _setup_ready_repo(tmp_path)
        decision_path = _record_decision(bundle_path, bundle, repo_root)
        _add_remote(repo_root, "feature")
        monkeypatch.chdir(repo_root)

        from advancore.agent_runner.__main__ import main

        code = main(
            [
                "finalize",
                "TASK-020",
                "--decision",
                str(decision_path),
                "--apply",
            ]
        )
        assert code == 0
        assert "STATUS: APPROVED" in task_path.read_text(encoding="utf-8")
        local = _current_head(repo_root)
        remote = _run(["git", "rev-parse", "origin/feature"], cwd=repo_root)
        assert local == remote.stdout.strip()


# ---------------------------------------------------------------------------
# Existing test regression guard
# ---------------------------------------------------------------------------


def test_finalize_import_does_not_break_existing_runner_imports():
    """Importing the package after TASK-020 should still succeed."""
    from advancore import agent_runner

    assert hasattr(agent_runner, "run_finalization")
    assert hasattr(agent_runner, "FinalizationStatus")
