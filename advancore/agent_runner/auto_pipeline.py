"""Governed automatic development pipeline for the local agent runner.

The auto pipeline orchestrates validation, worker execution, review-bundle
generation, full pytest, whitespace diff-check, and exact changed-file scope
verification in a single command. It stops before any staging, commit, push,
merge, or lifecycle approval action and reports ``READY_FOR_APPROVAL`` only
when every gate passes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.git_info import GitInfo
from advancore.agent_runner.runner import RunnerResult, RunnerStatus, execute
from advancore.agent_runner.task import Task, TaskError, find_task
from advancore.agent_runner.validation import ValidationResult, validate
from advancore.agent_runner.worker import WorkerAdapter

if TYPE_CHECKING:
    from advancore.agent_runner.review_bundle import ReviewBundle


class AutoPipelineStatus(str, Enum):
    """Terminal status of an automatic pipeline run."""

    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    WORKER_FAILED = "WORKER_FAILED"
    POST_WORKER_VERIFICATION_FAILED = "POST_WORKER_VERIFICATION_FAILED"
    TEST_FAILED = "TEST_FAILED"
    DIFF_CHECK_FAILED = "DIFF_CHECK_FAILED"
    SCOPE_FAILED = "SCOPE_FAILED"
    ARTIFACT_FAILED = "ARTIFACT_FAILED"


@dataclass
class PytestResult:
    """Result of running the repository pytest suite."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    passed_count: int | None
    summary: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class DiffCheckResult:
    """Result of running whitespace diff checks."""

    commands: list[list[str]]
    returncodes: list[int]
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return all(rc == 0 for rc in self.returncodes)


@dataclass
class ScopeResult:
    """Result of comparing actual changed paths to the allowed scope."""

    allowed_paths: list[str]
    actual_paths: list[str]
    out_of_scope_paths: list[str]
    unsafe_allowed_paths: list[str]
    missing_scope: bool
    ok: bool
    messages: list[str] = field(default_factory=list)


@dataclass
class AutoPipelineResult:
    """Complete result of an automatic pipeline invocation."""

    status: AutoPipelineStatus
    task: Task | None = None
    git_info: GitInfo | None = None
    pre_git_info: GitInfo | None = None
    post_git_info: GitInfo | None = None
    validation: ValidationResult | None = None
    allowed_paths: list[str] | None = None
    worker_type: str | None = None
    worker_result: "WorkerResult | None" = None
    post_verification: "PostWorkerVerification | None" = None
    pytest_result: PytestResult | None = None
    diff_check_result: DiffCheckResult | None = None
    scope_result: ScopeResult | None = None
    review_bundle_path: Path | None = None
    audit_path: Path | None = None
    audit_write_ok: bool = True
    audit_write_error: str | None = None
    auto_artifact_path: Path | None = None
    auto_artifact_write_ok: bool = True
    auto_artifact_write_error: str | None = None
    staged_paths: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.status == AutoPipelineStatus.READY_FOR_APPROVAL


# ---------------------------------------------------------------------------
# Safe subprocess helpers
# ---------------------------------------------------------------------------


def _run(
    args: list[str],
    cwd: Path,
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run *args* in *cwd* and return the completed process."""
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _repo_relative(path: str, repo_root: Path) -> str:
    """Return a normalized repository-relative path or raise ValueError."""
    p = Path(path)
    if p.is_absolute():
        p = p.relative_to(repo_root)
    normalized = p.as_posix()
    if normalized.startswith("..") or "/../" in normalized or "\\.." in normalized:
        raise ValueError(f"path escapes repository: {path}")
    return normalized


# ---------------------------------------------------------------------------
# Scope parsing and validation
# ---------------------------------------------------------------------------

# Section heading that declares the files a worker is permitted to modify.
_ALLOWED_SCOPE_HEADING_RE = re.compile(
    r"^##\s+Allowed changed-file scope\s*$", re.IGNORECASE
)

# Match a backtick-quoted path.
_ALLOWED_SCOPE_PATH_RE = re.compile(r"`([^`\n]+)`")


def parse_task_allowed_scope(path: Path) -> list[str] | None:
    """Extract the allowed changed-file scope from a task file.

    The scope is declared under an ``## Allowed changed-file scope`` heading.
    Paths are expected to be backtick-quoted and repository-relative. Returns
    ``None`` if the section is missing. Returns an empty list only if the
    section is present but contains no parseable paths.

    Raises:
        OSError: if the file cannot be read.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    scope: list[str] = []

    for line in lines:
        if _ALLOWED_SCOPE_HEADING_RE.match(line):
            in_section = True
            continue

        if in_section:
            # Stop at the next section heading of the same or higher level.
            if line.startswith("##"):
                break
            for match in _ALLOWED_SCOPE_PATH_RE.finditer(line):
                scope.append(match.group(1).strip())

    if not in_section:
        return None
    return scope


def _is_path_safe(path: str) -> bool:
    """Return True if *path* is a relative, non-escaping repository path."""
    if not path or not path.strip():
        return False
    stripped = path.strip()
    if stripped.startswith("/") or stripped.startswith("\\"):
        return False
    if ".." in stripped.split("/") or ".." in stripped.split("\\"):
        return False
    if stripped.startswith("~"):
        return False
    return True


def _normalize_scope_path(path: str) -> str:
    """Return a normalized scope path or raise ValueError."""
    stripped = path.strip()
    if not stripped:
        raise ValueError("empty path")
    # Reject absolute paths and parent-directory escapes before normalization.
    if stripped.startswith("/") or stripped.startswith("\\"):
        raise ValueError(f"absolute path: {path}")
    parts = stripped.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(f"path escapes repository: {path}")
    # Strip a leading "./" convenience prefix only.
    if parts and parts[0] == ".":
        parts = parts[1:]
    normalized = "/".join(parts)
    if not normalized:
        raise ValueError("empty path")
    return normalized


def _validate_allowed_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Split *paths* into safe normalized paths and unsafe raw paths."""
    safe: list[str] = []
    unsafe: list[str] = []
    for raw in paths:
        try:
            safe.append(_normalize_scope_path(raw))
        except ValueError:
            unsafe.append(raw)
    return safe, unsafe


def build_scope_result(
    allowed_paths: list[str] | None,
    actual_paths: list[str],
    require_scope: bool = True,
) -> ScopeResult:
    """Compare *actual_paths* against *allowed_paths* and return a ScopeResult.

    The comparison is fail-closed: missing scope (when required), unsafe
    allowed paths, or any actual path not in the allowed set causes failure.
    When *require_scope* is False and no scope is provided, scope validation
    is skipped and the result is considered passing.
    """
    messages: list[str] = []

    if allowed_paths is None:
        if require_scope:
            messages.append("FAIL: allowed changed-file scope is missing")
            return ScopeResult(
                allowed_paths=[],
                actual_paths=list(actual_paths),
                out_of_scope_paths=list(actual_paths),
                unsafe_allowed_paths=[],
                missing_scope=True,
                ok=False,
                messages=messages,
            )
        # Scope enforcement is disabled; accept all changes.
        normalized_actual = []
        for p in actual_paths:
            try:
                normalized_actual.append(_normalize_scope_path(p))
            except ValueError:
                normalized_actual.append(p)
        messages.append("PASS: scope enforcement disabled; changes accepted")
        return ScopeResult(
            allowed_paths=[],
            actual_paths=normalized_actual,
            out_of_scope_paths=[],
            unsafe_allowed_paths=[],
            missing_scope=False,
            ok=True,
            messages=messages,
        )

    safe_allowed, unsafe_allowed = _validate_allowed_paths(allowed_paths)
    normalized_actual = []
    for p in actual_paths:
        try:
            normalized_actual.append(_normalize_scope_path(p))
        except ValueError:
            normalized_actual.append(p)

    out_of_scope = [
        p for p in normalized_actual if p not in set(safe_allowed)
    ]

    ok = True
    if unsafe_allowed:
        messages.append(
            f"FAIL: {len(unsafe_allowed)} allowed scope path(s) are unsafe: "
            f"{unsafe_allowed}"
        )
        ok = False
    if out_of_scope:
        messages.append(
            f"FAIL: {len(out_of_scope)} changed path(s) exceed allowed scope: "
            f"{out_of_scope}"
        )
        ok = False
    if ok:
        if normalized_actual:
            messages.append(
                f"PASS: all {len(normalized_actual)} changed path(s) are within scope"
            )
        else:
            messages.append("PASS: no changed paths; scope is vacuously satisfied")

    return ScopeResult(
        allowed_paths=safe_allowed,
        actual_paths=normalized_actual,
        out_of_scope_paths=out_of_scope,
        unsafe_allowed_paths=unsafe_allowed,
        missing_scope=False,
        ok=ok,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# Pytest and diff-check runners
# ---------------------------------------------------------------------------


_PASSED_RE = re.compile(r"(\d+)\s+passed")
_SUMMARY_RE = re.compile(r"=+\s+([\w\s,]+)\s+=+")


def default_pytest_command(repo_root: Path) -> list[str]:
    """Return the default pytest command for *repo_root*."""
    python = shutil.which("python") or "python"
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        python = str(venv_python)
    return [python, "-m", "pytest", "tests/", "-v"]


def run_pytest(
    repo_root: Path,
    command: list[str] | None = None,
) -> PytestResult:
    """Run pytest in *repo_root* and return a PytestResult."""
    cmd = command if command is not None else default_pytest_command(repo_root)
    result = _run(cmd, cwd=repo_root)

    passed_count: int | None = None
    summary = ""
    if result.stdout:
        for line in reversed(result.stdout.splitlines()):
            match = _PASSED_RE.search(line)
            if match:
                passed_count = int(match.group(1))
            summary_match = _SUMMARY_RE.search(line)
            if summary_match:
                summary = summary_match.group(1).strip()
                break
    if not summary and result.stdout:
        summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""

    return PytestResult(
        command=cmd,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        passed_count=passed_count,
        summary=summary,
    )


def run_git_diff_check(repo_root: Path) -> DiffCheckResult:
    """Run whitespace checks on unstaged and staged changes.

    This covers the semantics of ``git diff --check`` for both the working
    tree and the index, without staging anything itself.
    """
    commands: list[list[str]] = [
        ["git", "diff", "--check"],
        ["git", "diff", "--cached", "--check"],
    ]
    returncodes: list[int] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    for cmd in commands:
        result = _run(cmd, cwd=repo_root)
        returncodes.append(result.returncode)
        if result.stdout:
            stdout_parts.append(result.stdout)
        if result.stderr:
            stderr_parts.append(result.stderr)

    return DiffCheckResult(
        commands=commands,
        returncodes=returncodes,
        stdout="\n".join(stdout_parts),
        stderr="\n".join(stderr_parts),
    )


def detect_staged_paths(repo_root: Path) -> list[str]:
    """Return repository-relative paths of staged changes, if any."""
    result = _run(["git", "diff", "--cached", "--name-only"], cwd=repo_root)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Auto artifact and audit
# ---------------------------------------------------------------------------


AUTO_SUBDIR = "auto"
AUTO_ARTIFACT_FILENAME = "auto_pipeline.jsonl"


def default_auto_dir(repo_root: Path) -> Path:
    """Return the default auto-pipeline artifact directory for *repo_root*."""
    return repo_root / ".agent_runner" / AUTO_SUBDIR


def build_auto_artifact_payload(result: AutoPipelineResult) -> dict[str, Any]:
    """Return a safe JSON-serializable payload for the auto pipeline artifact."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": result.task.task_id if result.task else None,
        "task_filename": result.task.filename if result.task else None,
        "status": result.status.value,
        "branch": result.git_info.current_branch if result.git_info else None,
        "pre_head": result.pre_git_info.head_sha if result.pre_git_info else None,
        "post_head": result.post_git_info.head_sha if result.post_git_info else None,
        "worker_type": result.worker_type,
        "worker_success": result.worker_result.success if result.worker_result else None,
        "review_bundle_path": str(result.review_bundle_path)
        if result.review_bundle_path
        else None,
        "pytest_command": result.pytest_result.command if result.pytest_result else None,
        "pytest_returncode": result.pytest_result.returncode if result.pytest_result else None,
        "pytest_passed_count": result.pytest_result.passed_count if result.pytest_result else None,
        "diff_check_ok": result.diff_check_result.ok if result.diff_check_result else None,
        "allowed_paths": result.scope_result.allowed_paths if result.scope_result else None,
        "actual_paths": result.scope_result.actual_paths if result.scope_result else None,
        "scope_ok": result.scope_result.ok if result.scope_result else None,
        "staged_paths": result.staged_paths,
        "working_tree_clean": result.post_git_info.is_clean if result.post_git_info else None,
        "no_publication_performed": True,
        "recommended_action": "controller/owner review",
        "messages": list(result.messages or []),
    }


class AutoArtifactWriteError(Exception):
    """Raised when an auto-pipeline artifact cannot be written durably."""


def write_auto_artifact(
    payload: dict[str, Any],
    auto_dir: Path,
) -> Path:
    """Append *payload* as one JSON Lines record under *auto_dir*.

    Raises:
        AutoArtifactWriteError: if the artifact cannot be written.
    """
    try:
        auto_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise AutoArtifactWriteError(
            f"Failed to create auto pipeline directory {auto_dir}: {exc}"
        ) from exc

    path = auto_dir / AUTO_ARTIFACT_FILENAME
    line = json.dumps(payload, separators=(",", ":"), default=str, sort_keys=True) + "\n"

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        raise AutoArtifactWriteError(
            f"Failed to write auto pipeline artifact to {path}: {exc}"
        ) from exc

    return path


# ---------------------------------------------------------------------------
# Consolidated report formatting
# ---------------------------------------------------------------------------


def format_auto_pipeline_report(result: AutoPipelineResult) -> str:
    """Return a controller-ready consolidated report for *result*."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("AdvanCore Governed Auto-Pipeline — Consolidated Approval Report")
    lines.append("=" * 72)

    if result.task:
        lines.append(f"Task:              {result.task.task_id}")
        lines.append(f"Title:             {result.task.title}")
        lines.append(f"Task file:         tasks/{result.task.filename}")
    else:
        lines.append("Task:              n/a")

    git_info = result.git_info
    if git_info:
        lines.append(f"Branch:            {git_info.current_branch}")
    if result.pre_git_info:
        lines.append(f"Pre HEAD:          {result.pre_git_info.head_sha}")
    if result.post_git_info:
        lines.append(f"Post HEAD:         {result.post_git_info.head_sha}")

    lines.append(f"Worker type:       {result.worker_type or 'n/a'}")
    if result.worker_result is not None:
        lines.append(f"Worker success:    {result.worker_result.success}")
        lines.append(f"Worker message:    {result.worker_result.message}")
    else:
        lines.append("Worker success:    n/a")

    if result.review_bundle_path:
        lines.append(f"Review bundle:     {result.review_bundle_path}")
    else:
        lines.append("Review bundle:     n/a")

    if result.pytest_result is not None:
        lines.append(f"Pytest command:    {' '.join(result.pytest_result.command)}")
        lines.append(f"Pytest result:     {'PASS' if result.pytest_result.ok else 'FAIL'}")
        lines.append(f"Pytest returncode: {result.pytest_result.returncode}")
        if result.pytest_result.passed_count is not None:
            lines.append(f"Pytest passed:     {result.pytest_result.passed_count}")
        if result.pytest_result.summary:
            lines.append(f"Pytest summary:    {result.pytest_result.summary}")
    else:
        lines.append("Pytest result:     n/a")

    if result.diff_check_result is not None:
        status = "PASS" if result.diff_check_result.ok else "FAIL"
        lines.append(f"Diff check result: {status}")
    else:
        lines.append("Diff check result: n/a")

    if result.scope_result is not None:
        lines.append(f"Allowed paths:     {result.scope_result.allowed_paths}")
        lines.append(f"Actual paths:      {result.scope_result.actual_paths}")
        status = "PASS" if result.scope_result.ok else "FAIL"
        lines.append(f"Scope match:       {status}")
    else:
        lines.append("Allowed paths:     n/a")
        lines.append("Actual paths:      n/a")
        lines.append("Scope match:       n/a")

    if result.staged_paths:
        lines.append(f"Staged paths:      {result.staged_paths}")
        lines.append("WARNING: worker created staged/index changes")
    else:
        lines.append("Staged paths:      none")

    if result.post_git_info is not None:
        lines.append(
            f"Working tree:      {'clean' if result.post_git_info.is_clean else 'dirty'}"
        )
    else:
        lines.append("Working tree:      n/a")

    lines.append("Publication state: NO staging / commit / push / merge performed")
    lines.append("Next action:       controller/owner review")
    lines.append("-" * 72)
    lines.append("Messages:")
    for msg in result.messages:
        lines.append(f"  {msg}")
    lines.append("=" * 72)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def _derive_actual_changed_paths(result: RunnerResult) -> list[str]:
    """Return the actual changed paths from a completed runner result."""
    if result.post_verification is not None:
        return list(result.post_verification.changed_paths or [])
    return []


def _pre_execute_failure(
    status: AutoPipelineStatus,
    messages: list[str],
    task: Task | None = None,
    repo_root: Path | None = None,
    worker_type: str | None = None,
) -> AutoPipelineResult:
    """Build a failure result before the worker is launched and write an artifact."""
    result = AutoPipelineResult(
        status=status,
        task=task,
        worker_type=worker_type,
        messages=messages,
    )
    if repo_root is not None:
        result.git_info = GitInfo(
            repo_root=repo_root,
            current_branch="unknown",
            head_sha="unknown",
            is_clean=False,
            status_lines=[],
        )
        _write_auto_artifact(result)
    return result


def run_auto_pipeline(
    tasks_dir: Path,
    task_id: str,
    worker: WorkerAdapter,
    *,
    require_scope: bool = True,
    pytest_runner: Callable[[Path], PytestResult] | None = None,
    diff_check_runner: Callable[[Path], DiffCheckResult] | None = None,
) -> AutoPipelineResult:
    """Run the full governed auto-pipeline for *task_id*.

    The pipeline reuses the existing ``execute()`` runner for validation,
    worker launch, post-worker Git verification, audit, and review-bundle
    generation. It then runs pytest, ``git diff --check`` (unstaged and
    staged), exact scope validation, and writes a consolidated auto artifact.

    The pipeline never stages, commits, pushes, merges, switches branches, or
    mutates task lifecycle state.
    """
    pytest_runner = pytest_runner or run_pytest
    diff_check_runner = diff_check_runner or run_git_diff_check
    repo_root = tasks_dir.parent

    # Step 1: discover the approved task.
    try:
        task = find_task(tasks_dir, task_id)
    except Exception as exc:
        return _pre_execute_failure(
            AutoPipelineStatus.VALIDATION_FAILED,
            [f"FAIL: cannot discover task: {exc}"],
            repo_root=repo_root,
        )

    # Step 2: parse and validate allowed changed-file scope before any worker runs.
    allowed_scope_raw = parse_task_allowed_scope(task.path)
    if require_scope and allowed_scope_raw is None:
        return _pre_execute_failure(
            AutoPipelineStatus.SCOPE_FAILED,
            ["FAIL: task is missing required 'Allowed changed-file scope' section"],
            task=task,
            repo_root=repo_root,
            worker_type=worker.name,
        )

    safe_allowed, unsafe_allowed = _validate_allowed_paths(allowed_scope_raw or [])
    if unsafe_allowed:
        return _pre_execute_failure(
            AutoPipelineStatus.SCOPE_FAILED,
            [
                "FAIL: allowed changed-file scope contains unsafe path(s): "
                f"{unsafe_allowed}"
            ],
            task=task,
            repo_root=repo_root,
            worker_type=worker.name,
        )

    # Step 3: launch worker via the existing runner execute path.
    # ``execute()`` validates branch/clean/status, captures pre/post Git snapshots,
    # writes an audit record, and produces a review bundle.
    runner_result = execute(tasks_dir, task_id, worker=worker)

    result = AutoPipelineResult(
        status=AutoPipelineStatus.READY_FOR_APPROVAL,
        task=task,
        git_info=runner_result.git_info,
        pre_git_info=runner_result.pre_git_info,
        post_git_info=runner_result.post_git_info,
        validation=runner_result.validation,
        allowed_paths=safe_allowed,
        worker_type=runner_result.worker_type,
        worker_result=runner_result.worker_result,
        post_verification=runner_result.post_verification,
        review_bundle_path=runner_result.review_bundle_path,
        audit_path=runner_result.audit_path,
        audit_write_ok=runner_result.audit_write_ok,
        audit_write_error=runner_result.audit_write_error,
        messages=list(runner_result.messages or []),
    )

    if runner_result.status == RunnerStatus.FAILED:
        result.status = AutoPipelineStatus.VALIDATION_FAILED
        if runner_result.validation is not None:
            result.messages.extend(runner_result.validation.messages)
        result.messages.append("Execution blocked: safety validation failed.")
        _write_auto_artifact(result)
        return result

    if runner_result.status == RunnerStatus.POST_WORKER_VERIFICATION_FAILED:
        result.status = AutoPipelineStatus.POST_WORKER_VERIFICATION_FAILED
        result.messages.append("Post-worker verification failed.")
        _write_auto_artifact(result)
        return result

    if runner_result.worker_result is None or not runner_result.worker_result.success:
        result.status = AutoPipelineStatus.WORKER_FAILED
        if runner_result.worker_result:
            result.messages.append(f"Worker failed: {runner_result.worker_result.message}")
        else:
            result.messages.append("Worker failed: no worker result returned")
        _write_auto_artifact(result)
        return result

    # Step 4: detect staged/index changes created by the worker.
    repo_root = runner_result.git_info.repo_root if runner_result.git_info else repo_root
    try:
        result.staged_paths = detect_staged_paths(repo_root)
    except Exception as exc:  # pragma: no cover - defensive
        result.staged_paths = []
        result.messages.append(f"WARNING: could not inspect staged changes: {exc}")

    if result.staged_paths:
        result.status = AutoPipelineStatus.SCOPE_FAILED
        result.messages.append(
            "FAIL: worker created staged/index changes; staging is not permitted"
        )
        _write_auto_artifact(result)
        return result

    # Step 5: run full pytest suite.
    try:
        result.pytest_result = pytest_runner(repo_root)
    except Exception as exc:
        result.pytest_result = PytestResult(
            command=[],
            returncode=-1,
            stdout="",
            stderr=str(exc),
            passed_count=None,
            summary=f"pytest runner failed: {exc}",
        )

    if not result.pytest_result.ok:
        result.status = AutoPipelineStatus.TEST_FAILED
        result.messages.append(
            f"FAIL: pytest exited with {result.pytest_result.returncode}"
        )
        _write_auto_artifact(result)
        return result

    result.messages.append(
        f"PASS: pytest ({' '.join(result.pytest_result.command)})"
    )
    if result.pytest_result.passed_count is not None:
        result.messages.append(
            f"PASS: {result.pytest_result.passed_count} test(s) passed"
        )

    # Step 6: run git diff --check (unstaged and staged).
    try:
        result.diff_check_result = diff_check_runner(repo_root)
    except Exception as exc:
        result.diff_check_result = DiffCheckResult(
            commands=[],
            returncodes=[-1],
            stdout="",
            stderr=str(exc),
        )

    if not result.diff_check_result.ok:
        result.status = AutoPipelineStatus.DIFF_CHECK_FAILED
        result.messages.append("FAIL: git diff --check detected whitespace errors")
        _write_auto_artifact(result)
        return result

    result.messages.append("PASS: git diff --check found no whitespace errors")

    # Step 7: validate exact changed-file scope.
    actual_paths = _derive_actual_changed_paths(runner_result)
    result.scope_result = build_scope_result(
        safe_allowed,
        actual_paths,
        require_scope=require_scope,
    )
    result.messages.extend(result.scope_result.messages)

    if not result.scope_result.ok:
        result.status = AutoPipelineStatus.SCOPE_FAILED
        _write_auto_artifact(result)
        return result

    # Step 8: finalize as READY_FOR_APPROVAL.
    result.status = AutoPipelineStatus.READY_FOR_APPROVAL
    result.messages.append(
        "Implementation and verification complete. READY FOR CONTROLLER/OWNER REVIEW."
    )
    result.messages.append(
        "No staging, commit, push, merge, deployment, or lifecycle approval occurred."
    )

    _write_auto_artifact(result)
    return result


def _write_auto_artifact(result: AutoPipelineResult) -> None:
    """Write the auto-pipeline artifact and update *result* in place."""
    repo_root = result.git_info.repo_root if result.git_info else None
    if repo_root is None:
        result.auto_artifact_write_ok = False
        result.auto_artifact_write_error = "Cannot write auto artifact: no Git snapshot available."
        result.messages.append(f"WARNING: {result.auto_artifact_write_error}")
        return

    try:
        payload = build_auto_artifact_payload(result)
        path = write_auto_artifact(payload, default_auto_dir(repo_root))
        result.auto_artifact_path = path
        try:
            rel_path = path.relative_to(repo_root)
        except ValueError:
            rel_path = path
        result.messages.append(f"Auto pipeline artifact written to {rel_path}")
    except AutoArtifactWriteError as exc:
        result.auto_artifact_write_ok = False
        result.auto_artifact_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")
