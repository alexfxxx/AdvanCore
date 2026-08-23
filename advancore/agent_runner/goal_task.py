"""Goal-to-task generation foundation for the local agent runner.

This module provides a governed **owner-goal -> task-draft** layer.  A bounded
natural-language owner goal is converted into a deterministic ``STATUS: DRAFT``
AdvanCore task file.

The planner (``kimi`` / ``kimi-swarm`` / dry-run) proposes task content only.
The AdvanCore runner validates the proposal, assigns the next task ID, renders
the canonical task document, enforces path/scope safety, verifies that the
planner did not mutate the repository, and writes the task file.

A generated DRAFT task is **not executable authority**.  Only a controller/owner
may move it to ``READY`` through the existing lifecycle rules.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from advancore.agent_runner.git_info import GitInfo, get_git_info
from advancore.agent_runner.worker import (
    APPROVED_PLANNER_NAMES,
    APPROVED_WORKER_NAMES,
    WorkerAdapter,
    WorkerResult,
)


# ---------------------------------------------------------------------------
# Bounded constants
# ---------------------------------------------------------------------------

MAX_GOAL_LENGTH = 2000
MAX_TITLE_LENGTH = 120
MAX_TEXT_FIELD_LENGTH = 4000
MAX_LIST_ITEM_LENGTH = 500
MAX_LIST_LENGTH = 100
MAX_SCOPE_PATH_LENGTH = 260
MAX_SCOPE_LIST_LENGTH = 50
MAX_SLUG_LENGTH = 60

PROPOSAL_SCHEMA_VERSION = "advancore-goal-task-proposal-v1"

PROPOSAL_START_MARKER = "--- ADVANCORE_GOAL_TASK_PROPOSAL_START ---"
PROPOSAL_END_MARKER = "--- ADVANCORE_GOAL_TASK_PROPOSAL_END ---"

TASK_FILENAME_RE = re.compile(r"^(TASK-(\d+))-(.+)\.md$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GoalTaskError(Exception):
    """Raised when goal-to-task generation cannot proceed safely."""


class OwnerGoalError(GoalTaskError):
    """Raised when the owner goal is invalid or unsafe."""


class ProposalError(GoalTaskError):
    """Raised when the planner proposal is malformed, unknown, or unsafe."""


class RepositoryMutationError(GoalTaskError):
    """Raised when the planner mutates the repository unexpectedly."""


class TaskIdAssignmentError(GoalTaskError):
    """Raised when the runner cannot assign a safe task ID."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class OwnerGoal:
    """Validated owner goal input."""

    raw_goal: str
    normalized: str
    accepted: bool
    messages: list[str] = field(default_factory=list)


@dataclass
class GoalTaskProposal:
    """Untrusted planner proposal parsed and validated by the runner."""

    schema_version: str
    title: str
    objective: str
    business_context: str
    facts: list[str]
    assumptions: list[str]
    in_scope: list[str]
    out_of_scope: list[str]
    allowed_changed_file_scope: list[str]
    database_impact: str
    acceptance_criteria: list[str]
    test_requirements: list[str]
    constraints_safety_requirements: list[str]
    owner_decisions: list[str]
    recommended_worker: str | None = None


@dataclass
class RepositorySnapshot:
    """Pre/post planner repository state used for integrity verification."""

    git_info: GitInfo
    remote_urls: list[str]


class GoalTaskGenerationStatus(str, Enum):
    """Terminal status of a goal-to-task generation attempt."""

    DRY_RUN = "dry_run"
    VALIDATION_FAILED = "validation_failed"
    PRECONDITION_FAILED = "precondition_failed"
    PLANNER_FAILED = "planner_failed"
    PROPOSAL_REJECTED = "proposal_rejected"
    MUTATION_DETECTED = "mutation_detected"
    TASK_ID_COLLISION = "task_id_collision"
    DRAFT_CREATED = "draft_created"


@dataclass
class GoalTaskGenerationResult:
    """Complete result of a goal-to-task generation attempt."""

    ok: bool
    status: GoalTaskGenerationStatus
    goal_accepted: bool = False
    planner_type: str | None = None
    planner_success: bool | None = None
    primary_planner: str | None = None
    fallback_planner: str | None = None
    terminal_planner: str | None = None
    planner_timeout_seconds: int | None = None
    failure_classification: str | None = None
    integrity_ok: bool | None = None
    fallback_used: bool = False
    recovery_evidence: list[str] = field(default_factory=list)
    proposal_valid: bool = False
    task_id: str | None = None
    task_path: Path | None = None
    task_written: bool = False
    artifact_path: Path | None = None
    pre_snapshot: RepositorySnapshot | None = None
    post_snapshot: RepositorySnapshot | None = None
    owner_decision_count: int = 0
    no_publication_performed: bool = True
    next_action: str = "controller/owner review and DRAFT -> READY decision"
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


# ---------------------------------------------------------------------------
# Owner goal validation
# ---------------------------------------------------------------------------


def _normalize_goal(raw: str) -> str:
    """Return a stripped, bounded normalization of *raw*."""
    return " ".join(raw.split())


def validate_owner_goal(raw: str) -> OwnerGoal:
    """Validate *raw* owner goal and return an ``OwnerGoal`` result.

    Rejects empty/whitespace-only input and goals that exceed the deterministic
    maximum length.  The raw goal is never treated as controller authority.
    """
    messages: list[str] = []

    if raw is None or not isinstance(raw, str):
        messages.append("FAIL: owner goal must be a string")
        return OwnerGoal(raw_goal="", normalized="", accepted=False, messages=messages)

    normalized = _normalize_goal(raw)

    if not normalized:
        messages.append("FAIL: owner goal is empty or whitespace-only")
        return OwnerGoal(raw_goal=raw, normalized=normalized, accepted=False, messages=messages)

    if len(normalized) > MAX_GOAL_LENGTH:
        messages.append(
            f"FAIL: owner goal exceeds maximum length ({len(normalized)} > {MAX_GOAL_LENGTH})"
        )
        return OwnerGoal(raw_goal=raw, normalized=normalized, accepted=False, messages=messages)

    messages.append("PASS: owner goal accepted")
    return OwnerGoal(
        raw_goal=raw, normalized=normalized, accepted=True, messages=messages
    )


def _hash_goal(text: str) -> str:
    """Return a deterministic short hash of *text* for audit metadata."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _short_summary(text: str, max_length: int = 120) -> str:
    """Return a bounded short summary of *text* for artifact metadata."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


# ---------------------------------------------------------------------------
# Planner instruction
# ---------------------------------------------------------------------------


def build_planner_instruction(goal: str, schema_version: str = PROPOSAL_SCHEMA_VERSION) -> str:
    """Return the canonical bounded planner instruction for *goal*.

    The instruction explicitly limits the planner to planning assistance only,
    forbids repository mutation, and requires a single structured proposal
    between deterministic markers.  The owner goal is included as bounded
    context, not as authority.
    """
    return f"""Read AGENTS.md.

You are acting as a bounded planner for the AdvanCore agent runner.
Your job is to propose the content of a single new AdvanCore task file based on
the owner goal below.  This proposal is planning assistance ONLY and has no
authority to execute, approve, or publish anything.

Owner goal (bounded planning context):
{goal}

Governance you MUST obey:
- Propose task content only.  Do NOT modify repository files.
- Do NOT stage, commit, push, merge, tag, deploy, switch branches, reset,
  rebase, or rewrite history.
- Do NOT change HEAD, branch, or remotes.
- Do NOT access credentials, secrets, tokens, or production data.
- Do NOT declare the task READY, APPROVED, or executable.
- Do NOT assign a task ID, status, or lifecycle transition.
- Return ONLY ONE bounded structured task proposal between the exact markers
  below and nothing else.

Return the proposal as a single JSON object between these markers:
{PROPOSAL_START_MARKER}
<JSON>
{PROPOSAL_END_MARKER}

Schema version (MUST match exactly): "{schema_version}"

Required JSON fields:
- "schema_version": "{schema_version}"
- "title": short task title (string)
- "objective": single outcome this task must achieve (string)
- "business_context": why the task matters (string)
- "facts": list of confirmed facts (list of strings)
- "assumptions": list of explicit assumptions (list of strings)
- "in_scope": list of explicitly authorised work (list of strings)
- "out_of_scope": list of work that must not be included (list of strings)
- "allowed_changed_file_scope": list of repository-relative file paths the
  task may change (list of strings).  Paths must be relative, no parent
  traversal, no absolute paths.
- "database_impact": expected schema/data impact or "None" (string)
- "acceptance_criteria": list of acceptance criteria (list of strings)
- "test_requirements": list of tests that must be added or run (list of strings)
- "constraints_safety_requirements": list of constraints and safety rules
  (list of strings)
- "owner_decisions": list of unresolved business/compliance/credential/
  production/deployment decisions that require controller/owner review
  (list of strings).  Use ["None"] if there are none.

Optional JSON field:
- "recommended_worker": one registered non-dry-run implementation worker:
  {", ".join(name for name in APPROVED_WORKER_NAMES if name != "dry-run")} (string)

Do NOT include any of the following fields:
- task_id, status, lifecycle, branch, commit, push, merge, deploy, approved.
"""


# ---------------------------------------------------------------------------
# Repository snapshot and mutation detection
# ---------------------------------------------------------------------------


def _capture_remote_urls(repo_root: Path) -> list[str]:
    """Return sorted ``remote -v`` output for *repo_root*.

    Uses the same argument-array subprocess boundary as the rest of the runner.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise GoalTaskError(f"Failed to inspect git remotes: {exc}") from exc

    if result.returncode != 0:
        raise GoalTaskError(f"git remote -v failed: {result.stderr.strip()}")

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return sorted(lines)


def capture_repository_snapshot(repo_root: Path) -> RepositorySnapshot:
    """Capture a deterministic pre/post planner repository snapshot."""
    git_info = get_git_info(cwd=repo_root)
    remote_urls = _capture_remote_urls(repo_root)
    return RepositorySnapshot(git_info=git_info, remote_urls=remote_urls)


def detect_repository_mutation(pre: RepositorySnapshot, post: RepositorySnapshot) -> list[str]:
    """Compare pre/post snapshots and return a list of failure messages.

    Any planner-created repository change is a generation failure.  The runner
    must not write a task file when mutation is detected.
    """
    failures: list[str] = []

    if pre.git_info.current_branch != post.git_info.current_branch:
        failures.append(
            f"FAIL: branch changed from '{pre.git_info.current_branch}' "
            f"to '{post.git_info.current_branch}'"
        )
    if pre.git_info.head_sha != post.git_info.head_sha:
        failures.append(
            f"FAIL: HEAD moved from {pre.git_info.head_sha[:8]} "
            f"to {post.git_info.head_sha[:8]}"
        )
    if pre.remote_urls != post.remote_urls:
        failures.append("FAIL: git remotes changed")

    # The pre-condition check guarantees the pre-snapshot worktree is clean.
    # Any post-status line is therefore a planner-side change.
    if post.git_info.status_lines:
        for line in post.git_info.status_lines:
            # Porcelain first column indicates staged/index changes.
            first = line[0] if line else " "
            if first not in (" ", "?"):
                failures.append(f"FAIL: planner staged/index change: {line}")
            else:
                failures.append(f"FAIL: planner worktree change: {line}")

    return failures


# ---------------------------------------------------------------------------
# Proposal parsing and validation
# ---------------------------------------------------------------------------


def _find_unique_marker(text: str, marker: str) -> int:
    """Return the index of *marker* in *text*, enforcing exactly one occurrence."""
    count = text.count(marker)
    if count == 0:
        raise ProposalError(f"Missing proposal marker: {marker}")
    if count > 1:
        raise ProposalError(f"Duplicate proposal marker: {marker}")
    return text.index(marker)


def parse_planner_output(raw_output: str) -> dict[str, Any]:
    """Extract the JSON proposal from deterministic markers in *raw_output*.

    Fails closed on missing/duplicate markers or malformed JSON.
    """
    if not isinstance(raw_output, str):
        raise ProposalError("Planner output is not a string")

    start = _find_unique_marker(raw_output, PROPOSAL_START_MARKER)
    end = _find_unique_marker(raw_output, PROPOSAL_END_MARKER)

    if end <= start:
        raise ProposalError("Proposal end marker appears before start marker")

    json_text = raw_output[start + len(PROPOSAL_START_MARKER) : end]
    json_text = json_text.strip()

    if not json_text:
        raise ProposalError("Proposal JSON is empty")

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ProposalError(f"Malformed proposal JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProposalError("Proposal JSON is not an object")

    return data


# ---------------------------------------------------------------------------
# Field-level validation helpers
# ---------------------------------------------------------------------------


def _validate_string(value: Any, field: str, max_length: int) -> str:
    """Validate that *value* is a non-empty string within the bound."""
    if not isinstance(value, str):
        raise ProposalError(f"Field '{field}' must be a string")
    stripped = value.strip()
    if not stripped:
        raise ProposalError(f"Field '{field}' is empty")
    if len(stripped) > max_length:
        raise ProposalError(
            f"Field '{field}' exceeds maximum length ({len(stripped)} > {max_length})"
        )
    return stripped


def _validate_string_list(
    value: Any,
    field: str,
    max_items: int = MAX_LIST_LENGTH,
    max_item_length: int = MAX_LIST_ITEM_LENGTH,
    allow_empty: bool = True,
) -> list[str]:
    """Validate a list of bounded strings, normalizing whitespace."""
    if not isinstance(value, list):
        raise ProposalError(f"Field '{field}' must be a list")
    if len(value) > max_items:
        raise ProposalError(
            f"Field '{field}' exceeds maximum list length ({len(value)} > {max_items})"
        )

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ProposalError(f"Field '{field}' contains a non-string item")
        stripped = " ".join(item.split())
        if not stripped:
            raise ProposalError(f"Field '{field}' contains an empty item")
        if len(stripped) > max_item_length:
            raise ProposalError(
                f"Item in '{field}' exceeds maximum length ({len(stripped)} > {max_item_length})"
            )
        normalized.append(stripped)

    if not allow_empty and not normalized:
        raise ProposalError(f"Field '{field}' must contain at least one item")

    return normalized


def _normalize_scope_path(path: str) -> str:
    """Return a normalized repository-relative scope path or raise ``ProposalError``."""
    stripped = path.strip()
    if not stripped:
        raise ProposalError("Empty scope path")
    if stripped.startswith("/") or stripped.startswith("\\"):
        raise ProposalError(f"Absolute scope path: {path}")
    if stripped.startswith("~"):
        raise ProposalError(f"Unsafe scope path: {path}")

    parts = stripped.replace("\\", "/").split("/")
    if ".." in parts:
        raise ProposalError(f"Scope path escapes repository: {path}")
    if parts and parts[0] == ".":
        parts = parts[1:]

    normalized = "/".join(parts)
    if not normalized:
        raise ProposalError(f"Empty scope path after normalization: {path}")
    if len(normalized) > MAX_SCOPE_PATH_LENGTH:
        raise ProposalError(f"Scope path too long: {path}")
    return normalized


def _validate_scope_paths(paths: list[str]) -> list[str]:
    """Validate and deduplicate scope paths, preserving order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in paths:
        try:
            norm = _normalize_scope_path(raw)
        except ProposalError:
            raise
        if norm in seen:
            continue
        seen.add(norm)
        normalized.append(norm)
    return normalized


# Required and optional proposal fields.
_REQUIRED_FIELDS = {
    "schema_version",
    "title",
    "objective",
    "business_context",
    "facts",
    "assumptions",
    "in_scope",
    "out_of_scope",
    "allowed_changed_file_scope",
    "database_impact",
    "acceptance_criteria",
    "test_requirements",
    "constraints_safety_requirements",
    "owner_decisions",
}

_OPTIONAL_FIELDS = {"recommended_worker"}

_ALLOWED_FIELDS = _REQUIRED_FIELDS | _OPTIONAL_FIELDS


# Planner-controlled fields that must never appear.
_DISALLOWED_FIELDS = {
    "task_id",
    "status",
    "lifecycle",
    "branch",
    "commit",
    "push",
    "merge",
    "deploy",
    "approved",
    "ready",
}


def validate_proposal(data: dict[str, Any]) -> GoalTaskProposal:
    """Validate *data* and return a ``GoalTaskProposal``.

    Fails closed on unknown schema version, unexpected fields, missing required
    fields, oversized fields, unsafe scope paths, and disallowed authority
    fields.
    """
    if not isinstance(data, dict):
        raise ProposalError("Proposal is not a JSON object")

    # Disallowed authority fields are rejected with a specific message.
    forbidden = set(data.keys()) & _DISALLOWED_FIELDS
    if forbidden:
        raise ProposalError(
            f"Proposal contains forbidden authority field(s): {sorted(forbidden)}"
        )

    # Unknown/unexpected top-level fields.
    unknown = set(data.keys()) - _ALLOWED_FIELDS
    if unknown:
        raise ProposalError(f"Unknown proposal field(s): {sorted(unknown)}")

    missing = _REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ProposalError(f"Missing required proposal field(s): {sorted(missing)}")

    schema_version = _validate_string(
        data["schema_version"], "schema_version", MAX_TEXT_FIELD_LENGTH
    )
    if schema_version != PROPOSAL_SCHEMA_VERSION:
        raise ProposalError(
            f"Unknown proposal schema version: {schema_version!r} "
            f"(expected {PROPOSAL_SCHEMA_VERSION!r})"
        )

    title = _validate_string(data["title"], "title", MAX_TITLE_LENGTH)
    objective = _validate_string(data["objective"], "objective", MAX_TEXT_FIELD_LENGTH)
    business_context = _validate_string(
        data["business_context"], "business_context", MAX_TEXT_FIELD_LENGTH
    )
    database_impact = _validate_string(
        data["database_impact"], "database_impact", MAX_TEXT_FIELD_LENGTH
    )

    facts = _validate_string_list(data["facts"], "facts")
    assumptions = _validate_string_list(data["assumptions"], "assumptions")
    in_scope = _validate_string_list(data["in_scope"], "in_scope", allow_empty=False)
    out_of_scope = _validate_string_list(
        data["out_of_scope"], "out_of_scope", allow_empty=False
    )
    acceptance_criteria = _validate_string_list(
        data["acceptance_criteria"], "acceptance_criteria", allow_empty=False
    )
    test_requirements = _validate_string_list(
        data["test_requirements"], "test_requirements", allow_empty=False
    )
    constraints_safety_requirements = _validate_string_list(
        data["constraints_safety_requirements"],
        "constraints_safety_requirements",
        allow_empty=False,
    )

    raw_scope = _validate_string_list(
        data["allowed_changed_file_scope"],
        "allowed_changed_file_scope",
        max_items=MAX_SCOPE_LIST_LENGTH,
        allow_empty=False,
    )
    allowed_changed_file_scope = _validate_scope_paths(raw_scope)

    owner_decisions = _validate_string_list(
        data["owner_decisions"], "owner_decisions", allow_empty=True
    )
    # Normalise ["None"] or empty list to an empty explicit representation.
    if owner_decisions == ["None"]:
        owner_decisions = []

    recommended_worker: str | None = None
    if "recommended_worker" in data:
        recommended_worker = _validate_string(
            data["recommended_worker"], "recommended_worker", MAX_TITLE_LENGTH
        )
        allowed_recommended_workers = {
            name for name in APPROVED_WORKER_NAMES if name != "dry-run"
        }
        if recommended_worker not in allowed_recommended_workers:
            raise ProposalError(
                "recommended_worker must be a registered non-dry-run worker, "
                f"got {recommended_worker!r}"
            )

    return GoalTaskProposal(
        schema_version=schema_version,
        title=title,
        objective=objective,
        business_context=business_context,
        facts=facts,
        assumptions=assumptions,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        allowed_changed_file_scope=allowed_changed_file_scope,
        database_impact=database_impact,
        acceptance_criteria=acceptance_criteria,
        test_requirements=test_requirements,
        constraints_safety_requirements=constraints_safety_requirements,
        owner_decisions=owner_decisions,
        recommended_worker=recommended_worker,
    )


# ---------------------------------------------------------------------------
# Task ID allocation and filename safety
# ---------------------------------------------------------------------------


def assign_next_task_id(tasks_dir: Path) -> str:
    """Return the next unused ``TASK-###`` ID based on existing task files.

    The planner cannot choose the number.  The assignment is stable and
    explainable: it is ``max(existing numbers) + 1``.
    """
    max_num = 0
    found = False

    for path in tasks_dir.glob("TASK-*.md"):
        match = TASK_FILENAME_RE.match(path.name)
        if not match:
            continue
        num = int(match.group(2))
        found = True
        if num > max_num:
            max_num = num

    next_num = max_num + 1 if found else 1
    return f"TASK-{next_num:03d}"


def _safe_slug(title: str) -> str:
    """Return a safe filename slug from *title*.

    Rejects/normalizes unsafe filename characters and guarantees the slug stays
    strictly under the ``tasks/`` directory when combined with a ``TASK-###``
    prefix.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-.")

    if not cleaned:
        raise GoalTaskError(f"Cannot create filename slug from title: {title!r}")

    if len(cleaned) > MAX_SLUG_LENGTH:
        cleaned = cleaned[:MAX_SLUG_LENGTH].rsplit("-", 1)[0].rstrip("-")
        if not cleaned:
            cleaned = title.lower()[:MAX_SLUG_LENGTH].strip("-.")

    return cleaned


def build_task_filename(task_id: str, title: str) -> str:
    """Return a safe ``TASK-###-slug.md`` filename."""
    slug = _safe_slug(title)
    return f"{task_id}-{slug}.md"


# ---------------------------------------------------------------------------
# Task rendering
# ---------------------------------------------------------------------------


def _render_list(items: list[str]) -> str:
    """Render a list of items as markdown bullets."""
    if not items:
        return "None."
    return "\n".join(f"- {item}" for item in items)


def _render_scope(paths: list[str]) -> str:
    """Render allowed changed-file scope as backtick-quoted bullets."""
    if not paths:
        return "None."
    return "\n".join(f"- `{path}`" for path in paths)


def render_task_markdown(task_id: str, title: str, proposal: GoalTaskProposal) -> str:
    """Render the canonical runner-owned DRAFT task markdown."""
    owner_decisions_text = _render_list(proposal.owner_decisions)
    if not proposal.owner_decisions:
        owner_decisions_text = "None."

    return f"""# {task_id} — {title}

STATUS: DRAFT

## Objective

{proposal.objective}

## Business context

{proposal.business_context}

## Facts

{_render_list(proposal.facts)}

## Assumptions

{_render_list(proposal.assumptions)}

## In scope

{_render_list(proposal.in_scope)}

## Explicitly out of scope

{_render_list(proposal.out_of_scope)}

## Allowed changed-file scope

{_render_scope(proposal.allowed_changed_file_scope)}

## Database impact

{proposal.database_impact}

## Safety requirements

- GitHub remains the source-of-truth.
- `main` remains untouched and non-executable unless explicitly approved.
- Worker/swarm cannot approve its own work.
- No automatic staging, commit, push, merge, tag, deploy, switch, reset,
  rebase, or history rewrite.
- This generated task is DRAFT and cannot execute until a valid
  `DRAFT -> READY` controller/owner transition.
- Unknown, unsafe, malformed, conflicting, or ambiguous states fail closed.
- The planner proposed only; the runner constructed this DRAFT; the
  controller/owner must authorize execution.

## Acceptance criteria

{_render_list(proposal.acceptance_criteria)}

## Test requirements

{_render_list(proposal.test_requirements)}

## Constraints

{_render_list(proposal.constraints_safety_requirements)}

## Owner decisions

{owner_decisions_text}

## Completion report

### Implemented

### Files changed

### Database changes

### Tests executed and results

### Assumptions

### Risks / unresolved issues

### Decisions required

### Recommended next step
"""


# ---------------------------------------------------------------------------
# Artifact writing
# ---------------------------------------------------------------------------


GOAL_TASK_SUBDIR = "goal_task"
GOAL_TASK_ARTIFACT_FILENAME = "goal_task.jsonl"


def default_goal_task_dir(repo_root: Path) -> Path:
    """Return the default goal-task artifact directory for *repo_root*."""
    return repo_root / ".agent_runner" / GOAL_TASK_SUBDIR


def build_goal_task_artifact_payload(
    result: GoalTaskGenerationResult,
    goal: OwnerGoal,
) -> dict[str, Any]:
    """Return bounded, JSON-safe metadata for a goal-task generation attempt.

    The payload intentionally excludes full planner transcripts, environment
    dumps, credentials, and the full owner goal text.  It records only enough
    metadata to audit the attempt.
    """
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "goal_hash": _hash_goal(goal.normalized),
        "goal_summary": _short_summary(goal.normalized),
        "goal_accepted": goal.accepted,
        "planner_type": result.planner_type,
        "planner_success": result.planner_success,
        "proposal_schema_version": PROPOSAL_SCHEMA_VERSION,
        "proposal_valid": result.proposal_valid,
        "assigned_task_id": result.task_id,
        "assigned_task_path": str(result.task_path) if result.task_path else None,
        "task_written": result.task_written,
        "pre_branch": result.pre_snapshot.git_info.current_branch
        if result.pre_snapshot
        else None,
        "pre_head": result.pre_snapshot.git_info.head_sha
        if result.pre_snapshot
        else None,
        "post_branch": result.post_snapshot.git_info.current_branch
        if result.post_snapshot
        else None,
        "post_head": result.post_snapshot.git_info.head_sha
        if result.post_snapshot
        else None,
        "validation_result": result.status.value,
        "owner_decision_count": result.owner_decision_count,
        "no_publication_performed": result.no_publication_performed,
        "next_action": result.next_action,
        "messages": list(result.messages or []),
    }
    if result.primary_planner in APPROVED_PLANNER_NAMES:
        payload.update({
            "primary_planner": result.primary_planner,
            "fallback_planner": result.fallback_planner,
            "terminal_planner": result.terminal_planner,
            "planner_timeout_seconds": result.planner_timeout_seconds,
            "failure_classification": result.failure_classification,
            "integrity_ok": result.integrity_ok,
            "fallback_used": result.fallback_used,
            "recovery_evidence": list(result.recovery_evidence),
        })
    return payload


class GoalTaskArtifactWriteError(Exception):
    """Raised when a goal-task artifact cannot be written durably."""


def write_goal_task_artifact(
    payload: dict[str, Any],
    artifact_dir: Path,
) -> Path:
    """Append *payload* as one JSON Lines record under *artifact_dir*.

    Raises:
        GoalTaskArtifactWriteError: if the artifact cannot be written.
    """
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise GoalTaskArtifactWriteError(
            f"Failed to create goal-task artifact directory {artifact_dir}: {exc}"
        ) from exc

    path = artifact_dir / GOAL_TASK_ARTIFACT_FILENAME
    line = json.dumps(payload, separators=(",", ":"), default=str, sort_keys=True) + "\n"

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        raise GoalTaskArtifactWriteError(
            f"Failed to write goal-task artifact to {path}: {exc}"
        ) from exc

    return path


# ---------------------------------------------------------------------------
# Consolidated report formatting
# ---------------------------------------------------------------------------


def format_goal_task_report(result: GoalTaskGenerationResult) -> str:
    """Return a controller-ready consolidated report for *result*."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("AdvanCore Goal-to-Task Generation — Consolidated Report")
    lines.append("=" * 72)

    lines.append(f"Goal accepted:     {'yes' if result.goal_accepted else 'no'}")
    lines.append(f"Planner type:      {result.planner_type or 'n/a'}")
    lines.append(f"Fallback planner:  {result.fallback_planner or 'none'}")
    lines.append(f"Terminal planner:  {result.terminal_planner or 'n/a'}")
    lines.append(
        f"Planner success:   {result.planner_success if result.planner_success is not None else 'n/a'}"
    )
    lines.append(f"Proposal valid:    {'yes' if result.proposal_valid else 'no'}")
    lines.append(f"Assigned task ID:  {result.task_id or 'n/a'}")
    lines.append(
        f"Assigned task path: {result.task_path if result.task_path else 'n/a'}"
    )
    lines.append(f"Generated state:   DRAFT")
    lines.append(
        f"Owner decisions:   {result.owner_decision_count} requiring review"
    )

    if result.pre_snapshot and result.post_snapshot:
        pre = result.pre_snapshot.git_info
        post = result.post_snapshot.git_info
        lines.append(f"Pre branch:        {pre.current_branch}")
        lines.append(f"Pre HEAD:          {pre.head_sha}")
        lines.append(f"Post branch:       {post.current_branch}")
        lines.append(f"Post HEAD:         {post.head_sha}")
        lines.append(
            f"Repository integrity: {'PASS' if result.ok else 'FAIL'}"
        )
    else:
        lines.append("Repository integrity: n/a")

    lines.append(
        f"Task file written: {'yes' if result.task_written else 'no'}"
    )
    lines.append(
        f"Artifact path:     {result.artifact_path if result.artifact_path else 'n/a'}"
    )
    lines.append(
        "Publication state: NO staging / commit / push / merge / deploy / "
        "approval performed"
    )
    lines.append(f"Next action:       {result.next_action}")

    lines.append("-" * 72)
    lines.append("Messages:")
    for msg in result.messages:
        lines.append(f"  {msg}")
    lines.append("=" * 72)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------


def _create_result(
    status: GoalTaskGenerationStatus,
    *,
    ok: bool = False,
    goal: OwnerGoal | None = None,
    planner_type: str | None = None,
    planner_success: bool | None = None,
    fallback_planner: str | None = None,
    planner_timeout_seconds: int | None = None,
    proposal_valid: bool = False,
    task_id: str | None = None,
    task_path: Path | None = None,
    task_written: bool = False,
    pre_snapshot: RepositorySnapshot | None = None,
    post_snapshot: RepositorySnapshot | None = None,
    owner_decision_count: int = 0,
    messages: list[str] | None = None,
) -> GoalTaskGenerationResult:
    """Build a ``GoalTaskGenerationResult`` with sensible defaults."""
    return GoalTaskGenerationResult(
        ok=ok,
        status=status,
        goal_accepted=goal.accepted if goal else False,
        planner_type=planner_type,
        planner_success=planner_success,
        primary_planner=planner_type,
        fallback_planner=fallback_planner,
        terminal_planner=planner_type,
        planner_timeout_seconds=planner_timeout_seconds,
        proposal_valid=proposal_valid,
        task_id=task_id,
        task_path=task_path,
        task_written=task_written,
        pre_snapshot=pre_snapshot,
        post_snapshot=post_snapshot,
        owner_decision_count=owner_decision_count,
        no_publication_performed=True,
        messages=messages or [],
    )


def _maybe_write_artifact(
    result: GoalTaskGenerationResult,
    goal: OwnerGoal,
    repo_root: Path,
) -> None:
    """Write the bounded audit artifact if the repository snapshot is available."""
    if result.pre_snapshot is None:
        result.messages.append("Artifact: not written (no repository snapshot)")
        return

    payload = build_goal_task_artifact_payload(result, goal)
    try:
        artifact_path = write_goal_task_artifact(
            payload, default_goal_task_dir(repo_root)
        )
        result.artifact_path = artifact_path
        rel_path = artifact_path.relative_to(repo_root)
        result.messages.append(f"Artifact written to {rel_path}")
    except GoalTaskArtifactWriteError as exc:
        result.messages.append(f"WARNING: could not write artifact: {exc}")


def _launch_planner(
    repo_root: Path,
    goal: OwnerGoal,
    planner: WorkerAdapter,
) -> WorkerResult:
    """Build the planner instruction and invoke *planner*."""
    instruction = build_planner_instruction(goal.normalized)
    return planner.run(instruction, repo_root)


def _classify_planner_failure(result: WorkerResult) -> str:
    """Classify only deterministic local provider availability failures."""
    if result.terminal_reason in {"timeout", "cancelled"}:
        return result.terminal_reason.upper()
    evidence = " ".join(
        value for value in (result.message, result.stdout, result.stderr) if value
    ).lower()[:4000]
    if "not found in path" in evidence or "no such file or directory" in evidence:
        return "EXECUTABLE_UNAVAILABLE"
    if any(token in evidence for token in (
        "quota", "rate limit", "rate-limit", "capacity", "overloaded",
        "resource exhausted", "too many requests",
    )):
        return "QUOTA_OR_CAPACITY"
    if any(token in evidence for token in (
        "authentication unavailable", "not authenticated", "authentication required",
        "unauthorized", "invalid api key", "login required",
    )):
        return "AUTHENTICATION_UNAVAILABLE"
    return "UNKNOWN"


_FALLBACK_ELIGIBLE = {
    "EXECUTABLE_UNAVAILABLE", "QUOTA_OR_CAPACITY", "AUTHENTICATION_UNAVAILABLE"
}


def generate_goal_task(
    repo_root: Path,
    tasks_dir: Path,
    goal: str,
    planner: WorkerAdapter,
    *,
    execute: bool = False,
    fallback_planner: WorkerAdapter | None = None,
) -> GoalTaskGenerationResult:
    """Convert *goal* into a deterministic ``STATUS: DRAFT`` task file.

    Arguments:
        repo_root: Repository root path.
        tasks_dir: Directory containing ``TASK-###-name.md`` files.
        goal: Raw natural-language owner goal.
        planner: Replaceable planner worker adapter.
        execute: If ``True``, invoke the planner and write the DRAFT task file
            after all validations pass.  If ``False``, perform a dry-run: no
            planner is launched and no task file is written.

    Returns:
        A ``GoalTaskGenerationResult`` describing the outcome.  The result is
        truthy only when a DRAFT task file was successfully created.
    """
    owner_goal = validate_owner_goal(goal)
    if not owner_goal.accepted:
        result = _create_result(
            GoalTaskGenerationStatus.VALIDATION_FAILED,
            goal=owner_goal,
            planner_type=planner.name, fallback_planner=fallback_planner.name if fallback_planner else None,
            messages=owner_goal.messages
            + ["Goal rejected; no task file created."],
        )
        return result

    # Capture repository snapshot early for both dry-run and execute modes.
    try:
        pre_snapshot = capture_repository_snapshot(repo_root)
    except Exception as exc:
        result = _create_result(
            GoalTaskGenerationStatus.PRECONDITION_FAILED,
            goal=owner_goal,
            planner_type=planner.name,
            messages=[f"FAIL: cannot inspect repository: {exc}"],
        )
        return result

    if execute:
        # Planner execution requires a non-main branch and a clean worktree.
        if pre_snapshot.git_info.current_branch == "main":
            result = _create_result(
                GoalTaskGenerationStatus.PRECONDITION_FAILED,
                goal=owner_goal,
                planner_type=planner.name,
                pre_snapshot=pre_snapshot,
                messages=["FAIL: goal-task generation on 'main' is not allowed"],
            )
            _maybe_write_artifact(result, owner_goal, repo_root)
            return result

        if not pre_snapshot.git_info.is_clean:
            result = _create_result(
                GoalTaskGenerationStatus.PRECONDITION_FAILED,
                goal=owner_goal,
                planner_type=planner.name,
                pre_snapshot=pre_snapshot,
                messages=["FAIL: working tree is not clean"],
            )
            _maybe_write_artifact(result, owner_goal, repo_root)
            return result

    # Determine the next task ID deterministically in both modes so dry-runs
    # can report it.
    try:
        next_task_id = assign_next_task_id(tasks_dir)
    except Exception as exc:
        result = _create_result(
            GoalTaskGenerationStatus.TASK_ID_COLLISION,
            goal=owner_goal,
            planner_type=planner.name,
            pre_snapshot=pre_snapshot,
            messages=[f"FAIL: could not assign next task ID: {exc}"],
        )
        _maybe_write_artifact(result, owner_goal, repo_root)
        return result

    if not execute:
        result = _create_result(
            GoalTaskGenerationStatus.DRY_RUN,
            goal=owner_goal,
            planner_type=planner.name,
            task_id=next_task_id,
            pre_snapshot=pre_snapshot,
            messages=owner_goal.messages
            + [
                f"Dry-run: next candidate task ID is {next_task_id}",
                "Dry-run: planner would not be launched",
                "Dry-run: no task file will be written",
            ],
        )
        return result

    # Execute mode: launch the planner and validate its output.
    result = _create_result(
        GoalTaskGenerationStatus.PLANNER_FAILED,
        goal=owner_goal,
        planner_type=planner.name,
        fallback_planner=fallback_planner.name if fallback_planner else None,
        planner_timeout_seconds=getattr(planner, "timeout_seconds", None),
        task_id=next_task_id,
        pre_snapshot=pre_snapshot,
        messages=owner_goal.messages
        + [f"Next candidate task ID: {next_task_id}", "Launching planner..."],
    )

    planner_result = _launch_planner(repo_root, owner_goal, planner)
    result.planner_success = planner_result.success
    result.messages.append(
        f"Planner finished: success={planner_result.success}; {planner_result.message}"
    )

    try:
        post_snapshot = capture_repository_snapshot(repo_root)
    except Exception as exc:
        result.failure_classification = "INTEGRITY_AMBIGUOUS"
        result.messages.append(f"FAIL: could not capture post-planner repository snapshot: {exc}")
        _maybe_write_artifact(result, owner_goal, repo_root)
        return result
    result.post_snapshot = post_snapshot
    mutation_messages = detect_repository_mutation(pre_snapshot, post_snapshot)
    result.integrity_ok = not mutation_messages
    result.recovery_evidence = [
        f"branch_unchanged={pre_snapshot.git_info.current_branch == post_snapshot.git_info.current_branch}",
        f"head_unchanged={pre_snapshot.git_info.head_sha == post_snapshot.git_info.head_sha}",
        f"index_worktree_clean={post_snapshot.git_info.is_clean}",
        f"remotes_unchanged={pre_snapshot.remote_urls == post_snapshot.remote_urls}",
    ]
    if mutation_messages:
        result.status = GoalTaskGenerationStatus.MUTATION_DETECTED
        result.failure_classification = "REPOSITORY_MUTATION"
        result.messages.extend(mutation_messages)
        result.messages.append("FAIL: planner mutated the repository; fallback and task write prohibited")
        _maybe_write_artifact(result, owner_goal, repo_root)
        return result

    if not planner_result.success:
        result.failure_classification = _classify_planner_failure(planner_result)
        if fallback_planner is None or result.failure_classification not in _FALLBACK_ELIGIBLE:
            result.messages.append("FAIL: planner failure is not eligible for fallback")
            _maybe_write_artifact(result, owner_goal, repo_root)
            return result
        result.fallback_used = True
        result.terminal_planner = fallback_planner.name
        result.planner_timeout_seconds = getattr(fallback_planner, "timeout_seconds", None)
        result.messages.append(
            f"Fallback authorized once: {planner.name} -> {fallback_planner.name}"
        )
        planner_result = _launch_planner(repo_root, owner_goal, fallback_planner)
        result.planner_success = planner_result.success
        try:
            fallback_post = capture_repository_snapshot(repo_root)
        except Exception as exc:
            result.integrity_ok = False
            result.messages.append(f"FAIL: fallback integrity capture failed: {exc}")
            _maybe_write_artifact(result, owner_goal, repo_root)
            return result
        result.post_snapshot = fallback_post
        fallback_mutations = detect_repository_mutation(pre_snapshot, fallback_post)
        result.integrity_ok = not fallback_mutations
        if fallback_mutations:
            result.status = GoalTaskGenerationStatus.MUTATION_DETECTED
            result.messages.extend(fallback_mutations)
            _maybe_write_artifact(result, owner_goal, repo_root)
            return result
        if not planner_result.success:
            result.failure_classification = _classify_planner_failure(planner_result)
            result.messages.append("FAIL: fallback planner failed; no further hop permitted")
            _maybe_write_artifact(result, owner_goal, repo_root)
            return result

    # Parse and validate the proposal.
    raw_output = ""
    if planner_result.stdout:
        raw_output = planner_result.stdout
    elif planner_result.stderr:
        raw_output = planner_result.stderr

    try:
        proposal_data = parse_planner_output(raw_output)
        proposal = validate_proposal(proposal_data)
        result.proposal_valid = True
        result.messages.append("PASS: planner proposal parsed and validated")
    except ProposalError as exc:
        result.status = GoalTaskGenerationStatus.PROPOSAL_REJECTED
        result.messages.append(f"FAIL: proposal rejected: {exc}")
        _maybe_write_artifact(result, owner_goal, repo_root)
        return result

    result.messages.append("PASS: no planner repository mutation detected")

    # Assign filename and guard against collisions.
    filename = build_task_filename(next_task_id, proposal.title)
    task_path = tasks_dir / filename

    if task_path.exists():
        result.status = GoalTaskGenerationStatus.TASK_ID_COLLISION
        result.messages.append(
            f"FAIL: target task path already exists: {task_path.name}"
        )
        _maybe_write_artifact(result, owner_goal, repo_root)
        return result

    # Render and write the canonical DRAFT task.
    markdown = render_task_markdown(next_task_id, proposal.title, proposal)
    try:
        tasks_dir.mkdir(parents=True, exist_ok=True)
        task_path.write_text(markdown, encoding="utf-8")
    except Exception as exc:
        result.messages.append(f"FAIL: could not write task file: {exc}")
        _maybe_write_artifact(result, owner_goal, repo_root)
        return result

    result.task_id = next_task_id
    result.task_path = task_path
    result.task_written = True
    result.status = GoalTaskGenerationStatus.DRAFT_CREATED
    result.ok = True
    result.owner_decision_count = len(proposal.owner_decisions)
    result.messages.append(f"PASS: wrote DRAFT task file {task_path.name}")
    result.messages.append(
        "Generated task is DRAFT and cannot execute until controller/owner "
        "transitions it to READY."
    )
    result.messages.append(
        "No staging, commit, push, merge, deploy, or approval was performed."
    )

    _maybe_write_artifact(result, owner_goal, repo_root)
    return result
