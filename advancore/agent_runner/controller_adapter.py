"""Controller adapter boundary for the local agent runner.

A controller adapter is a replaceable transport/orchestration boundary between the
local handoff request and an independent controller. It consumes a validated
controller-handoff request and returns a bounded controller-adapter result. It is
not an authority source: it does not make a worker into a controller, treat a
handoff request as approval, fabricate decisions, bypass TASK-011 decision
validation, bypass TASK-012 lifecycle authority, or perform any Git/database
mutation.

The built-in ``manual`` adapter is local, read-only, and performs no network or
subprocess execution. Future adapters can be registered without changing the
core handoff/decision/lifecycle semantics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_controller_adapter_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoff,
    ControllerHandoffError,
    HandoffState,
    find_latest_handoff,
    load_controller_handoff,
    reconcile_controller_handoff,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecisionError,
    load_controller_decision,
)
from advancore.agent_runner.git_info import GitInfo


class AdapterResultState(str, Enum):
    """Allowed states of a controller-adapter result."""

    PENDING = "PENDING"
    DECISION_RECEIVED = "DECISION_RECEIVED"
    BLOCKED = "BLOCKED"


class ControllerAdapterError(Exception):
    """Raised when a controller adapter cannot process a handoff request."""


@dataclass
class ControllerAdapterInput:
    """Bounded input to a controller adapter.

    The input contains only validated handoff metadata and safe references. It
    never includes the full task body, worker transcripts, credentials,
    environment dumps, or arbitrary repository contents.
    """

    request_path: Path
    handoff: ControllerHandoff
    repo_root: Path
    git_info: GitInfo | None = None


@dataclass
class ControllerAdapterResult:
    """Deterministic result of a controller-adapter dispatch attempt."""

    adapter_name: str
    state: str
    task_id: str | None = None
    task_filename: str | None = None
    request_path: str | None = None
    bundle_path: str | None = None
    decision_path: str | None = None
    decision: str | None = None
    reconciled: bool = False
    audit_path: str | None = None
    audit_write_ok: bool = True
    audit_write_error: str | None = None
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.state != AdapterResultState.BLOCKED


class ControllerAdapter(ABC):
    """Replaceable boundary between the local handoff queue and a controller."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""
        ...

    @abstractmethod
    def dispatch(self, input: ControllerAdapterInput) -> ControllerAdapterResult:
        """Process *input* and return a bounded adapter result.

        Implementations must not mutate task lifecycle state, Git state, database
        state, or deployment state. They must not access secrets or credentials,
        and they must not synthesize a controller decision.
        """
        ...


class ManualControllerAdapter(ControllerAdapter):
    """Safe built-in local/manual controller adapter.

    The manual adapter validates the handoff request and exposes the bounded
    handoff information needed for an independent controller. It never invents
    or synthesizes a controller decision; it returns ``PENDING`` until a
    separately valid controller decision exists. It performs no network or
    external-process execution.
    """

    @property
    def name(self) -> str:
        return "manual"

    def dispatch(self, input: ControllerAdapterInput) -> ControllerAdapterResult:
        handoff = input.handoff
        result = ControllerAdapterResult(
            adapter_name=self.name,
            state=AdapterResultState.BLOCKED.value,
            task_id=handoff.task_id,
            task_filename=handoff.task_filename,
            request_path=str(input.request_path),
            bundle_path=handoff.bundle_path,
        )

        if handoff.state == HandoffState.BLOCKED.value:
            result.messages.append("Handoff request state is BLOCKED")
            return result

        if handoff.state not in {
            HandoffState.WAITING_DECISION.value,
            HandoffState.DECISION_RECEIVED.value,
        }:
            result.messages.append(
                f"Unsupported handoff state for controller review: {handoff.state}"
            )
            return result

        if (
            handoff.state == HandoffState.DECISION_RECEIVED.value
            and handoff.decision_path
        ):
            # The handoff already references a controller decision. Report it so
            # the orchestrator can validate and reconcile through TASK-013.
            result.state = AdapterResultState.DECISION_RECEIVED.value
            result.decision_path = handoff.decision_path
            result.decision = handoff.decision
            result.messages.append(
                f"Handoff references existing decision at {handoff.decision_path}"
            )
            return result

        result.state = AdapterResultState.PENDING.value
        result.messages.append(
            "No separately valid controller decision is available; adapter returns PENDING"
        )
        return result


class FakeControllerAdapter(ControllerAdapter):
    """Test-only adapter that returns a deterministic preset result.

    This adapter is intentionally simple and performs no I/O. It is useful for
    unit tests that need to exercise the orchestration boundary with controlled
    adapter behavior. It is not registered by default.
    """

    def __init__(
        self,
        result: ControllerAdapterResult | None = None,
        exception: Exception | None = None,
    ):
        self._result = result
        self._exception = exception

    @property
    def name(self) -> str:
        return "fake"

    def dispatch(self, input: ControllerAdapterInput) -> ControllerAdapterResult:
        if self._exception is not None:
            raise self._exception
        if self._result is None:
            return ControllerAdapterResult(
                adapter_name=self.name,
                state=AdapterResultState.PENDING.value,
                request_path=str(input.request_path),
                messages=["Fake adapter default PENDING result"],
            )
        return self._result


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_controller_adapters: dict[str, ControllerAdapter] = {}


def register_controller_adapter(adapter: ControllerAdapter) -> None:
    """Register *adapter* by its ``name`` for lookup by dispatch CLI/helpers."""
    _controller_adapters[adapter.name] = adapter


def get_controller_adapter(name: str) -> ControllerAdapter | None:
    """Return the registered adapter named *name*, or ``None``."""
    return _controller_adapters.get(name)


def _register_default_adapters() -> None:
    register_controller_adapter(ManualControllerAdapter())


_register_default_adapters()


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------


def _resolve_handoff_path(target: str | Path, repo_root: Path) -> Path:
    """Return an absolute handoff-request path from a CLI-style target."""
    target_str = str(target).strip()
    if target_str.lower() == "latest":
        latest = find_latest_handoff(repo_root / ".agent_runner" / "controller_handoff")
        if latest is None:
            raise ControllerAdapterError(
                f"No handoff requests found under {repo_root / '.agent_runner' / 'controller_handoff'}"
            )
        return latest.resolve()

    path = Path(target_str)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path.resolve()


def _resolve_decision_path(value: str, repo_root: Path) -> Path:
    """Return an absolute decision-record path from a possibly relative string."""
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path.resolve()


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


def _validate_adapter_result_state(state: str) -> bool:
    """Return whether *state* is a known adapter result state."""
    return state in {
        AdapterResultState.PENDING.value,
        AdapterResultState.DECISION_RECEIVED.value,
        AdapterResultState.BLOCKED.value,
    }


def _build_base_result(
    handoff: ControllerHandoff,
    request_path: Path,
    adapter_name: str,
) -> ControllerAdapterResult:
    """Return a base result populated from *handoff* metadata."""
    return ControllerAdapterResult(
        adapter_name=adapter_name,
        state=AdapterResultState.PENDING.value,
        task_id=handoff.task_id,
        task_filename=handoff.task_filename,
        request_path=str(request_path),
        bundle_path=handoff.bundle_path,
    )


def _maybe_write_adapter_audit(
    result: ControllerAdapterResult,
    git_info: GitInfo | None,
) -> None:
    """Append a controller-adapter audit record if a Git snapshot is available."""
    if git_info is None:
        return

    payload = build_controller_adapter_audit_payload(
        timestamp=datetime.now(timezone.utc),
        task_id=result.task_id,
        task_filename=result.task_filename,
        adapter_name=result.adapter_name,
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
        result.messages.append(f"Adapter audit record written to {audit_path}")
    except AuditWriteError as exc:
        result.audit_write_ok = False
        result.audit_write_error = str(exc)
        result.messages.append(f"WARNING: {exc}")


def dispatch_controller_adapter(
    handoff_target: str | Path,
    adapter: ControllerAdapter | str,
    *,
    repo_root: Path,
    git_info: GitInfo | None = None,
) -> ControllerAdapterResult:
    """Load a handoff request, invoke exactly one adapter, and reconcile if needed.

    The helper:

    1. Resolves and loads the handoff request.
    2. Looks up the requested adapter (or uses the supplied instance).
    3. Invokes the adapter with bounded input.
    4. Validates the returned adapter result state.
    5. If the adapter returns ``DECISION_RECEIVED`` with a decision path,
       validates and reconciles the decision through the existing TASK-013
       handoff reconciliation logic.
    6. Writes a local audit record when a Git snapshot is available.

    This helper does **not** invoke the TASK-012 lifecycle bridge and does not
    mutate task files, Git index/commits/branches/remotes, or database state.
    """
    # 1. Resolve and load the handoff request.
    try:
        request_path = _resolve_handoff_path(handoff_target, repo_root)
        handoff = load_controller_handoff(request_path)
    except (ControllerAdapterError, ControllerHandoffError, OSError) as exc:
        result = ControllerAdapterResult(
            adapter_name=getattr(adapter, "name", None) or "unknown",
            state=AdapterResultState.BLOCKED.value,
            request_path=str(handoff_target) if not isinstance(handoff_target, Path) else str(handoff_target),
            messages=[f"FAIL: cannot load handoff request: {exc}"],
        )
        _maybe_write_adapter_audit(result, git_info)
        return result

    # 2. Resolve the adapter.
    adapter_instance: ControllerAdapter | None
    if isinstance(adapter, ControllerAdapter):
        adapter_instance = adapter
    else:
        adapter_instance = get_controller_adapter(adapter)

    if adapter_instance is None:
        result = _build_base_result(handoff, request_path, str(adapter))
        result.state = AdapterResultState.BLOCKED.value
        result.messages.append(f"Unknown controller adapter: {adapter!r}")
        _maybe_write_adapter_audit(result, git_info)
        return result

    result = _build_base_result(handoff, request_path, adapter_instance.name)

    # 3. Invoke the adapter.
    try:
        adapter_input = ControllerAdapterInput(
            request_path=request_path,
            handoff=handoff,
            repo_root=repo_root,
            git_info=git_info,
        )
        adapter_result = adapter_instance.dispatch(adapter_input)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        result.state = AdapterResultState.BLOCKED.value
        result.messages.append(f"Adapter {adapter_instance.name} failed: {exc}")
        _maybe_write_adapter_audit(result, git_info)
        return result

    # 4. Validate the returned result state.
    if not _validate_adapter_result_state(adapter_result.state):
        result.state = AdapterResultState.BLOCKED.value
        result.messages.append(
            f"Unknown adapter result state: {adapter_result.state!r}"
        )
        _maybe_write_adapter_audit(result, git_info)
        return result

    result.state = adapter_result.state
    result.decision_path = adapter_result.decision_path
    result.decision = adapter_result.decision
    result.messages.extend(adapter_result.messages)

    # 5. If a decision is reported, validate and reconcile through TASK-013.
    if (
        result.state == AdapterResultState.DECISION_RECEIVED.value
        and result.decision_path
    ):
        try:
            decision_path = _resolve_decision_path(result.decision_path, repo_root)
        except (OSError, ValueError) as exc:
            result.state = AdapterResultState.BLOCKED.value
            result.messages.append(f"Cannot resolve decision path: {exc}")
            _maybe_write_adapter_audit(result, git_info)
            return result

        reconcile_result = reconcile_controller_handoff(
            request_path=request_path,
            decision_path=decision_path,
            repo_root=repo_root,
            git_info=git_info,
        )
        result.reconciled = reconcile_result.ok
        result.messages.extend(reconcile_result.messages)

        if not reconcile_result.ok:
            result.state = AdapterResultState.BLOCKED.value
            result.messages.append(
                "Decision could not be reconciled; adapter result treated as BLOCKED"
            )
            _maybe_write_adapter_audit(result, git_info)
            return result

        if reconcile_result.handoff is not None:
            result.decision = reconcile_result.handoff.decision
            result.decision_path = reconcile_result.handoff.decision_path

    # 6. Write audit record.
    _maybe_write_adapter_audit(result, git_info)
    return result


def inspect_controller_adapter_status(
    handoff_target: str | Path,
    *,
    repo_root: Path,
    git_info: GitInfo | None = None,
) -> ControllerAdapterResult:
    """Read-only inspection of a handoff request through the manual adapter lens.

    This helper loads the handoff request and reports its current state as an
    adapter result. It does not invoke any network transport, reconcile a
    decision, write artifacts, or mutate task/Git/database state.
    """
    try:
        request_path = _resolve_handoff_path(handoff_target, repo_root)
        handoff = load_controller_handoff(request_path)
    except (ControllerAdapterError, ControllerHandoffError, OSError) as exc:
        return ControllerAdapterResult(
            adapter_name="manual",
            state=AdapterResultState.BLOCKED.value,
            request_path=str(handoff_target) if not isinstance(handoff_target, Path) else str(handoff_target),
            messages=[f"FAIL: cannot load handoff request: {exc}"],
        )

    result = _build_base_result(handoff, request_path, "manual")

    if handoff.state == HandoffState.BLOCKED.value:
        result.state = AdapterResultState.BLOCKED.value
        result.messages.append("Handoff request state is BLOCKED")
    elif handoff.state == HandoffState.DECISION_RECEIVED.value:
        result.state = AdapterResultState.DECISION_RECEIVED.value
        result.decision_path = handoff.decision_path
        result.decision = handoff.decision
        result.messages.append(
            f"Handoff is reconciled to decision {handoff.decision or 'n/a'}"
        )
    elif handoff.state == HandoffState.WAITING_DECISION.value:
        result.state = AdapterResultState.PENDING.value
        result.messages.append("Handoff is waiting for an independent controller decision")
    else:
        result.state = AdapterResultState.BLOCKED.value
        result.messages.append(f"Unsupported handoff state: {handoff.state}")

    return result


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_adapter_result(result: ControllerAdapterResult) -> str:
    """Return a concise, human-readable summary of *result*."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Controller Adapter Result")
    lines.append("=" * 64)
    lines.append(f"Adapter:       {result.adapter_name}")
    lines.append(f"Task:          {result.task_id or 'n/a'}")
    lines.append(f"File:          {result.task_filename or 'n/a'}")
    lines.append(f"Handoff:       {result.request_path or 'n/a'}")
    lines.append(f"Bundle:        {result.bundle_path or 'n/a'}")
    lines.append(f"Adapter state: {result.state}")
    if result.decision_path:
        lines.append(f"Decision:      {result.decision or 'n/a'}")
        lines.append(f"Decision path: {result.decision_path}")
    lines.append(f"Reconciled:    {'yes' if result.reconciled else 'no'}")
    if result.audit_path:
        lines.append(f"Audit record:  {result.audit_path}")
    elif not result.audit_write_ok:
        lines.append("Audit record:  NOT WRITTEN")
        if result.audit_write_error:
            lines.append(f"  error: {result.audit_write_error}")
    lines.append("-" * 64)
    lines.append("Messages:")
    if result.messages:
        for msg in result.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  (none)")
    lines.append("=" * 64)
    return "\n".join(lines)
