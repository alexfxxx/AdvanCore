"""Focused tests for the read-only orchestration exception inbox (TASK-027)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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


def _terminal_checkpoint(
    repo: Path,
    run_id: str = "ORCH-published",
    *,
    directory_reference: bool = False,
) -> dict[str, Path]:
    """Create the immutable publication chain used by TASK-029/030/031."""
    task_path = repo / "tasks" / "TASK-027-inbox.md"
    task_path.write_text(
        task_path.read_text(encoding="utf-8").replace("STATUS: DRAFT", "STATUS: APPROVED"),
        encoding="utf-8",
    )
    _git(repo, "add", str(task_path.relative_to(repo)))
    _git(repo, "commit", "-m", "approve fixture task")
    commit = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    bundle_path = repo / ".agent_runner" / "review" / "bundle.json"
    decision_path = repo / ".agent_runner" / "decisions" / "decision.json"
    finalize_dir = repo / ".agent_runner" / "finalize"
    finalize_path = finalize_dir / "finalize.jsonl"
    bundle_path.parent.mkdir(parents=True)
    decision_path.parent.mkdir(parents=True)
    finalize_dir.mkdir(parents=True)
    bundle = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": "TASK-027",
        "task_filename": task_path.name,
        "previous_status": "READY",
        "current_status": "APPROVED",
        "branch": branch,
        "pre_head": commit,
        "post_head": commit,
        "runner_status": "success",
        "worker_type": "dry-run",
        "worker_success": True,
        "post_verification_ok": True,
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    decision = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": "TASK-027",
        "task_filename": task_path.name,
        "bundle_path": str(bundle_path.relative_to(repo)),
        "bundle_task_id": "TASK-027",
        "bundle_task_filename": task_path.name,
        "bundle_branch": branch,
        "bundle_pre_head": commit,
        "bundle_post_head": commit,
        "decision": "APPROVE",
        "actor_role": "controller",
    }
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    finalization = {
        "mode": "finalize",
        "status": "PUSHED",
        "task_id": "TASK-027",
        "task_filename": task_path.name,
        "branch": branch,
        "pre_head": commit,
        "post_head": commit,
        "commit_sha": commit,
        "bundle_path": str(bundle_path.relative_to(repo)),
        "decision_path": str(decision_path.relative_to(repo)),
    }
    finalize_path.write_text(json.dumps(finalization) + "\n", encoding="utf-8")
    checkpoint_path = _checkpoint(
        repo,
        run_id,
        status=OrchestrationStatus.PUBLISHED.value,
        phase=OrchestrationPhase.PUBLISHED.value,
    )
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint.update(
        push_verified=True,
        commit_sha=commit,
        decision="APPROVE",
        review_bundle_path=str(bundle_path.relative_to(repo)),
        decision_path=str(decision_path.relative_to(repo)),
        finalization_artifact_path=str(
            (finalize_dir if directory_reference else finalize_path).relative_to(repo)
        ),
        completed_phases=[
            OrchestrationPhase.FINALIZATION.value,
        ],
    )
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    return {
        "checkpoint": checkpoint_path,
        "bundle": bundle_path,
        "decision": decision_path,
        "finalize": finalize_path,
    }


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


def test_task_029_historical_publication_ignores_later_head_and_fingerprint_changes(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _terminal_checkpoint(repo)
    (repo / "later.txt").write_text("later commit\n", encoding="utf-8")
    _git(repo, "add", "later.txt")
    _git(repo, "commit", "-m", "later feature-line work")
    (repo / "working.txt").write_text("uncommitted later work\n", encoding="utf-8")

    assert build_orchestration_inbox(repo).entries == ()


def test_task_030_directory_reference_and_task_031_later_tip_are_valid(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _terminal_checkpoint(repo, directory_reference=True)
    (repo / "later.txt").write_text("later synchronized-shape tip\n", encoding="utf-8")
    _git(repo, "add", "later.txt")
    _git(repo, "commit", "-m", "advance feature line")

    assert build_orchestration_inbox(repo).entries == ()


def test_incomplete_published_and_failed_runs_remain_visible(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _checkpoint(
        repo,
        "ORCH-incomplete",
        status=OrchestrationStatus.PUBLISHED.value,
        phase=OrchestrationPhase.PUBLISHED.value,
    )
    _checkpoint(
        repo,
        "ORCH-failed",
        status=OrchestrationStatus.FAILED.value,
        phase=OrchestrationPhase.FAILED.value,
    )

    inbox = build_orchestration_inbox(repo)

    assert {entry.run_id for entry in inbox.entries} == {
        "ORCH-incomplete",
        "ORCH-failed",
    }


@pytest.mark.parametrize(
    "case",
    [
        "missing-finalize",
        "malformed-jsonl",
        "no-match",
        "duplicate-match",
        "unsuccessful",
        "task-id",
        "task-filename",
        "branch",
        "commit",
        "bundle-ref",
        "decision-ref",
        "non-approve",
        "unauthorized-actor",
    ],
)
def test_terminal_evidence_conflicts_fail_closed(tmp_path: Path, case: str) -> None:
    repo = _repo(tmp_path)
    paths = _terminal_checkpoint(repo)
    checkpoint = json.loads(paths["checkpoint"].read_text(encoding="utf-8"))
    bundle = json.loads(paths["bundle"].read_text(encoding="utf-8"))
    decision = json.loads(paths["decision"].read_text(encoding="utf-8"))
    record = json.loads(paths["finalize"].read_text(encoding="utf-8"))

    if case == "missing-finalize":
        paths["finalize"].unlink()
    elif case == "malformed-jsonl":
        paths["finalize"].write_text("not-json\n", encoding="utf-8")
    elif case == "no-match":
        record["mode"] = "preview"
    elif case == "duplicate-match":
        paths["finalize"].write_text(
            json.dumps(record) + "\n" + json.dumps(record) + "\n", encoding="utf-8"
        )
    elif case == "unsuccessful":
        record["status"] = "PUBLICATION_FAILED"
    elif case == "task-id":
        record["task_id"] = "TASK-other"
    elif case == "task-filename":
        record["task_filename"] = "other.md"
    elif case == "branch":
        record["branch"] = "feature/other"
    elif case == "commit":
        record["commit_sha"] = "f" * 40
    elif case == "bundle-ref":
        record["bundle_path"] = ".agent_runner/review/other.json"
    elif case == "decision-ref":
        record["decision_path"] = ".agent_runner/decisions/other.json"
    elif case == "non-approve":
        decision["decision"] = "REWORK"
    elif case == "unauthorized-actor":
        decision["actor_role"] = "worker"

    if case not in {"missing-finalize", "malformed-jsonl", "duplicate-match"}:
        paths["finalize"].write_text(json.dumps(record) + "\n", encoding="utf-8")
    paths["checkpoint"].write_text(json.dumps(checkpoint), encoding="utf-8")
    paths["bundle"].write_text(json.dumps(bundle), encoding="utf-8")
    paths["decision"].write_text(json.dumps(decision), encoding="utf-8")

    entry = build_orchestration_inbox(repo).entries[0]
    assert entry.run_id == "ORCH-published"
    assert entry.classification == InboxClassification.STALE_OR_INVALID_EVIDENCE.value


def test_terminal_finalization_path_misuse_and_symlinks_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    paths = _terminal_checkpoint(repo)
    checkpoint = json.loads(paths["checkpoint"].read_text(encoding="utf-8"))
    paths["finalize"].unlink()
    (paths["finalize"].parent / "other.jsonl").write_text("{}\n", encoding="utf-8")
    checkpoint["finalization_artifact_path"] = str(paths["finalize"].parent.relative_to(repo))
    paths["checkpoint"].write_text(json.dumps(checkpoint), encoding="utf-8")
    assert build_orchestration_inbox(repo).entries

    target = repo / "finalize-target.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    paths["finalize"].symlink_to(target)
    assert build_orchestration_inbox(repo).entries

    paths["finalize"].unlink()
    paths["finalize"].mkdir()
    assert build_orchestration_inbox(repo).entries


@pytest.mark.parametrize("kind", ["task-status", "review-location", "decision-location"])
def test_terminal_authority_and_canonical_locations_fail_closed(
    tmp_path: Path, kind: str
) -> None:
    repo = _repo(tmp_path)
    paths = _terminal_checkpoint(repo)
    checkpoint = json.loads(paths["checkpoint"].read_text(encoding="utf-8"))
    if kind == "task-status":
        task_path = repo / "tasks" / "TASK-027-inbox.md"
        task_path.write_text(
            task_path.read_text(encoding="utf-8").replace("STATUS: APPROVED", "STATUS: REVIEW"),
            encoding="utf-8",
        )
    else:
        source = paths["bundle"] if kind == "review-location" else paths["decision"]
        copied = repo / f"noncanonical-{source.name}"
        copied.write_bytes(source.read_bytes())
        field = "review_bundle_path" if kind == "review-location" else "decision_path"
        checkpoint[field] = str(copied.relative_to(repo))
        paths["checkpoint"].write_text(json.dumps(checkpoint), encoding="utf-8")

    entry = build_orchestration_inbox(repo).entries[0]
    assert entry.run_id == "ORCH-published"
    assert entry.classification == InboxClassification.STALE_OR_INVALID_EVIDENCE.value


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


def test_unresolved_checkpoints_retain_head_and_path_fingerprint_freshness(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    head_path = _checkpoint(repo, "ORCH-head-stale")
    path_path = _checkpoint(repo, "ORCH-path-stale")
    path_data = json.loads(path_path.read_text(encoding="utf-8"))
    path_data["expected_head"] = None
    path_data["path_fingerprint"] = ["recorded.txt"]
    path_path.write_text(json.dumps(path_data), encoding="utf-8")
    (repo / "later.txt").write_text("later\n", encoding="utf-8")
    _git(repo, "add", "later.txt")
    _git(repo, "commit", "-m", "advance unresolved fixture")

    entries = {entry.run_id: entry for entry in build_orchestration_inbox(repo).entries}
    assert entries["ORCH-head-stale"].status == OrchestrationStatus.STALE_EVIDENCE.value
    assert "HEAD differs" in entries["ORCH-head-stale"].reason
    assert entries["ORCH-path-stale"].status == OrchestrationStatus.STALE_EVIDENCE.value
    assert "path fingerprint differs" in entries["ORCH-path-stale"].reason


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
