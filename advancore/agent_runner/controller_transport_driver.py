"""Controller transport-driver boundary for the local agent runner.

A transport driver is delivery plumbing only. It separates envelope semantics
from delivery mechanics so that future remote transports can be added without
changing controller authority, envelope semantics, handoff reconciliation,
lifecycle authority, or Git-publication governance.

The driver contract defined here is intentionally small:

* ``send`` writes a validated TASK-015 request envelope.
* ``receive`` loads a validated TASK-015 response envelope bound to a request.
* ``show`` inspects driver artifacts for a correlation id without mutation.

The built-in ``LocalFilesystemTransportDriver`` is a bounded local-filesystem
implementation. It is not HTTP, webhooks, sockets, queues, background polling,
model calls, credentials, or subprocess transport. It does not create, infer,
approve, reconcile, apply, publish, or deploy on its own.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from advancore.agent_runner.controller_transport import (
    ControllerTransportError,
    ControllerTransportRequest,
    ControllerTransportResponse,
    ControllerTransportValidationError,
    ControllerTransportWriteError,
    _sanitize_filename,
    default_transport_dir,
    load_transport_request,
    load_transport_response,
    serialize_transport_request,
    serialize_transport_response,
    validate_transport_request,
    validate_transport_response,
    write_transport_response,
)


class ControllerTransportDriverError(Exception):
    """Raised when a transport driver cannot complete an operation."""


class ControllerTransportDriverConflictError(ControllerTransportDriverError):
    """Raised when an existing artifact conflicts with the requested operation."""


class ControllerTransportDriverNotFoundError(ControllerTransportDriverError):
    """Raised when a required driver artifact is not found."""


class ControllerTransportDriverAmbiguousError(ControllerTransportDriverError):
    """Raised when more than one candidate artifact matches a unique id."""


@dataclass
class DriverArtifactView:
    """Read-only view of driver artifacts for a single correlation id."""

    request_id: str
    request_path: Path | None = None
    response_path: Path | None = None
    request: ControllerTransportRequest | None = None
    response: ControllerTransportResponse | None = None


class ControllerTransportDriver(ABC):
    """Replaceable boundary between envelope semantics and delivery mechanics.

    A driver moves validated envelope artifacts. It does NOT possess controller
    authority: it never creates, infers, approves, reconciles, applies,
    publishes, or deploys on its own.
    """

    @abstractmethod
    def send(self, request: ControllerTransportRequest) -> Path:
        """Write *request* to the transport store and return the artifact path.

        Implementations must validate the request through the existing TASK-015
        envelope contract, remain inside the bounded transport directory, and
        block conflicting duplicates for the same correlation id.
        """
        ...

    @abstractmethod
    def receive(self, request: ControllerTransportRequest) -> ControllerTransportResponse:
        """Load the response envelope bound to *request*.

        Implementations must validate the response through the existing TASK-015
        envelope contract and bind it to the expected request id, task id,
        handoff path, and review-bundle path. Missing or ambiguous responses
        fail closed.
        """
        ...

    @abstractmethod
    def show(self, request_id: str) -> DriverArtifactView:
        """Return a read-only view of artifacts for *request_id*."""
        ...


def default_driver_dirs(repo_root: Path) -> tuple[Path, Path]:
    """Return the default (outbox, inbox) directories for the local driver."""
    base = default_transport_dir(repo_root)
    return base / "outbox", base / "inbox"


class LocalFilesystemTransportDriver(ControllerTransportDriver):
    """Bounded local-filesystem controller transport driver.

    Requests are written under ``.agent_runner/controller_transport/outbox/``;
    responses are loaded from ``.agent_runner/controller_transport/inbox/``.
    Both directories are gitignored by the existing ``.agent_runner/`` rule.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.outbox_dir, self.inbox_dir = default_driver_dirs(self.repo_root)

    def send(self, request: ControllerTransportRequest) -> Path:
        """Write *request* to the outbox, idempotently if already present."""
        # Validate through the existing TASK-015 helper before writing.
        payload = serialize_transport_request(request)
        try:
            validate_transport_request(payload)
        except ControllerTransportError as exc:
            raise ControllerTransportDriverError(
                f"Invalid transport request: {exc}"
            ) from exc

        self.outbox_dir.mkdir(parents=True, exist_ok=True)

        # Detect existing request artifacts for the same correlation id.
        existing_request = self._find_request_by_id(request.request_id)
        if existing_request is not None:
            existing_payload = json.loads(
                existing_request.read_text(encoding="utf-8")
            )
            if existing_payload == payload:
                return existing_request
            raise ControllerTransportDriverConflictError(
                f"Request {request.request_id!r} already exists with different content"
            )

        path = self._request_path(request)
        self._guard_write_path(path, self.outbox_dir)

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

    def receive(self, request: ControllerTransportRequest) -> ControllerTransportResponse:
        """Load the single response envelope bound to *request*."""
        # Validate the request through the existing TASK-015 helper first.
        validate_transport_request(serialize_transport_request(request))

        candidates = self._find_responses_by_id(request.request_id)
        if not candidates:
            raise ControllerTransportDriverNotFoundError(
                f"No response found for request {request.request_id!r}"
            )
        if len(candidates) > 1:
            names = ", ".join(p.name for p in candidates)
            raise ControllerTransportDriverAmbiguousError(
                f"Ambiguous responses for request {request.request_id!r}: {names}"
            )

        response_path = candidates[0]
        self._guard_read_path(response_path, self.inbox_dir)

        try:
            data = json.loads(response_path.read_text(encoding="utf-8"))
            response = validate_transport_response(
                data,
                expected_request_id=request.request_id,
                expected_task_id=request.task_id,
                expected_handoff_path=request.handoff_request_path,
                expected_bundle_path=request.review_bundle_path,
            )
        except (json.JSONDecodeError, ControllerTransportError) as exc:
            raise ControllerTransportDriverError(
                f"Invalid response for request {request.request_id!r}: {exc}"
            ) from exc
        return response

    def show(self, request_id: str) -> DriverArtifactView:
        """Return a read-only view of artifacts for *request_id*."""
        view = DriverArtifactView(request_id=request_id)

        request_path = self._find_request_by_id(request_id)
        if request_path is not None:
            self._guard_read_path(request_path, self.outbox_dir)
            view.request_path = request_path
            try:
                view.request = load_transport_request(request_path)
            except (json.JSONDecodeError, ControllerTransportError) as exc:
                raise ControllerTransportDriverError(
                    f"Invalid request artifact for {request_id!r}: {exc}"
                ) from exc

        response_paths = self._find_responses_by_id(request_id)
        if len(response_paths) == 1:
            response_path = response_paths[0]
            self._guard_read_path(response_path, self.inbox_dir)
            try:
                view.response = load_transport_response(response_path)
            except (json.JSONDecodeError, ControllerTransportError) as exc:
                raise ControllerTransportDriverError(
                    f"Invalid response artifact for {request_id!r}: {exc}"
                ) from exc
            view.response_path = response_path

        return view

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _request_path(self, request: ControllerTransportRequest) -> Path:
        """Return the deterministic outbox path for *request*."""
        ts = datetime.fromisoformat(request.timestamp).strftime("%Y%m%dT%H%M%S")
        task_part = _sanitize_filename(request.task_id)
        request_part = _sanitize_filename(request.request_id)
        filename = f"{ts}_{task_part}_{request_part}_request.json"
        return self.outbox_dir / filename

    def _find_request_by_id(self, request_id: str) -> Path | None:
        """Return the unique request artifact with *request_id*, if any."""
        if not self.outbox_dir.exists():
            return None
        request_part = _sanitize_filename(request_id)
        matches = sorted(self.outbox_dir.glob(f"*{request_part}_request.json"))
        if len(matches) > 1:
            names = ", ".join(p.name for p in matches)
            raise ControllerTransportDriverAmbiguousError(
                f"Ambiguous requests for id {request_id!r}: {names}"
            )
        return matches[0] if matches else None

    def _find_responses_by_id(self, request_id: str) -> list[Path]:
        """Return all response artifacts with *request_id*."""
        if not self.inbox_dir.exists():
            return []
        request_part = _sanitize_filename(request_id)
        return sorted(self.inbox_dir.glob(f"*{request_part}_response.json"))

    def _guard_write_path(self, path: Path, root: Path) -> None:
        """Fail closed if *path* escapes *root* via traversal or symlink."""
        resolved = path.resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ControllerTransportDriverError(
                f"Path escapes bounded transport directory: {path}"
            ) from exc

        parent = resolved.parent
        try:
            parent.relative_to(root.resolve())
        except ValueError as exc:
            raise ControllerTransportDriverError(
                f"Parent path escapes bounded transport directory: {parent}"
            ) from exc

    def _guard_read_path(self, path: Path, root: Path) -> None:
        """Fail closed if *path* escapes *root* via traversal or symlink."""
        # os.path.realpath follows symlinks; resolve() does too on most platforms.
        real = Path(os.path.realpath(path))
        try:
            real.relative_to(root.resolve())
        except ValueError as exc:
            raise ControllerTransportDriverError(
                f"Read path escapes bounded transport directory: {path}"
            ) from exc


def write_driver_response(
    response: ControllerTransportResponse,
    inbox_dir: Path,
) -> Path:
    """Write *response* to *inbox_dir* for use by the local driver.

    This helper is a thin wrapper around the existing TASK-015 response writer.
    It is intended for tests and for external controller simulators that place
    responses in the driver's inbox. It does not reconcile or apply decisions.
    """
    return write_transport_response(response, inbox_dir)


def load_driver_request_by_id(
    request_id: str,
    outbox_dir: Path,
) -> ControllerTransportRequest:
    """Load a request envelope from *outbox_dir* by its *request_id*.

    Raises:
        ControllerTransportDriverNotFoundError: if no matching request exists.
        ControllerTransportDriverAmbiguousError: if more than one matches.
    """
    driver = LocalFilesystemTransportDriver.__new__(LocalFilesystemTransportDriver)
    driver.outbox_dir = outbox_dir
    driver.inbox_dir = outbox_dir.parent / "inbox"
    path = driver._find_request_by_id(request_id)
    if path is None:
        raise ControllerTransportDriverNotFoundError(
            f"No request found for id {request_id!r}"
        )
    return load_transport_request(path)


def format_driver_view_summary(view: DriverArtifactView) -> str:
    """Return a concise, human-readable summary of *view*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Controller Transport Driver View")
    lines.append("=" * 64)
    lines.append(f"Request ID:    {view.request_id}")
    lines.append(f"Request path:  {view.request_path or 'n/a'}")
    lines.append(f"Response path: {view.response_path or 'n/a'}")
    if view.request is not None:
        lines.append(f"Task:          {view.request.task_id or 'n/a'}")
        lines.append(f"File:          {view.request.task_filename or 'n/a'}")
        lines.append(f"Handoff:       {view.request.handoff_request_path}")
        lines.append(f"Bundle:        {view.request.review_bundle_path}")
    if view.response is not None:
        lines.append(f"Result state:  {view.response.result_state}")
        if view.response.decision_path or view.response.decision:
            lines.append(f"Decision:      {view.response.decision or 'n/a'}")
            if view.response.decision_path:
                lines.append(f"Decision path: {view.response.decision_path}")
    lines.append("=" * 64)
    return "\n".join(lines)
