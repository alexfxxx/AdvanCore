"""Contract tests for persistent Kimi workspace readiness."""

from pathlib import Path
import os
import shutil
import signal
import subprocess

from advancore.agent_runner import persistent_worker_workspace as workspace_module
from advancore.agent_runner.persistent_worker_workspace import (
    WorkspaceReadinessReason,
    inspect_persistent_kimi_workspace,
)


def _run(cwd: Path, *arguments: str) -> None:
    subprocess.run(
        ["/usr/bin/git", *arguments],
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _repository_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _run(repository, "init", "-b", "projects-lifecycle-recovery")
    _run(repository, "config", "user.name", "Test Owner")
    _run(repository, "config", "user.email", "owner@example.invalid")
    _run(repository, "remote", "add", "origin", "https://example.invalid/owner/repo.git")
    (repository / "README.md").write_text("governed\n", encoding="utf-8")
    _run(repository, "add", "README.md")
    _run(repository, "commit", "-m", "initial")
    worker = tmp_path / "worker"
    _run(repository, "worktree", "add", "-b", "task-146-ready", str(worker))
    return repository, worker


def test_clean_linked_feature_worktree_is_ready(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)

    result = inspect_persistent_kimi_workspace(repository, worker)

    assert result.eligible is True
    assert result.reason == WorkspaceReadinessReason.READY
    assert result.branch == "task-146-ready"


def test_missing_symlink_and_same_workspace_fail_closed(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)
    missing = inspect_persistent_kimi_workspace(repository, tmp_path / "missing")
    assert missing.reason == WorkspaceReadinessReason.WORKSPACE_MISSING

    alias = tmp_path / "alias"
    alias.symlink_to(worker, target_is_directory=True)
    assert inspect_persistent_kimi_workspace(repository, alias).reason == (
        WorkspaceReadinessReason.WORKSPACE_UNSAFE
    )
    assert inspect_persistent_kimi_workspace(repository, repository).reason == (
        WorkspaceReadinessReason.WORKSPACE_UNSAFE
    )


def test_foreign_repository_fails_closed(tmp_path):
    repository, _ = _repository_with_worktree(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    _run(foreign, "init", "-b", "task-999-foreign")
    _run(foreign, "config", "user.name", "Test Owner")
    _run(foreign, "config", "user.email", "owner@example.invalid")
    _run(foreign, "remote", "add", "origin", "https://example.invalid/other/repo.git")
    (foreign / "README.md").write_text("foreign\n", encoding="utf-8")
    _run(foreign, "add", "README.md")
    _run(foreign, "commit", "-m", "initial")

    assert inspect_persistent_kimi_workspace(repository, foreign).reason == (
        WorkspaceReadinessReason.FOREIGN_REPOSITORY
    )


def test_dirty_base_and_detached_worktrees_fail_closed(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)
    (worker / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    dirty = inspect_persistent_kimi_workspace(repository, worker)
    assert dirty.reason == WorkspaceReadinessReason.DIRTY_WORKTREE

    (worker / "untracked.txt").unlink()
    _run(worker, "switch", "--detach")
    detached = inspect_persistent_kimi_workspace(repository, worker)
    assert detached.reason == WorkspaceReadinessReason.DETACHED_HEAD

    _run(worker, "switch", "projects-lifecycle-recovery", "--ignore-other-worktrees")
    base = inspect_persistent_kimi_workspace(repository, worker)
    assert base.reason == WorkspaceReadinessReason.UNSAFE_BRANCH


def test_result_exposes_no_path_remote_or_output(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)
    result = inspect_persistent_kimi_workspace(repository, worker)
    projection = repr(result)

    assert str(tmp_path) not in projection
    assert "example.invalid" not in projection
    assert "https://" not in projection


def test_nested_directory_is_not_accepted_as_worktree_root(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)
    nested = worker / "nested"
    nested.mkdir()

    assert inspect_persistent_kimi_workspace(repository, nested).reason == (
        WorkspaceReadinessReason.WORKSPACE_UNSAFE
    )


def test_state_change_after_first_clean_probe_fails_closed(tmp_path, monkeypatch):
    repository, worker = _repository_with_worktree(tmp_path)
    original_git = workspace_module._git
    status_calls = 0

    def changing_git(repo: Path, *arguments: str) -> str:
        nonlocal status_calls
        result = original_git(repo, *arguments)
        if arguments and arguments[0] == "status":
            status_calls += 1
            if status_calls == 1:
                (worker / "appeared-after-probe.txt").write_text(
                    "changed\n", encoding="utf-8"
                )
        return result

    monkeypatch.setattr(workspace_module, "_git", changing_git)
    result = inspect_persistent_kimi_workspace(repository, worker)

    assert result.reason == WorkspaceReadinessReason.DIRTY_WORKTREE


def test_git_probe_does_not_refresh_index_metadata(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)
    index = subprocess.run(
        ["/usr/bin/git", "rev-parse", "--git-path", "index"],
        cwd=worker,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    index_path = Path(index)
    if not index_path.is_absolute():
        index_path = worker / index_path
    before = index_path.stat().st_mtime_ns
    os.utime(worker / "README.md", None)

    assert inspect_persistent_kimi_workspace(repository, worker).eligible is True
    assert index_path.stat().st_mtime_ns == before


def test_large_status_output_fails_as_bounded_probe(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)
    for index in range(300):
        (worker / f"untracked-file-{index:04d}-with-long-name.txt").write_text(
            "x\n", encoding="utf-8"
        )

    result = inspect_persistent_kimi_workspace(repository, worker)

    assert result.reason == WorkspaceReadinessReason.GIT_PROBE_FAILED


def test_unregistered_worktree_copy_fails_closed(tmp_path):
    repository, worker = _repository_with_worktree(tmp_path)
    copied = tmp_path / "copied-worker"
    shutil.copytree(worker, copied)

    result = inspect_persistent_kimi_workspace(repository, copied)

    assert result.reason == WorkspaceReadinessReason.WORKSPACE_UNSAFE


def test_process_group_cleanup_checks_group_not_only_leader(monkeypatch):
    signals: list[int] = []
    times = iter([0.0, 0.3])

    class FinishedLeader:
        pid = 12345

        @staticmethod
        def wait(timeout):
            return 0

    monkeypatch.setattr(
        workspace_module.os,
        "killpg",
        lambda _group, sent_signal: signals.append(sent_signal),
    )
    monkeypatch.setattr(
        workspace_module,
        "_process_group_exists",
        lambda _group: True,
    )
    monkeypatch.setattr(
        workspace_module.time, "monotonic", lambda: next(times, 0.3)
    )

    workspace_module._terminate_process_group(FinishedLeader())

    assert signals == [signal.SIGTERM, signal.SIGKILL]
