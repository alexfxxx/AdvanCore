"""Controller transport envelope for the local agent runner.

A controller transport envelope is a deterministic, bounded, transport-neutral
JSON wrapper around the existing TASK-013/TASK-014 controller-adapter boundary.
It defines a versioned request/response contract so that a future remote
controller transport can exchange safe artifacts without redesigning controller
authority, handoff, decision, lifecycle, or Git-publication semantics.

The envelope is data exchange only. It is NOT controller authority. It never
makes a worker a controller, infers ``APPROVE``, treats ``DECISION_RECEIVED`` as
sufficient authority without a separately valid TASK-011 decision record, or
bypasses TASK-012/TASK-013/TASK-014 validation and reconciliation.

This module does not implement HTTP, webhooks, sockets, queues, background
polling, model calls, credential handling, or subprocess transport.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_controller_transport_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.controller_adapter import (
    AdapterResultState,
    ControllerAdapterResult,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoff,
    ControllerHandoffError,
    HandoffState,
    load_controller_handoff,
    reconcile_controller_handoff,
)
from advancore.agent_runner.git_info import GitInfo


TRANSPORT_SUBDIR = "controller_transport"
TRANSPORT_ENVELOPE_VERSION = "1"
TRANSPORT_REQUEST_SCHEMA = "advancore.controller.transport.request"
TRANSPORT_RESPONSE_SCHEMA = "advancore.controller.transport.response"


class ControllerTransportError(Exception):
    """Raised when a transport envelope cannot be built, validated, or loaded."""


class ControllerTransportWriteError(Exception):
    """Raised when a transport envelope cannot be written durably."""


class ControllerTransportValidationError(ControllerTransportError):
    """Raised when a transport envelope fails schema or correlation validation."""


@dataclass
class ControllerTransportRequest:
    """Versioned, bounded request envelope sent to a controller transport.

    The request carries only safe references and metadata already authorized by
    TASK-010/TASK-013/TASK-014. It never includes full task bodies, worker
    transcripts, credentials, environment dumps, secrets, customer data, or
    arbitrary repository contents.
    """

    envelope_version: str
    schema: str
    request_id: str
    timestamp: str
    task_id: str
    task_filename: str
    handoff_request_path: str
    handoff_request_id: str
    review_bundle_path: str
    adapter_name: str
    adapter_type: str | None
    bundle_branch: str
    bundle_pre_head: str
    bundle_post_head: str | None
    bundle_recommended_action: str
    handoff_state: str
    messages: list[str] = field(default_factory=list)


@dataclass
class ControllerTransportResponse:
    """Versioned, bounded response envelope returned from a controller transport.

    The response carries only the matching correlation ID, task identity, a
    bounded result state, an optional controller-decision record reference, and
    bounded messages. It is never itself an approval or lifecycle authorization.
    """

    envelope_version: str
    schema: str
    request_id: str
    timestamp: str
    task_id: str
    task_filename: str
    handoff_request_path: str
    review_bundle_path: str
    result_state: str
    decision_path: str | None = None
    decision: str | None = None
    messages: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Path and filename helpers
# ---------------------------------------------------------------------------


def default_transport_dir(repo_root: Path) -> Path:
    """Return the default controller-transport directory for *repo_root*."""
    return repo_root / ".agent_runner" / TRANSPORT_SUBDIR


def _sanitize_filename(value: str | None) -> str:
    """Return a filesystem-safe fragment from *value*."""
    if not value:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9_\-]", "_", value)[:64]


def _generate_request_id() -> str:
    """Return a short, unique transport request identifier."""
    return f"CTE-{uuid.uuid4().hex}"


def _resolve_under_repo(path_value: str, repo_root: Path | None) -> Path:
    """Resolve *path_value* against *repo_root* and return an absolute path.

    Raises:
        ControllerTransportError: if the path escapes the repository root or
            contains traversal components.
    """
    if repo_root is None:
        return Path(path_value).resolve()

    repo_root = repo_root.resolve()
    path = Path(path_value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    else:
        path = path.resolve()

    # Reject traversal attempts such as ".." that resolve outside repo_root.
    try:
        path.relative_to(repo_root)
    except ValueError as exc:
        raise ControllerTransportError(
            f"Path escapes repository root: {path_value}"
        ) from exc

    return path


def _normalize_relative_path(path_value: str, repo_root: Path | None) -> str:
    """Return a repository-relative path when possible for portability."""
    stored = path_value
    if repo_root is not None:
        try:
            stored = str(
                _resolve_under_repo(path_value, repo_root).relative_to(
                    repo_root.resolve()
                )
            )
        except ControllerTransportError:
            pass
    return stored


# ---------------------------------------------------------------------------
# Request envelope builders and serializers
# ---------------------------------------------------------------------------


def build_transport_request(
    handoff_path: Path,
    handoff: ControllerHandoff,
    adapter_name: str,
    *,
    adapter_type: str | None = None,
    repo_root: Path | None = None,
) -> ControllerTransportRequest:
    """Build a bounded transport request envelope from a validated handoff.

    Arguments:
        handoff_path: Path to the source handoff request. Stored as a
            repository-relative path when *repo_root* is supplied and the path
            is inside it.
        handoff: The loaded ``ControllerHandoff`` to wrap.
        adapter_name: Name of the controller adapter that will receive the
            envelope (e.g. ``manual``).
        adapter_type: Optional transport adapter type hint (e.g. ``local``,
            ``remote``). Defaults to ``None``.
        repo_root: Optional repository root used to make paths relative.

    Raises:
        ControllerTransportError: if required handoff linkage evidence is
            missing or inconsistent.
    """
    task_id = _require_handoff_field("task_id", handoff.task_id)
    task_filename = _require_handoff_field(
        "task_filename", handoff.task_filename
    )
    bundle_path = _require_handoff_field("bundle_path", handoff.bundle_path)
    request_id = _require_handoff_field("request_id", handoff.request_id)
    bundle_branch = _require_handoff_field("bundle_branch", handoff.bundle_branch)
    bundle_pre_head = _require_handoff_field("bundle_pre_head", handoff.bundle_pre_head)

    if handoff.state not in {s.value for s in HandoffState}:
        raise ControllerTransportError(
            f"Unsupported handoff state for transport: {handoff.state!r}"
        )

    stored_handoff_path = _normalize_relative_path(str(handoff_path), repo_root)
    stored_bundle_path = _normalize_relative_path(bundle_path, repo_root)

    return ControllerTransportRequest(
        envelope_version=TRANSPORT_ENVELOPE_VERSION,
        schema=TRANSPORT_REQUEST_SCHEMA,
        request_id=_generate_request_id(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        task_id=task_id,
        task_filename=task_filename,
        handoff_request_path=stored_handoff_path,
        handoff_request_id=request_id,
        review_bundle_path=stored_bundle_path,
        adapter_name=adapter_name,
        adapter_type=adapter_type,
        bundle_branch=bundle_branch,
        bundle_pre_head=bundle_pre_head,
        bundle_post_head=handoff.bundle_post_head,
        bundle_recommended_action=handoff.bundle_recommended_action,
        handoff_state=handoff.state,
        messages=[
            f"Transport request prepared for {task_id} from {stored_handoff_path}"
        ],
    )


def _require_handoff_field(name: str, value: str | None) -> str:
    """Return *value* if it is a non-empty string, else raise."""
    if not value or not isinstance(value, str):
        raise ControllerTransportError(
            f"Handoff request is missing required transport field: {name}"
        )
    return value


def serialize_transport_request(request: ControllerTransportRequest) -> dict[str, Any]:
    """Return a deterministic JSON-serializable dict for *request*."""
    data = asdict(request)
    data["envelope_version"] = str(request.envelope_version)
    data["schema"] = str(request.schema)
    data["request_id"] = str(request.request_id)
    data["handoff_state"] = str(request.handoff_state)
    data["bundle_recommended_action"] = str(request.bundle_recommended_action)
    return data


def write_transport_request(
    request: ControllerTransportRequest,
    transport_dir: Path,
) -> Path:
    """Write *request* as JSON under *transport_dir* and return the path.

    Raises:
        ControllerTransportWriteError: if the envelope cannot be written.
    """
    try:
        transport_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise ControllerTransportWriteError(
            f"Failed to create transport directory {transport_dir}: {exc}"
        ) from exc

    ts = datetime.fromisoformat(request.timestamp).strftime("%Y%m%dT%H%M%S")
    task_part = _sanitize_filename(request.task_id)
    request_part = _sanitize_filename(request.request_id)
    filename = f"{ts}_{task_part}_{request_part}_request.json"

    # Defensive path-traversal guard on the generated filename.
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ControllerTransportWriteError(
            f"Refusing to write transport request with unsafe filename: {filename}"
        )

    path = transport_dir / filename
    payload = serialize_transport_request(request)
    try:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise ControllerTransportWriteError(
            f"Failed to write transport request to {path}: {exc}"
        ) from exc

    return path


def load_transport_request(path: Path) -> ControllerTransportRequest:
    """Load a ``ControllerTransportRequest`` from *path*.

    Raises:
        ControllerTransportError: if the file cannot be read or parsed.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControllerTransportError(
            f"Cannot read transport request {path}: {exc}"
        ) from exc

    return validate_transport_request(data)


def validate_transport_request(
    data: dict[str, Any],
    *,
    expected_request_id: str | None = None,
) -> ControllerTransportRequest:
    """Validate *data* and return a ``ControllerTransportRequest``.

    Raises:
        ControllerTransportValidationError: if the envelope is malformed, has an
            unknown version/schema, is missing required fields, or fails
            correlation checks.
    """
    _validate_envelope_header(
        data,
        expected_version=TRANSPORT_ENVELOPE_VERSION,
        expected_schema=TRANSPORT_REQUEST_SCHEMA,
    )

    required = {
        "request_id",
        "timestamp",
        "task_id",
        "task_filename",
        "handoff_request_path",
        "handoff_request_id",
        "review_bundle_path",
        "adapter_name",
        "bundle_branch",
        "bundle_pre_head",
        "bundle_recommended_action",
        "handoff_state",
    }
    missing = required - set(data.keys())
    if missing:
        raise ControllerTransportValidationError(
            f"Transport request missing required fields: {sorted(missing)}"
        )

    if expected_request_id is not None and data["request_id"] != expected_request_id:
        raise ControllerTransportValidationError(
            f"Transport request ID mismatch: expected {expected_request_id!r}, "
            f"got {data['request_id']!r}"
        )

    if data["handoff_state"] not in {s.value for s in HandoffState}:
        raise ControllerTransportValidationError(
            f"Unknown handoff state in transport request: {data['handoff_state']!r}"
        )

    try:
        return ControllerTransportRequest(**data)
    except Exception as exc:
        raise ControllerTransportValidationError(
            f"Invalid transport request format: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Response envelope builders and serializers
# ---------------------------------------------------------------------------


def build_transport_response(
    request: ControllerTransportRequest,
    state: str | AdapterResultState,
    *,
    decision_path: str | None = None,
    decision: str | None = None,
    messages: list[str] | None = None,
) -> ControllerTransportResponse:
    """Build a bounded transport response envelope from a request and state.

    Arguments:
        request: The transport request envelope this response answers.
        state: One of ``PENDING``, ``DECISION_RECEIVED``, or ``BLOCKED``.
        decision_path: Optional controller-decision record reference when
            *state* is ``DECISION_RECEIVED``.
        decision: Optional decision value when *state* is ``DECISION_RECEIVED``.
        messages: Optional bounded human-readable messages.

    Raises:
        ControllerTransportError: if *state* is unknown.
    """
    state_value = state.value if isinstance(state, AdapterResultState) else state
    if state_value not in {s.value for s in AdapterResultState}:
        raise ControllerTransportError(
            f"Unknown transport response state: {state_value!r}. "
            f"Allowed values are: {', '.join(s.value for s in AdapterResultState)}."
        )

    return ControllerTransportResponse(
        envelope_version=TRANSPORT_ENVELOPE_VERSION,
        schema=TRANSPORT_RESPONSE_SCHEMA,
        request_id=request.request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        task_id=request.task_id,
        task_filename=request.task_filename,
        handoff_request_path=request.handoff_request_path,
        review_bundle_path=request.review_bundle_path,
        result_state=state_value,
        decision_path=decision_path,
        decision=decision,
        messages=list(messages or []),
    )


def serialize_transport_response(
    response: ControllerTransportResponse,
) -> dict[str, Any]:
    """Return a deterministic JSON-serializable dict for *response*."""
    data = asdict(response)
    data["envelope_version"] = str(response.envelope_version)
    data["schema"] = str(response.schema)
    data["request_id"] = str(response.request_id)
    data["result_state"] = str(response.result_state)
    return data


def write_transport_response(
    response: ControllerTransportResponse,
    transport_dir: Path,
) -> Path:
    """Write *response* as JSON under *transport_dir* and return the path.

    Raises:
        ControllerTransportWriteError: if the envelope cannot be written.
    """
    try:
        transport_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise ControllerTransportWriteError(
            f"Failed to create transport directory {transport_dir}: {exc}"
        ) from exc

    ts = datetime.fromisoformat(response.timestamp).strftime("%Y%m%dT%H%M%S")
    task_part = _sanitize_filename(response.task_id)
    request_part = _sanitize_filename(response.request_id)
    filename = f"{ts}_{task_part}_{request_part}_response.json"

    if ".." in filename or "/" in filename or "\\" in filename:
        raise ControllerTransportWriteError(
            f"Refusing to write transport response with unsafe filename: {filename}"
        )

    path = transport_dir / filename
    payload = serialize_transport_response(response)
    try:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        raise ControllerTransportWriteError(
            f"Failed to write transport response to {path}: {exc}"
        ) from exc

    return path


def load_transport_response(path: Path) -> ControllerTransportResponse:
    """Load a ``ControllerTransportResponse`` from *path*.

    Raises:
        ControllerTransportError: if the file cannot be read or parsed.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControllerTransportError(
            f"Cannot read transport response {path}: {exc}"
        ) from exc

    return validate_transport_response(data)


def validate_transport_response(
    data: dict[str, Any],
    *,
    expected_request_id: str | None = None,
    expected_task_id: str | None = None,
    expected_handoff_path: str | None = None,
    expected_bundle_path: str | None = None,
) -> ControllerTransportResponse:
    """Validate *data* and return a ``ControllerTransportResponse``.

    Raises:
        ControllerTransportValidationError: if the envelope is malformed, has an
            unknown version/schema/state, is missing required fields, or fails
            correlation/reference checks.
    """
    _validate_envelope_header(
        data,
        expected_version=TRANSPORT_ENVELOPE_VERSION,
        expected_schema=TRANSPORT_RESPONSE_SCHEMA,
    )

    required = {
        "request_id",
        "timestamp",
        "task_id",
        "task_filename",
        "handoff_request_path",
        "review_bundle_path",
        "result_state",
    }
    missing = required - set(data.keys())
    if missing:
        raise ControllerTransportValidationError(
            f"Transport response missing required fields: {sorted(missing)}"
        )

    if data["result_state"] not in {s.value for s in AdapterResultState}:
        raise ControllerTransportValidationError(
            f"Unknown transport response state: {data['result_state']!r}"
        )

    if expected_request_id is not None and data["request_id"] != expected_request_id:
        raise ControllerTransportValidationError(
            f"Transport response request ID mismatch: expected {expected_request_id!r}, "
            f"got {data['request_id']!r}"
        )

    if expected_task_id is not None and data["task_id"] != expected_task_id:
        raise ControllerTransportValidationError(
            f"Transport response task ID mismatch: expected {expected_task_id!r}, "
            f"got {data['task_id']!r}"
        )

    if (
        expected_handoff_path is not None
        and data["handoff_request_path"] != expected_handoff_path
    ):
        raise ControllerTransportValidationError(
            f"Transport response handoff path mismatch: expected {expected_handoff_path!r}, "
            f"got {data['handoff_request_path']!r}"
        )

    if (
        expected_bundle_path is not None
        and data["review_bundle_path"] != expected_bundle_path
    ):
        raise ControllerTransportValidationError(
            f"Transport response bundle path mismatch: expected {expected_bundle_path!r}, "
            f"got {data['review_bundle_path']!r}"
        )

    try:
        return ControllerTransportResponse(**data)
    except Exception as exc:
        raise ControllerTransportValidationError(
            f"Invalid transport response format: {exc}"
        ) from exc


def _validate_envelope_header(
    data: dict[str, Any],
    *,
    expected_version: str,
    expected_schema: str,
) -> None:
    """Fail closed if the envelope header is missing, malformed, or unknown."""
    if not isinstance(data, dict):
        raise ControllerTransportValidationError(
            "Transport envelope must be a JSON object"
        )

    version = data.get("envelope_version")
    if version != expected_version:
        raise ControllerTransportValidationError(
            f"Unknown transport envelope version: {version!r} "
            f"(expected {expected_version!r})"
        )

    schema = data.get("schema")
    if schema != expected_schema:
        raise ControllerTransportValidationError(
            f"Unknown transport envelope schema: {schema!r} "
            f"(expected {expected_schema!r})"
        )


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


def handoff_to_transport_request(
    handoff_path: Path,
    handoff: ControllerHandoff,
    adapter_name: str,
    *,
    adapter_type: str | None = None,
    repo_root: Path | None = None,
) -> ControllerTransportRequest:
    """Convert a validated TASK-013/TASK-014 handoff into a request envelope.

    This is a convenience alias for ``build_transport_request`` that preserves
    the existing authority semantics: the handoff is transport data, not a
    controller decision or approval.
    """
    return build_transport_request(
        handoff_path=handoff_path,
        handoff=handoff,
        adapter_name=adapter_name,
        adapter_type=adapter_type,
        repo_root=repo_root,
    )


def convert_response_to_adapter_result(
    response: ControllerTransportResponse,
) -> ControllerAdapterResult:
    """Convert a valid response envelope into a bounded adapter result.

    The returned result carries the same bounded metadata and state. It does not
    perform any reconciliation or authority mutation; callers that need to
    reconcile a returned decision should use ``apply_transport_response``.
    """
    return ControllerAdapterResult(
        adapter_name="transport",
        state=response.result_state,
        task_id=response.task_id,
        task_filename=response.task_filename,
        request_path=response.handoff_request_path,
        bundle_path=response.review_bundle_path,
        decision_path=response.decision_path,
        decision=response.decision,
        reconciled=False,
        messages=list(response.messages or []),
    )


def apply_transport_response(
    response: ControllerTransportResponse,
    *,
    repo_root: Path | None = None,
    git_info: GitInfo | None = None,
) -> ControllerAdapterResult:
    """Validate a response envelope and reconcile any returned decision.

    The helper:

    1. Converts the response to a bounded adapter result.
    2. If the result state is ``DECISION_RECEIVED`` and a decision path is
       present, resolves the source handoff path and decision path and
       reconciles them through the existing TASK-013 handoff reconciliation
       logic.
    3. Writes a local audit record when a Git snapshot is available.

    This helper does **not** invoke the TASK-012 lifecycle bridge and does not
    mutate task files, Git index/commits/branches/remotes, or database state. A
    ``DECISION_RECEIVED`` result is still only evidence of a returned decision;
    it is not itself an approval or lifecycle authorization.
    """
    result = convert_response_to_adapter_result(response)

    if (
        result.state == AdapterResultState.DECISION_RECEIVED.value
        and result.decision_path
    ):
        try:
            handoff_path = _resolve_under_repo(
                response.handoff_request_path, repo_root
            )
            decision_path = _resolve_under_repo(result.decision_path, repo_root)
        except ControllerTransportError as exc:
            result.state = AdapterResultState.BLOCKED.value
            result.messages.append(f"Cannot resolve transport paths: {exc}")
            _maybe_write_transport_audit(result, git_info)
            return result

        try:
            reconcile_result = reconcile_controller_handoff(
                request_path=handoff_path,
                decision_path=decision_path,
                repo_root=repo_root,
                git_info=git_info,
            )
        except ControllerHandoffError as exc:
            result.state = AdapterResultState.BLOCKED.value
            result.messages.append(f"Reconciliation failed: {exc}")
            _maybe_write_transport_audit(result, git_info)
            return result

        result.reconciled = reconcile_result.ok
        result.messages.extend(reconcile_result.messages)

        if reconcile_result.handoff is not None:
            result.decision = reconcile_result.handoff.decision
            result.decision_path = reconcile_result.handoff.decision_path

        if not reconcile_result.ok:
            result.state = AdapterResultState.BLOCKED.value
            result.messages.append(
                "Decision could not be reconciled; transport response treated as BLOCKED"
            )
            _maybe_write_transport_audit(result, git_info)
            return result

    _maybe_write_transport_audit(result, git_info)
    return result


def _maybe_write_transport_audit(
    result: ControllerAdapterResult,
    git_info: GitInfo | None,
) -> None:
    """Append a transport-specific audit record if a Git snapshot is available."""
    if git_info is None:
        return

    payload = build_controller_transport_audit_payload(
        timestamp=datetime.now(timezone.utc),
        task_id=result.task_id,
        task_filename=result.task_filename,
        request_id=None,
        state=result.state,
        request_path=result.request_path,
        bundle_path=result.bundle_path,
        decision_path=result.decision_path,
        decision=result.decision,
        reconciled=result.reconciled,
        branch=git_info.current_branch,
        head_sha=git_info.head_sha,
    )

    try:
        audit_path = write_audit_record(payload, default_audit_dir(git_info.repo_root))
        result.audit_path = str(audit_path)
        result.messages.append(f"Transport audit record written to {audit_path}")
    except AuditWriteError as exc:
        result.audit_write_ok = False
        result.audit_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def find_latest_transport_request(transport_dir: Path) -> Path | None:
    """Return the most recently modified request envelope under *transport_dir*."""
    if not transport_dir.exists():
        return None
    candidates = sorted(
        transport_dir.glob("*_request.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def find_latest_transport_response(transport_dir: Path) -> Path | None:
    """Return the most recently modified response envelope under *transport_dir*."""
    if not transport_dir.exists():
        return None
    candidates = sorted(
        transport_dir.glob("*_response.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_transport_request_summary(request: ControllerTransportRequest) -> str:
    """Return a concise, human-readable summary of *request*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Controller Transport Request Envelope")
    lines.append("=" * 64)
    lines.append(f"Request ID:    {request.request_id}")
    lines.append(f"Version:       {request.envelope_version}")
    lines.append(f"Schema:        {request.schema}")
    lines.append(f"Task:          {request.task_id or 'n/a'}")
    lines.append(f"File:          {request.task_filename or 'n/a'}")
    lines.append(f"Handoff:       {request.handoff_request_path}")
    lines.append(f"Handoff ID:    {request.handoff_request_id}")
    lines.append(f"Bundle:        {request.review_bundle_path}")
    lines.append(f"Adapter:       {request.adapter_name}")
    if request.adapter_type:
        lines.append(f"Adapter type:  {request.adapter_type}")
    lines.append(f"Branch:        {request.bundle_branch or 'n/a'}")
    lines.append(f"Pre HEAD:      {request.bundle_pre_head or 'n/a'}")
    lines.append(f"Post HEAD:     {request.bundle_post_head or 'n/a'}")
    lines.append(f"Recommended:   {request.bundle_recommended_action}")
    lines.append(f"Handoff state: {request.handoff_state}")
    if request.messages:
        lines.append("-" * 64)
        lines.append("Messages:")
        for msg in request.messages:
            lines.append(f"  {msg}")
    lines.append("=" * 64)
    return "\n".join(lines)


def format_transport_response_summary(response: ControllerTransportResponse) -> str:
    """Return a concise, human-readable summary of *response*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Controller Transport Response Envelope")
    lines.append("=" * 64)
    lines.append(f"Request ID:    {response.request_id}")
    lines.append(f"Version:       {response.envelope_version}")
    lines.append(f"Schema:        {response.schema}")
    lines.append(f"Task:          {response.task_id or 'n/a'}")
    lines.append(f"File:          {response.task_filename or 'n/a'}")
    lines.append(f"Handoff:       {response.handoff_request_path}")
    lines.append(f"Bundle:        {response.review_bundle_path}")
    lines.append(f"Result state:  {response.result_state}")
    if response.decision_path or response.decision:
        lines.append(f"Decision:      {response.decision or 'n/a'}")
        if response.decision_path:
            lines.append(f"Decision path: {response.decision_path}")
    if response.messages:
        lines.append("-" * 64)
        lines.append("Messages:")
        for msg in response.messages:
            lines.append(f"  {msg}")
    lines.append("=" * 64)
    return "\n".join(lines)
