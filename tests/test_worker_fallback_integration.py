"""Operational integration validation for governed worker fallback (TASK-023).

These tests use temporary Git repositories and executable shell fixtures.  They
exercise the production worker adapters and their real subprocess argv without
contacting an AI provider or relying on a developer's installed worker CLIs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from advancore.agent_runner import (
    AutoPipelineStatus,
    CodexWorkerAdapter,
    KimiSwarmWorkerAdapter,
    ProviderFailure,
    build_worker_adapter,
    format_auto_pipeline_report,
    run_auto_pipeline,
)
from advancore.agent_runner.__main__ import main
from advancore.agent_runner.auto_pipeline import DiffCheckResult, PytestResult
from advancore.agent_runner.git_info import GitInfo


RAW_PRIMARY = "PRIMARY_RAW_TRANSCRIPT credential=primary-secret"
RAW_FALLBACK = "FALLBACK_RAW_TRANSCRIPT api_key=fallback-secret"


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )


def _write_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    tasks = repo / "tasks"
    fake_bin = tmp_path / "fake-bin"
    tasks.mkdir(parents=True)
    fake_bin.mkdir()
    (repo / ".gitignore").write_text(".agent_runner/\n", encoding="utf-8")
    (tasks / "TASK-023-fixture.md").write_text(
        "# TASK-023 — Fixture\n\n"
        "STATUS: READY\n\n"
        "## Allowed changed-file scope\n\n"
        "1. `only.py`\n",
        encoding="utf-8",
    )
    _run_git(repo, "init", "-b", "task-023-validation")
    _run_git(repo, "config", "user.name", "TASK-023 Test")
    _run_git(repo, "config", "user.email", "task-023@example.invalid")
    _run_git(repo, "add", ".gitignore", "tasks/TASK-023-fixture.md")
    _run_git(repo, "commit", "-m", "fixture")
    return repo, tasks, fake_bin


def _install_workers(fake_bin: Path) -> Path:
    real_git = Path(shutil.which("git") or "")
    assert real_git.is_file()
    os.symlink(real_git, fake_bin / "git")
    log = fake_bin.parent / "worker-invocations.log"
    git = str(real_git)
    _write_executable(
        fake_bin / "kimi",
        f'''printf 'kimi\\n' >> "$WORKER_LOG"
printf '%s\\n' "$*" > "$WORKER_LOG.kimi-argv"
case "${{PRIMARY_MODE:-availability}}" in
  availability) printf '%s\\n' '{RAW_PRIMARY} quota exhausted' >&2 ;;
  unknown) printf '%s\\n' 'unexpected worker crash {RAW_PRIMARY}' >&2 ;;
  worktree) printf 'changed\\n' > only.py ;;
  index) printf 'staged\\n' > only.py; "{git}" add only.py ;;
  branch) "{git}" switch -q -c worker-mutated-branch ;;
  head) printf 'committed\\n' > only.py; "{git}" add only.py; "{git}" commit -qm worker-mutation ;;
  remote) "{git}" remote add worker-added https://example.invalid/repo.git ;;
esac
exit 75
''',
    )
    _write_executable(
        fake_bin / "codex",
        f'''printf 'codex\\n' >> "$WORKER_LOG"
printf '%s\\n' "$*" > "$WORKER_LOG.codex-argv"
printf '%s\\n' '{RAW_FALLBACK}'
if [ "${{FALLBACK_MODE:-success}}" = failure ]; then
  printf '%s\\n' 'fallback quota exhausted' >&2
  exit 76
fi
exit 0
''',
    )
    return log


def _passing_pytest(repo: Path) -> PytestResult:
    return PytestResult(["pytest"], 0, "1 passed", "", 1, "1 passed")


def _passing_diff(repo: Path) -> DiffCheckResult:
    return DiffCheckResult([["git", "diff", "--check"]], [0], "", "")


def _run_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    primary_mode: str = "availability",
    fallback_mode: str = "success",
):
    repo, tasks, fake_bin = _repo(tmp_path)
    log = _install_workers(fake_bin)
    monkeypatch.setenv("PATH", str(fake_bin))
    monkeypatch.setenv("WORKER_LOG", str(log))
    monkeypatch.setenv("PRIMARY_MODE", primary_mode)
    monkeypatch.setenv("FALLBACK_MODE", fallback_mode)
    result = run_auto_pipeline(
        tasks,
        "TASK-023",
        worker=KimiSwarmWorkerAdapter(),
        fallback_worker=CodexWorkerAdapter(),
        pytest_runner=_passing_pytest,
        diff_check_runner=_passing_diff,
    )
    invocations = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return repo, result, invocations


def test_clean_availability_failure_uses_codex_once_then_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _, result, invocations = _run_pipeline(tmp_path, monkeypatch)

    assert invocations == ["kimi", "codex"]
    log = tmp_path / "worker-invocations.log"
    assert "--prompt Read AGENTS.md." in Path(f"{log}.kimi-argv").read_text()
    assert "--ask-for-approval never exec --ephemeral --sandbox workspace-write" in Path(
        f"{log}.codex-argv"
    ).read_text()
    assert result.status == AutoPipelineStatus.READY_FOR_APPROVAL
    assert result.pytest_result and result.pytest_result.ok
    assert result.diff_check_result and result.diff_check_result.ok
    assert result.scope_result and result.scope_result.ok
    assert result.fallback_attempt
    assert result.fallback_attempt.failure == ProviderFailure.QUOTA_OR_CAPACITY
    assert result.fallback_attempt.integrity_ok
    assert result.primary_worker == "kimi-swarm"
    assert result.fallback_worker == result.terminal_worker == "codex"


@pytest.mark.parametrize("primary_mode", ["unknown", "worktree", "index", "branch", "head", "remote"])
def test_unknown_or_git_mutation_stops_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, primary_mode: str
):
    _, result, invocations = _run_pipeline(
        tmp_path, monkeypatch, primary_mode=primary_mode
    )

    assert invocations == ["kimi"]
    assert result.status in {
        AutoPipelineStatus.WORKER_FAILED,
        AutoPipelineStatus.POST_WORKER_VERIFICATION_FAILED,
    }
    assert result.fallback_attempt
    if primary_mode == "unknown":
        assert result.fallback_attempt.failure == ProviderFailure.UNKNOWN
    else:
        assert not result.fallback_attempt.integrity_ok
    assert result.terminal_worker == "kimi-swarm"


def test_failed_fallback_is_terminal_and_never_chains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _, result, invocations = _run_pipeline(
        tmp_path, monkeypatch, fallback_mode="failure"
    )

    assert invocations == ["kimi", "codex"]
    assert result.status == AutoPipelineStatus.WORKER_FAILED
    assert result.terminal_worker == "codex"
    assert result.fallback_attempt and result.fallback_attempt.terminal_worker == "codex"


def test_cli_default_has_no_fallback_and_invalid_policies_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    repo, _, _ = _repo(tmp_path)
    git_info = GitInfo(
        repo,
        "task-023-validation",
        _run_git(repo, "rev-parse", "HEAD").stdout.strip(),
        True,
        [],
    )
    captured: list[tuple[str, str | None]] = []

    def fake_pipeline(tasks_dir, task_id, worker, **kwargs):
        fallback = kwargs.get("fallback_worker")
        captured.append((worker.name, getattr(fallback, "name", None)))
        from advancore.agent_runner.auto_pipeline import AutoPipelineResult

        return AutoPipelineResult(status=AutoPipelineStatus.WORKER_FAILED)

    with patch("advancore.agent_runner.__main__.get_git_info", return_value=git_info), patch(
        "advancore.agent_runner.__main__.run_auto_pipeline", side_effect=fake_pipeline
    ):
        assert main(["auto", "TASK-023", "--worker", "kimi-swarm"]) == 1
        assert captured == [("kimi-swarm", None)]
        for args in (
            ["auto", "TASK-023", "--worker", "kimi", "--fallback-worker", "kimi"],
            ["auto", "TASK-023", "--worker", "kimi", "--fallback-worker", "dry-run"],
            ["auto", "TASK-023", "--worker", "dry-run", "--fallback-worker", "codex"],
        ):
            assert main(args) == 1
    assert len(captured) == 1
    assert "FAIL:" in capsys.readouterr().err


def test_report_and_persisted_evidence_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, result, _ = _run_pipeline(tmp_path, monkeypatch)
    report = format_auto_pipeline_report(result)
    artifact = json.loads(result.auto_artifact_path.read_text(encoding="utf-8"))

    for expected in ("kimi-swarm", "QUOTA_OR_CAPACITY", "codex"):
        assert expected in report
        assert expected in json.dumps(artifact)
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (repo / ".agent_runner").rglob("*")
        if path.is_file()
    )
    for forbidden in (RAW_PRIMARY, RAW_FALLBACK, "primary-secret", "fallback-secret"):
        assert forbidden not in report
        assert forbidden not in persisted


def test_registered_worker_policy_rejects_unknown_duplicate_and_dry_run():
    with pytest.raises(Exception):
        build_worker_adapter("unregistered-worker")
    from advancore.agent_runner import validate_worker_policy

    unsafe_policies = (
        ("kimi", "kimi"),
        ("kimi", "dry-run"),
        ("dry-run", "codex"),
    )
    for primary, fallback in unsafe_policies:
        with pytest.raises(Exception):
            validate_worker_policy(primary, fallback)
