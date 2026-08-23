"""Focused tests for the read-only orchestration exception inbox (TASK-027)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from advancore.agent_runner.__main__ import main
from advancore.agent_runner.git_info import get_git_info
from advancore.agent_runner.orchestration import (
    ORCHESTRATION_SCHEMA_VERSION,
    OrchestrationCheckpoint,
    OrchestrationPhase,
    OrchestrationStatus,
    default_orchestration_dir,
)
from advancore.agent_runner.orchestration_inbox import (
    INBOX_SCHEMA_VERSION,
    InboxClassification,
    build_orchestration_inbox,
    format_orchestration_inbox,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "feature/inbox-test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Inbox Test")
    (repo / ".gitignore").write_text(".agent_runner/\n", encoding="utf-8")
    (repo / "tasks").mkdir()
    (repo / "tasks" / "TASK-027-inbox.md").write_text(
        "# TASK-027 — Inbox test\n\nSTATUS: DRAFT\n", encoding="utf-8"
    )
    _git(repo, "add", ".gitignore", "tasks/TASK-027-inbox.md")
    _git(repo, "commit", "-m", "fixture")
    return repo


def _checkpoint(
    repo: Path,
    run_id: str,
    *,
    status: str = OrchestrationStatus.AWAITING_TASK_APPROVAL.value,
    phase: str = OrchestrationPhase.AWAITING_TASK_APPROVAL.value,
    updated_at: str | None = None,
) -> Path:
    git_info = get_git_info(repo)
    checkpoint = OrchestrationCheckpoint(
        schema_version=ORCHESTRATION_SCHEMA_VERSION,
        run_id=run_id,
        goal_hash="0" * 16,
        goal_summary="bounded fixture",
        planner="dry-run",
        worker="dry-run",
        controller="manual",
        repair_attempts=0,
        max_rework=0,
        apply=True,
        phase=phase,
        status=status,
        branch=git_info.current_branch,
        expected_head=git_info.head_sha,
        task_id="TASK-027",
        task_path=str(repo / "tasks" / "TASK-027-inbox.md"),
        task_written=True,
        updated_at=updated_at or datetime.now(timezone.utc).isoformat(),
    )
    path = default_orchestration_dir(repo) / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(checkpoint), sort_keys=True), encoding="utf-8")
    return path


def _snapshot(repo: Path) -> tuple[dict[str, bytes], str, str]:
    files = {
        str(path.relative_to(repo)): path.read_bytes()
        for path in sorted(repo.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    }
    return files, _git(repo, "rev-parse", "HEAD"), _git(repo, "status", "--porcelain")


def test_discovers_unresolved_without_run_id_and_formats_one_action(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _checkpoint(repo, "ORCH-owner")

    inbox = build_orchestration_inbox(repo)

    assert inbox.schema_version == INBOX_SCHEMA_VERSION
    assert len(inbox.entries) == 1
    entry = inbox.entries[0]
    assert entry.run_id == "ORCH-owner"
    assert entry.task_title == "Inbox test"
    assert entry.classification == InboxClassification.ACTION_REQUIRED.value
    assert entry.owner_decision_required is True
    assert entry.command.endswith("orchestrate --resume ORCH-owner")
    human = format_orchestration_inbox(inbox)
    assert human.count("Next:") == 1
    assert "--apply" not in human


def test_verified_published_is_excluded_but_incomplete_published_fails_closed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    verified_path = _checkpoint(
        repo,
        "ORCH-published",
        status=OrchestrationStatus.PUBLISHED.value,
        phase=OrchestrationPhase.PUBLISHED.value,
    )
    data = json.loads(verified_path.read_text(encoding="utf-8"))
    finalize_dir = repo / ".agent_runner" / "finalize"
    finalize_dir.mkdir(parents=True)
    finalization_artifact = finalize_dir / "result.json"
    finalization_artifact.write_text("{}", encoding="utf-8")
    data.update(
        push_verified=True,
        commit_sha=get_git_info(repo).head_sha,
        finalization_artifact_path=str(finalization_artifact),
        completed_phases=[OrchestrationPhase.FINALIZATION.value],
    )
    verified_path.write_text(json.dumps(data), encoding="utf-8")
    _checkpoint(
        repo,
        "ORCH-incomplete",
        status=OrchestrationStatus.PUBLISHED.value,
        phase=OrchestrationPhase.PUBLISHED.value,
    )

    inbox = build_orchestration_inbox(repo)

    assert [entry.run_id for entry in inbox.entries] == ["ORCH-incomplete"]
    assert inbox.entries[0].classification == "stale-or-invalid-evidence"


def test_malformed_missing_and_stale_evidence_surface_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    inbox_dir = default_orchestration_dir(repo)
    inbox_dir.mkdir(parents=True)
    (inbox_dir / "ORCH-bad.json").write_text("not-json", encoding="utf-8")
    stale = _checkpoint(repo, "ORCH-stale")
    data = json.loads(stale.read_text(encoding="utf-8"))
    data["review_bundle_path"] = ".agent_runner/review/missing.json"
    stale.write_text(json.dumps(data), encoding="utf-8")

    inbox = build_orchestration_inbox(repo)
    missing = build_orchestration_inbox(repo, run_id="ORCH-missing")

    assert {entry.run_id for entry in inbox.entries} == {"ORCH-bad", "ORCH-stale"}
    assert all(
        entry.classification == InboxClassification.STALE_OR_INVALID_EVIDENCE.value
        for entry in inbox.entries
    )
    assert missing.entries[0].reason == "checkpoint was not found"


def test_directory_and_symlink_artifact_references_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    directory = repo / ".agent_runner" / "review"
    directory.mkdir(parents=True)
    directory_checkpoint = _checkpoint(repo, "ORCH-directory")
    data = json.loads(directory_checkpoint.read_text(encoding="utf-8"))
    data["review_bundle_path"] = str(directory)
    directory_checkpoint.write_text(json.dumps(data), encoding="utf-8")

    target = directory / "target.json"
    target.write_text("{}", encoding="utf-8")
    symlink = directory / "linked.json"
    symlink.symlink_to(target)
    symlink_checkpoint = _checkpoint(repo, "ORCH-symlink")
    data = json.loads(symlink_checkpoint.read_text(encoding="utf-8"))
    data["review_bundle_path"] = str(symlink)
    symlink_checkpoint.write_text(json.dumps(data), encoding="utf-8")

    entries = {entry.run_id: entry for entry in build_orchestration_inbox(repo).entries}
    assert "not a regular file" in entries["ORCH-directory"].reason
    assert "symlink evidence is not accepted" in entries["ORCH-symlink"].reason


def test_order_and_json_schema_are_deterministic(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    now = datetime.now(timezone.utc)
    _checkpoint(repo, "ORCH-owner-z", updated_at=(now + timedelta(seconds=1)).isoformat())
    _checkpoint(repo, "ORCH-owner-a", updated_at=now.isoformat())
    _checkpoint(
        repo,
        "ORCH-failed",
        status=OrchestrationStatus.FAILED.value,
        phase=OrchestrationPhase.FAILED.value,
        updated_at=(now - timedelta(days=1)).isoformat(),
    )

    first = build_orchestration_inbox(repo)
    second = build_orchestration_inbox(repo)

    assert first.to_dict() == second.to_dict()
    assert [entry.run_id for entry in first.entries] == [
        "ORCH-owner-a",
        "ORCH-owner-z",
        "ORCH-failed",
    ]
    payload = first.to_dict()
    assert set(payload) == {"schema_version", "entries"}
    assert set(payload["entries"][0]) == {
        "run_id",
        "task_id",
        "task_title",
        "phase",
        "status",
        "classification",
        "reason",
        "evidence_references",
        "owner_decision_required",
        "command",
    }


def test_api_and_cli_are_byte_for_byte_read_only(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo = _repo(tmp_path)
    _checkpoint(repo, "ORCH-read-only")
    before = _snapshot(repo)

    build_orchestration_inbox(repo)
    monkeypatch.chdir(repo)
    assert main(["orchestration-inbox", "--json", "--run", "ORCH-read-only"]) == 0
    output = json.loads(capsys.readouterr().out)
    after = _snapshot(repo)

    assert output["schema_version"] == INBOX_SCHEMA_VERSION
    assert before == after
