"""Safety validation for agent-runner execution planning."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from advancore.agent_runner.task import ALLOWED_STATUSES, Task


@dataclass
class ValidationResult:
    """Result of safety pre-flight checks."""

    ok: bool
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


REWORK_EVIDENCE_SCHEMA = "advancore-owner-rework-v2"
REWORK_TERMINAL_HASH_PREFIX = "PASS: owner rework terminal content hash "
_STATUS_LINE_RE = re.compile(rb"(?m)^STATUS:\s*[^\r\n]+$")


class ReworkValidationPhase(str, Enum):
    """Repository content policy for one owner-authorized rework capability."""

    BASELINE = "BASELINE"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class OwnerReworkEvidence:
    """Single-use, content-bound authority for one exact owner rework cycle."""

    schema_version: str
    task_id: str
    task_path: str
    run_id: str
    review_bundle_id: str
    review_bundle_path: str
    handoff_id: str
    handoff_path: str
    decision_id: str
    decision_path: str
    owner_note: str | None
    branch: str
    head_sha: str
    allowed_scope: tuple[str, ...]
    changed_paths: tuple[str, ...]
    content_hashes: tuple[tuple[str, str], ...]
    normalized_task_hash: str
    binary_diff_hash: str
    index_hash: str
    remote_config_hash: str
    remote_refs_hash: str
    integrity_hash: str
    authorization_id: str
    evidence_hash: str


@dataclass(frozen=True)
class _ReworkSnapshot:
    branch: str
    head_sha: str
    changed_paths: tuple[str, ...]
    content_hashes: tuple[tuple[str, str], ...]
    normalized_task_hash: str
    binary_diff_hash: str
    index_hash: str
    remote_config_hash: str
    remote_refs_hash: str
    integrity_hash: str


def _git_bytes(repo_root: Path, *args: str, allow_no_match: bool = False) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return completed.stdout
    if allow_no_match and completed.returncode == 1:
        return b""
    stderr = completed.stderr.decode("utf-8", "replace").strip()
    raise ValueError(f"git {' '.join(args)} failed: {stderr}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalized_task_bytes(data: bytes) -> bytes:
    matches = list(_STATUS_LINE_RE.finditer(data))
    if len(matches) != 1:
        raise ValueError("task must contain exactly one STATUS line")
    return _STATUS_LINE_RE.sub(b"STATUS: <LIFECYCLE>", data, count=1)


def _canonical_json_hash(payload: dict[str, object]) -> str:
    return _sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _normalize_repo_path(path: str) -> str:
    stripped = path.strip()
    if not stripped or stripped.startswith(("/", "\\", "~")):
        raise ValueError(f"unsafe repository path: {path!r}")
    parts = stripped.replace("\\", "/").split("/")
    if parts and parts[0] == ".":
        parts = parts[1:]
    if not parts or any(part in {"", ".", "..", ".git"} for part in parts):
        raise ValueError(f"unsafe repository path: {path!r}")
    return "/".join(parts)


def _status_paths(repo_root: Path) -> tuple[str, ...]:
    raw = _git_bytes(
        repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    paths: list[str] = []
    for entry in (item for item in raw.split(b"\0") if item):
        if len(entry) < 4 or entry[2:3] != b" ":
            raise ValueError("malformed Git status entry")
        code = entry[:2]
        path = entry[3:].decode("utf-8", "strict")
        if code != b" M":
            raise ValueError(
                f"unsupported or ambiguous Git state {code!r} for {path}"
            )
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate changed paths")
    if not paths:
        raise ValueError("reviewed rework baseline has no tracked unstaged changes")
    if _git_bytes(repo_root, "diff", "--cached", "--binary", "--no-ext-diff"):
        raise ValueError("index is not clean")
    if _git_bytes(repo_root, "diff", "--summary", "--no-ext-diff"):
        raise ValueError("rename, deletion, or mode change is not supported")
    return tuple(sorted(paths))


def _capture_rework_snapshot(
    repo_root: Path,
    *,
    task_path: str,
    allowed_scope: tuple[str, ...],
    include_clean_task: bool = False,
) -> _ReworkSnapshot:
    repo = repo_root.resolve()
    branch = _git_bytes(repo, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip()
    head_sha = _git_bytes(repo, "rev-parse", "--verify", "HEAD").decode().strip()
    changed_paths = _status_paths(repo)
    if include_clean_task and task_path not in changed_paths:
        changed_paths = tuple(sorted((*changed_paths, task_path)))
    outside = sorted(set(changed_paths) - set(allowed_scope))
    if outside:
        raise ValueError(f"reviewed path outside task scope: {outside}")

    hashes: list[tuple[str, str]] = []
    normalized_task_hash = ""
    diff_parts: list[bytes] = []
    for path in changed_paths:
        worktree_data = (repo / path).read_bytes()
        head_data = _git_bytes(repo, "show", f"HEAD:{path}")
        if path == task_path:
            worktree_data = _normalized_task_bytes(worktree_data)
            head_data = _normalized_task_bytes(head_data)
            normalized_task_hash = _sha256(worktree_data)
        hashes.append((path, _sha256(worktree_data)))
        diff_parts.extend(
            (path.encode("utf-8"), b"\0", head_data, b"\0", worktree_data, b"\0")
        )

    remote_config = _git_bytes(
        repo,
        "config",
        "--local",
        "--null",
        "--get-regexp",
        r"^remote\.",
        allow_no_match=True,
    )
    remote_refs = _git_bytes(
        repo,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)%00%(symref)",
        "refs/remotes",
    )
    fsck = _git_bytes(repo, "fsck", "--full", "--no-progress")
    reachable = _git_bytes(repo, "rev-list", "--objects", "--all")
    index_diff = _git_bytes(repo, "diff", "--cached", "--binary", "--no-ext-diff")
    return _ReworkSnapshot(
        branch=branch,
        head_sha=head_sha,
        changed_paths=changed_paths,
        content_hashes=tuple(hashes),
        normalized_task_hash=normalized_task_hash,
        binary_diff_hash=_sha256(b"".join(diff_parts)),
        index_hash=_sha256(index_diff),
        remote_config_hash=_sha256(remote_config),
        remote_refs_hash=_sha256(remote_refs),
        integrity_hash=_sha256(fsck + b"\0" + reachable),
    )


def _evidence_payload(evidence: OwnerReworkEvidence) -> dict[str, object]:
    return {
        name: getattr(evidence, name)
        for name in evidence.__dataclass_fields__
        if name != "evidence_hash"
    }


def capture_owner_rework_evidence(
    repo_root: Path,
    *,
    task_id: str,
    task_path: str,
    run_id: str,
    review_bundle_id: str,
    review_bundle_path: str,
    handoff_id: str,
    handoff_path: str,
    decision_id: str,
    decision_path: str,
    allowed_scope: list[str] | tuple[str, ...],
    owner_note: str | None = None,
) -> OwnerReworkEvidence:
    """Capture the exact reviewed baseline after a matching owner decision."""
    identities = (
        task_id,
        task_path,
        run_id,
        review_bundle_id,
        review_bundle_path,
        handoff_id,
        handoff_path,
        decision_id,
        decision_path,
    )
    if any(not value or not value.strip() for value in identities):
        raise ValueError("rework evidence identities must be non-empty")
    if owner_note is not None and (
        "\n" in owner_note or "\r" in owner_note or len(owner_note) > 400
    ):
        raise ValueError("owner note is malformed or oversized")
    task_path = _normalize_repo_path(task_path)
    scope = tuple(sorted(_normalize_repo_path(path) for path in allowed_scope))
    if not scope or len(scope) != len(set(scope)):
        raise ValueError("allowed scope is missing or duplicated")
    snapshot = _capture_rework_snapshot(
        repo_root,
        task_path=task_path,
        allowed_scope=scope,
        include_clean_task=True,
    )
    authorization_id = _canonical_json_hash(
        {
            "schema_version": REWORK_EVIDENCE_SCHEMA,
            "task_id": task_id,
            "run_id": run_id,
            "review_bundle_id": review_bundle_id,
            "handoff_id": handoff_id,
            "decision_id": decision_id,
        }
    )
    draft = OwnerReworkEvidence(
        schema_version=REWORK_EVIDENCE_SCHEMA,
        task_id=task_id,
        task_path=task_path,
        run_id=run_id,
        review_bundle_id=review_bundle_id,
        review_bundle_path=review_bundle_path,
        handoff_id=handoff_id,
        handoff_path=handoff_path,
        decision_id=decision_id,
        decision_path=decision_path,
        owner_note=owner_note,
        allowed_scope=scope,
        authorization_id=authorization_id,
        evidence_hash="",
        **snapshot.__dict__,
    )
    return OwnerReworkEvidence(
        **{
            **draft.__dict__,
            "evidence_hash": _canonical_json_hash(_evidence_payload(draft)),
        }
    )


def validate_owner_rework_evidence(
    evidence: OwnerReworkEvidence | None,
    repo_root: Path,
    *,
    phase: ReworkValidationPhase,
    task_id: str,
    task_path: str,
    run_id: str | None = None,
    review_bundle_id: str | None = None,
    handoff_id: str | None = None,
    decision_id: str | None = None,
    allowed_scope: list[str] | tuple[str, ...] | None = None,
) -> ValidationResult:
    """Recompute either the frozen baseline or protected terminal boundary."""
    if not isinstance(evidence, OwnerReworkEvidence):
        return ValidationResult(False, ["FAIL: typed owner rework evidence is required"])
    try:
        expected_task_path = _normalize_repo_path(task_path)
        expected_scope = (
            tuple(sorted(_normalize_repo_path(path) for path in allowed_scope))
            if allowed_scope is not None
            else None
        )
    except ValueError as exc:
        return ValidationResult(False, [f"FAIL: unsafe rework path evidence: {exc}"])
    expected: dict[str, str] = {
        "task_id": task_id,
        "task_path": expected_task_path,
    }
    for name, value in (
        ("run_id", run_id),
        ("review_bundle_id", review_bundle_id),
        ("handoff_id", handoff_id),
        ("decision_id", decision_id),
    ):
        if value is not None:
            expected[name] = value
    mismatches = [
        name for name, value in expected.items() if getattr(evidence, name) != value
    ]
    if evidence.schema_version != REWORK_EVIDENCE_SCHEMA:
        mismatches.append("schema_version")
    if expected_scope is not None and evidence.allowed_scope != expected_scope:
        mismatches.append("allowed_scope")
    if _canonical_json_hash(_evidence_payload(evidence)) != evidence.evidence_hash:
        mismatches.append("evidence_hash")
    expected_authorization = _canonical_json_hash(
        {
            "schema_version": evidence.schema_version,
            "task_id": evidence.task_id,
            "run_id": evidence.run_id,
            "review_bundle_id": evidence.review_bundle_id,
            "handoff_id": evidence.handoff_id,
            "decision_id": evidence.decision_id,
        }
    )
    if expected_authorization != evidence.authorization_id:
        mismatches.append("authorization_id")
    repo = repo_root.resolve()
    for path_field, hash_field in (
        ("review_bundle_path", "review_bundle_id"),
        ("handoff_path", "handoff_id"),
        ("decision_path", "decision_id"),
    ):
        raw_path = Path(getattr(evidence, path_field))
        artifact_path = raw_path if raw_path.is_absolute() else repo / raw_path
        try:
            if artifact_path.is_symlink():
                raise ValueError("symbolic links are not allowed")
            resolved = artifact_path.resolve(strict=True)
            resolved.relative_to(repo)
            if not resolved.is_file():
                raise ValueError("artifact is not a regular file")
            if _sha256(resolved.read_bytes()) != getattr(evidence, hash_field):
                mismatches.append(hash_field)
        except (OSError, ValueError):
            mismatches.append(path_field)
    try:
        snapshot = _capture_rework_snapshot(
            repo_root,
            task_path=evidence.task_path,
            allowed_scope=evidence.allowed_scope,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        return ValidationResult(
            False, [f"FAIL: rework repository validation failed: {exc}"]
        )

    protected_fields = (
        "branch",
        "head_sha",
        "changed_paths",
        "index_hash",
        "remote_config_hash",
        "remote_refs_hash",
        "integrity_hash",
    )
    for name in protected_fields:
        if getattr(snapshot, name) != getattr(evidence, name):
            mismatches.append(name)
    if phase == ReworkValidationPhase.BASELINE:
        for name in ("content_hashes", "normalized_task_hash", "binary_diff_hash"):
            if getattr(snapshot, name) != getattr(evidence, name):
                mismatches.append(name)
    elif phase != ReworkValidationPhase.TERMINAL:
        mismatches.append("phase")

    if mismatches:
        return ValidationResult(
            False,
            ["FAIL: rework evidence mismatch: " + ", ".join(sorted(set(mismatches)))],
        )
    return ValidationResult(
        True,
        [
            "PASS: owner rework baseline exactly matches"
            if phase == ReworkValidationPhase.BASELINE
            else "PASS: owner rework terminal repository boundary matches"
        ],
    )


def owner_rework_terminal_content_hash(
    evidence: OwnerReworkEvidence, repo_root: Path
) -> str:
    """Fingerprint current terminal content for fresh review/handoff binding."""
    snapshot = _capture_rework_snapshot(
        repo_root,
        task_path=evidence.task_path,
        allowed_scope=evidence.allowed_scope,
    )
    return _canonical_json_hash(
        {
            "authorization_id": evidence.authorization_id,
            "terminal_snapshot": asdict(snapshot),
        }
    )


def validate(
    task: Task,
    current_branch: str,
    is_clean: bool,
    allowed_statuses: set[str] | None = None,
) -> ValidationResult:
    """Validate that *task* can be planned/executed safely.

    Checks:
      - current branch is not ``main``,
      - working tree is clean,
      - task status is in *allowed_statuses* (default ``READY``/``REWORK``).

    Returns a ``ValidationResult`` that is truthy iff all checks pass.
    """
    if allowed_statuses is None:
        allowed_statuses = ALLOWED_STATUSES

    messages: list[str] = []
    ok = True

    if current_branch == "main":
        messages.append("FAIL: execution on 'main' branch is not allowed")
        ok = False
    else:
        messages.append(f"PASS: current branch '{current_branch}' is not 'main'")

    if not is_clean:
        messages.append("FAIL: working tree has uncommitted changes")
        ok = False
    else:
        messages.append("PASS: working tree is clean")

    if task.status not in allowed_statuses:
        messages.append(
            f"FAIL: task status '{task.status}' is not executable "
            f"(must be one of {', '.join(sorted(allowed_statuses))})"
        )
        ok = False
    else:
        messages.append(f"PASS: task status '{task.status}' is executable")

    if ok:
        messages.append("PASS: all safety validations passed")

    return ValidationResult(ok=ok, messages=messages)
