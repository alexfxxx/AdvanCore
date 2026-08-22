"""Tests for the controller review bundle.

These tests are isolated from the real repository and Git state. They exercise
bundle construction, controller-action rules, safe-field policy, serialization,
inspection, and failure handling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner import (
    ControllerAction,
    DryRunWorkerAdapter,
    ReviewBundle,
    ReviewBundleError,
    ReviewBundleWriteError,
    WorkerAdapter,
    WorkerResult,
    build_review_bundle,
    execute,
    find_latest_bundle,
    format_bundle_summary,
    load_review_bundle,
    write_review_bundle,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.runner import RunnerResult, RunnerStatus
from advancore.agent_runner.task import Task


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


@dataclass
class FakeWorkerAdapter(WorkerAdapter):
    """Test-only worker adapter that returns canned output."""

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


# ---------------------------------------------------------------------------
# Controller action rules
# ---------------------------------------------------------------------------


class TestControllerActionRules:
    def test_worker_success_and_verification_pass_recommends_review(self):
        result = RunnerResult(
            status=RunnerStatus.AWAITING_APPROVAL,
            git_info=_git_info(Path("/tmp/repo")),
            worker_result=WorkerResult(success=True, message="ok"),
            post_verification=type(
                "PV", (), {"ok": True, "changed_paths": [], "messages": []}
            )(),
        )

        bundle = build_review_bundle(result)

        assert bundle.recommended_action == ControllerAction.REVIEW.value

    def test_worker_failure_with_safe_verification_recommends_rework(self):
        result = RunnerResult(
            status=RunnerStatus.WORKER_FAILED,
            git_info=_git_info(Path("/tmp/repo")),
            worker_result=WorkerResult(success=False, message="worker error"),
            post_verification=type(
                "PV", (), {"ok": True, "changed_paths": [], "messages": []}
            )(),
        )

        bundle = build_review_bundle(result)

        assert bundle.recommended_action == ControllerAction.REWORK.value

    def test_failed_verification_recommends_blocked(self):
        result = RunnerResult(
            status=RunnerStatus.POST_WORKER_VERIFICATION_FAILED,
            git_info=_git_info(Path("/tmp/repo")),
            worker_result=WorkerResult(success=True, message="ok"),
            post_verification=type(
                "PV", (), {"ok": False, "changed_paths": [], "messages": []}
            )(),
        )

        bundle = build_review_bundle(result)

        assert bundle.recommended_action == ControllerAction.BLOCKED.value

    def test_missing_post_verification_recommends_blocked(self):
        result = RunnerResult(
            status=RunnerStatus.WORKER_COMPLETED,
            git_info=_git_info(Path("/tmp/repo")),
            worker_result=WorkerResult(success=True, message="ok"),
            post_verification=None,
        )

        bundle = build_review_bundle(result)

        assert bundle.recommended_action == ControllerAction.BLOCKED.value

    def test_bundle_never_recommends_approved(self):
        for status in RunnerStatus:
            result = RunnerResult(
                status=status,
                git_info=_git_info(Path("/tmp/repo")),
                worker_result=WorkerResult(success=True, message="ok"),
                post_verification=type(
                    "PV", (), {"ok": True, "changed_paths": [], "messages": []}
                )(),
            )
            bundle = build_review_bundle(result)
            assert bundle.recommended_action != "APPROVED"


# ---------------------------------------------------------------------------
# Bundle contents and safe-field policy
# ---------------------------------------------------------------------------


class TestBundleContents:
    def test_safe_metadata_fields_are_present(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        task_path = _write_task(tasks_dir, "TASK-010", "Review Bundle", "READY")
        task = Task(
            task_id="TASK-010",
            title="Review Bundle",
            status="READY",
            filename=task_path.name,
            path=task_path,
        )
        git_info = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post_git_info = _git_info(
            repo_root,
            head_sha="post00000000000000000000000000000000000",
            clean=False,
            status_lines=[" M changed.py"],
        )
        result = RunnerResult(
            status=RunnerStatus.AWAITING_APPROVAL,
            task=task,
            git_info=git_info,
            pre_git_info=git_info,
            post_git_info=post_git_info,
            worker_type="fake",
            worker_result=WorkerResult(success=True, message="ok"),
            post_verification=type(
                "PV",
                (),
                {
                    "ok": True,
                    "changed_paths": ["changed.py"],
                    "messages": ["PASS: branch unchanged"],
                },
            )(),
            audit_path=repo_root / ".agent_runner" / "audit" / "runner.jsonl",
        )

        bundle = build_review_bundle(result)

        assert bundle.task_id == "TASK-010"
        assert bundle.task_filename == task_path.name
        assert bundle.current_status == "READY"
        assert bundle.branch == "agent-control-foundation"
        assert bundle.pre_head == git_info.head_sha
        assert bundle.post_head == post_git_info.head_sha
        assert bundle.runner_status == "awaiting_approval"
        assert bundle.worker_type == "fake"
        assert bundle.worker_success is True
        assert bundle.post_verification_ok is True
        assert bundle.changed_paths == ["changed.py"]
        assert bundle.audit_path == ".agent_runner/audit/runner.jsonl"
        assert bundle.recommended_action == ControllerAction.REVIEW.value

    def test_sensitive_and_full_content_fields_are_absent(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        task_path = _write_task(
            tasks_dir,
            "TASK-010",
            "Secret Task",
            "READY",
            content="Business secret: password=abc token=xyz",
        )
        task = Task(
            task_id="TASK-010",
            title="Secret Task",
            status="READY",
            filename=task_path.name,
            path=task_path,
        )
        git_info = _git_info(repo_root)
        result = RunnerResult(
            status=RunnerStatus.AWAITING_APPROVAL,
            task=task,
            git_info=git_info,
            pre_git_info=git_info,
            worker_type="fake",
            worker_result=WorkerResult(
                success=True,
                message="ok",
                stdout="password=abc",
                stderr="token=xyz",
            ),
            post_verification=type(
                "PV", (), {"ok": True, "changed_paths": [], "messages": []}
            )(),
        )

        bundle = build_review_bundle(result)
        payload = json.loads(json.dumps(bundle, default=str))
        raw = json.dumps(payload)

        assert "password" not in raw.lower()
        assert "token" not in raw.lower()
        assert "Business secret" not in raw
        assert "stdout" not in raw
        assert "stderr" not in raw
        assert "AGENTS.md" not in raw

    def test_changed_paths_match_runner_state(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        git_info = _git_info(repo_root)
        result = RunnerResult(
            status=RunnerStatus.AWAITING_APPROVAL,
            git_info=git_info,
            pre_git_info=git_info,
            worker_result=WorkerResult(success=True, message="ok"),
            post_verification=type(
                "PV",
                (),
                {
                    "ok": True,
                    "changed_paths": ["a.py", "b.py"],
                    "messages": [],
                },
            )(),
        )

        bundle = build_review_bundle(result)

        assert bundle.changed_paths == ["a.py", "b.py"]
        assert bundle.diff_summary["total"] == 2

    def test_audit_reference_present_when_available(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        git_info = _git_info(repo_root)
        result = RunnerResult(
            status=RunnerStatus.AWAITING_APPROVAL,
            git_info=git_info,
            pre_git_info=git_info,
            worker_result=WorkerResult(success=True, message="ok"),
            post_verification=type(
                "PV", (), {"ok": True, "changed_paths": [], "messages": []}
            )(),
            audit_path=repo_root / ".agent_runner" / "audit" / "runner.jsonl",
        )

        bundle = build_review_bundle(result)

        assert bundle.audit_path == ".agent_runner/audit/runner.jsonl"

    def test_audit_reference_absent_when_unavailable(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        git_info = _git_info(repo_root)
        result = RunnerResult(
            status=RunnerStatus.AWAITING_APPROVAL,
            git_info=git_info,
            pre_git_info=git_info,
            worker_result=WorkerResult(success=True, message="ok"),
            post_verification=type(
                "PV", (), {"ok": True, "changed_paths": [], "messages": []}
            )(),
        )

        bundle = build_review_bundle(result)

        assert bundle.audit_path is None


# ---------------------------------------------------------------------------
# Bundle serialization and persistence
# ---------------------------------------------------------------------------


class TestBundleSerialization:
    def test_write_and_load_roundtrip(self, tmp_path: Path):
        bundle = ReviewBundle(
            timestamp="2026-08-20T12:00:00+00:00",
            task_id="TASK-010",
            task_filename="TASK-010-review-bundle.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=["a.py"],
            recommended_action=ControllerAction.REVIEW.value,
        )

        path = write_review_bundle(bundle, tmp_path)

        assert path.exists()
        assert path.parent == tmp_path
        loaded = load_review_bundle(path)
        assert loaded.task_id == "TASK-010"
        assert loaded.recommended_action == ControllerAction.REVIEW.value

    def test_load_invalid_file_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        with pytest.raises(ReviewBundleError):
            load_review_bundle(path)

    def test_write_failure_is_reported(self, tmp_path: Path):
        bundle = ReviewBundle(
            timestamp="2026-08-20T12:00:00+00:00",
            task_id="TASK-010",
            task_filename="TASK-010-review-bundle.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=["a.py"],
            recommended_action=ControllerAction.REVIEW.value,
        )

        # Make the review "directory" a file so directory creation fails.
        review_dir = tmp_path / "not-a-dir"
        review_dir.write_text("I am a file, not a directory.", encoding="utf-8")

        with pytest.raises(ReviewBundleWriteError):
            write_review_bundle(bundle, review_dir)


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


class TestRunnerReviewBundleIntegration:
    def test_execute_creates_review_bundle_for_awaiting_approval(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-010", "Review Bundle", "READY")
        pre = _git_info(repo_root)
        post = _git_info(
            repo_root,
            clean=False,
            status_lines=[" M changed.py"],
        )

        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-010")

        assert result.status == RunnerStatus.AWAITING_APPROVAL
        assert result.review_bundle_path is not None
        assert result.review_bundle_path.exists()
        assert result.review_bundle_write_ok is True
        bundle = load_review_bundle(result.review_bundle_path)
        assert bundle.recommended_action == ControllerAction.REVIEW.value
        assert bundle.changed_paths == ["changed.py"]

    def test_execute_creates_rework_bundle_for_worker_failure(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-010", "Review Bundle", "READY")
        pre = _git_info(repo_root)
        post = _git_info(repo_root)
        fake = FakeWorkerAdapter(return_success=False, return_message="worker error")

        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-010", worker=fake)

        assert result.status == RunnerStatus.WORKER_FAILED
        assert result.review_bundle_path is not None
        bundle = load_review_bundle(result.review_bundle_path)
        assert bundle.recommended_action == ControllerAction.REWORK.value

    def test_execute_creates_blocked_bundle_for_failed_verification(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-010", "Review Bundle", "READY")
        pre = _git_info(repo_root, head_sha="pre000000000000000000000000000000000000")
        post = _git_info(repo_root, head_sha="post00000000000000000000000000000000000")

        with _patch_sequence_git_info(pre, post):
            result = execute(tasks_dir, "TASK-010")

        assert result.status == RunnerStatus.POST_WORKER_VERIFICATION_FAILED
        assert result.review_bundle_path is not None
        bundle = load_review_bundle(result.review_bundle_path)
        assert bundle.recommended_action == ControllerAction.BLOCKED.value

    def test_bundle_write_failure_is_reported(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        tasks_dir = repo_root / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, "TASK-010", "Review Bundle", "READY")
        pre = _git_info(repo_root)
        post = _git_info(repo_root)

        with _patch_sequence_git_info(pre, post):
            with patch(
                "advancore.agent_runner.runner.write_review_bundle"
            ) as mock_write:
                mock_write.side_effect = ReviewBundleWriteError("disk full")
                result = execute(tasks_dir, "TASK-010")

        assert result.status == RunnerStatus.AWAITING_APPROVAL
        assert result.review_bundle_write_ok is False
        assert "disk full" in " ".join(result.messages)


# ---------------------------------------------------------------------------
# CLI inspection
# ---------------------------------------------------------------------------


class TestReviewBundleCLI:
    def test_cli_show_bundle_by_path(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = ReviewBundle(
            timestamp="2026-08-20T12:00:00+00:00",
            task_id="TASK-010",
            task_filename="TASK-010-review-bundle.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=["a.py"],
            recommended_action=ControllerAction.REVIEW.value,
        )
        bundle_path = write_review_bundle(bundle, review_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["review-bundle", "show", str(bundle_path)])
        assert code == 0

    def test_cli_show_latest_bundle(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle1 = ReviewBundle(
            timestamp="2026-08-20T11:00:00+00:00",
            task_id="TASK-009",
            task_filename="TASK-009-old.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=[],
            recommended_action=ControllerAction.REVIEW.value,
        )
        bundle2 = ReviewBundle(
            timestamp="2026-08-20T12:00:00+00:00",
            task_id="TASK-010",
            task_filename="TASK-010-new.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=[],
            recommended_action=ControllerAction.REVIEW.value,
        )
        write_review_bundle(bundle1, review_dir)
        import time

        time.sleep(0.01)
        write_review_bundle(bundle2, review_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["review-bundle", "show"])
        assert code == 0

    def test_cli_show_does_not_mutate_git_state(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        review_dir = repo_root / ".agent_runner" / "review"
        review_dir.mkdir(parents=True)
        bundle = ReviewBundle(
            timestamp="2026-08-20T12:00:00+00:00",
            task_id="TASK-010",
            task_filename="TASK-010-review-bundle.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=[],
            recommended_action=ControllerAction.REVIEW.value,
        )
        bundle_path = write_review_bundle(bundle, review_dir)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        with patch("advancore.agent_runner.git_info.subprocess.run") as mock_run:
            code = main(["review-bundle", "show", str(bundle_path)])

        assert code == 0
        for call in mock_run.call_args_list:
            args = call.args[0]
            assert args[0] == "git"
            assert "commit" not in args
            assert "push" not in args
            assert "merge" not in args
            assert "reset" not in args
            assert "checkout" not in args

    def test_cli_show_missing_bundle_returns_nonzero(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True)

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(
            "advancore.agent_runner.__main__.get_git_info",
            lambda cwd=None: _git_info(repo_root),
        )

        from advancore.agent_runner.__main__ import main

        code = main(["review-bundle", "show", "missing.json"])
        assert code != 0


# ---------------------------------------------------------------------------
# Latest-bundle helper
# ---------------------------------------------------------------------------


class TestFindLatestBundle:
    def test_find_latest_bundle_returns_most_recent(self, tmp_path: Path):
        bundle1 = ReviewBundle(
            timestamp="2026-08-20T11:00:00+00:00",
            task_id="TASK-009",
            task_filename="TASK-009-old.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=[],
            recommended_action=ControllerAction.REVIEW.value,
        )
        bundle2 = ReviewBundle(
            timestamp="2026-08-20T12:00:00+00:00",
            task_id="TASK-010",
            task_filename="TASK-010-new.md",
            previous_status=None,
            current_status="READY",
            branch="feature-branch",
            pre_head="pre",
            post_head="post",
            runner_status="awaiting_approval",
            worker_type="fake",
            worker_success=True,
            post_verification_ok=True,
            changed_paths=[],
            recommended_action=ControllerAction.REVIEW.value,
        )
        path1 = write_review_bundle(bundle1, tmp_path)
        import time

        time.sleep(0.01)
        path2 = write_review_bundle(bundle2, tmp_path)

        latest = find_latest_bundle(tmp_path)

        assert latest == path2

    def test_find_latest_bundle_returns_none_when_empty(self, tmp_path: Path):
        assert find_latest_bundle(tmp_path) is None
