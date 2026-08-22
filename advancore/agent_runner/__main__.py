"""CLI entry point for the local agent runner.

Default behaviour is dry-run planning. Use ``--execute`` to actually invoke
a worker adapter, and choose the worker with ``--worker``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_controller_decision_audit_payload,
    build_controller_transport_audit_payload,
    build_handoff_audit_payload,
    default_audit_dir,
    write_audit_record,
)
from advancore.agent_runner.controller_adapter import (
    AdapterResultState,
    ControllerAdapterResult,
    dispatch_controller_adapter,
    format_adapter_result,
    inspect_controller_adapter_status,
)
from advancore.agent_runner.controller_transport import (
    TRANSPORT_REQUEST_SCHEMA,
    TRANSPORT_RESPONSE_SCHEMA,
    ControllerTransportError,
    ControllerTransportRequest,
    ControllerTransportValidationError,
    ControllerTransportWriteError,
    apply_transport_response,
    build_transport_request,
    build_transport_response,
    default_transport_dir,
    find_latest_transport_request,
    find_latest_transport_response,
    format_transport_request_summary,
    format_transport_response_summary,
    handoff_to_transport_request,
    load_transport_request,
    load_transport_response,
    serialize_transport_request,
    validate_transport_request,
    validate_transport_response,
    write_transport_request,
    write_transport_response,
)
from advancore.agent_runner.controller_transport_driver import (
    ControllerTransportDriverAmbiguousError,
    ControllerTransportDriverConflictError,
    ControllerTransportDriverError,
    ControllerTransportDriverNotFoundError,
    DriverArtifactView,
    LocalFilesystemTransportDriver,
    default_driver_dirs,
    format_driver_view_summary,
    load_driver_request_by_id,
    write_driver_response,
)
from advancore.agent_runner.controller_decision import (
    ControllerDecisionError,
    ControllerDecisionWriteError,
    DecisionValue,
    build_controller_decision,
    default_decisions_dir,
    find_latest_decision,
    format_decision_summary,
    load_controller_decision,
    write_controller_decision,
)
from advancore.agent_runner.controller_handoff import (
    ControllerHandoffError,
    ControllerHandoffWriteError,
    HandoffReconciliationResult,
    HandoffState,
    build_controller_handoff,
    default_handoff_dir,
    find_latest_handoff,
    format_handoff_summary,
    load_controller_handoff,
    reconcile_controller_handoff,
    write_controller_handoff,
)
from advancore.agent_runner.decision_lifecycle_bridge import (
    DecisionLifecycleResult,
    apply_controller_decision,
)
from advancore.agent_runner.finalize import (
    FinalizationResult,
    FinalizationStatus,
    format_finalization_result,
    run_finalization,
)
from advancore.agent_runner.git_info import GitInfo, get_git_info
from advancore.agent_runner.lifecycle import (
    ActorRole,
    LifecycleResult,
    TaskStatus,
    transition_task,
)
from advancore.agent_runner.review_bundle import (
    ReviewBundleError,
    find_latest_bundle,
    format_bundle_summary,
    load_review_bundle,
)
from advancore.agent_runner.runner import RunnerResult, RunnerStatus, execute, plan
from advancore.agent_runner.worker import (
    APPROVED_WORKER_NAMES,
    DryRunWorkerAdapter,
    KimiSwarmWorkerAdapter,
    KimiWorkerAdapter,
    WorkerAdapter,
    WorkerError,
    build_worker_adapter,
    validate_worker_policy,
)
from advancore.agent_runner.auto_pipeline import (
    AutoPipelineStatus,
    format_auto_pipeline_report,
    run_auto_pipeline,
)
from advancore.agent_runner.goal_task import (
    GoalTaskGenerationResult,
    GoalTaskGenerationStatus,
    generate_goal_task,
    format_goal_task_report,
)
from advancore.agent_runner.orchestration import (
    OrchestrationConfig,
    OrchestrationError,
    OrchestrationPhase,
    OrchestrationResult,
    OrchestrationStatus,
    run_orchestration,
)


def _format_result(result: RunnerResult) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Execution Plan")
    lines.append("=" * 64)

    if result.task:
        lines.append(f"Task:         {result.task.task_id}")
        lines.append(f"Title:        {result.task.title}")
        lines.append(f"Status:       {result.task.status}")
        lines.append(f"File:         tasks/{result.task.filename}")
    else:
        lines.append("Task:         n/a")

    git_info = result.pre_git_info or result.git_info
    if git_info:
        lines.append(f"Branch:       {git_info.current_branch}")
        lines.append(f"HEAD:         {git_info.head_sha}")
        lines.append(f"Repo root:    {git_info.repo_root}")
        lines.append(
            f"Working tree: {'clean' if git_info.is_clean else 'dirty'}"
        )
        if git_info.status_lines:
            lines.append("Pre-worker uncommitted changes:")
            for status_line in git_info.status_lines:
                lines.append(f"  {status_line}")
    else:
        lines.append("Branch:       n/a")
        lines.append("HEAD:         n/a")
        lines.append("Repo root:    n/a")

    lines.append("-" * 64)
    lines.append("Validation:")
    if result.validation:
        for msg in result.validation.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  n/a")

    lines.append("-" * 64)
    lines.append("Worker instruction:")
    if result.worker_instruction:
        for line in result.worker_instruction.splitlines():
            lines.append(f"  {line}")
    else:
        lines.append("  n/a")

    lines.append("-" * 64)
    if result.worker_command:
        lines.append(f"Worker:       {result.worker_command[0]}")
        lines.append(f"Command:      {' '.join(result.worker_command)}")
    else:
        lines.append("Worker:       dry-run")
        lines.append("Command:      (none)")

    lines.append("-" * 64)
    lines.append("Allowed automatic actions:")
    lines.append("  - Read approved repository files")
    lines.append("  - Parse task metadata")
    lines.append("  - Inspect git status / branch / HEAD")
    lines.append("  - Generate worker prompt")
    lines.append("  - Capture pre/post Git snapshots")
    lines.append("  - Write local audit record")
    lines.append("Gated actions (require explicit approval):")
    lines.append("  - Commit, push, merge")
    lines.append("  - Destructive Git operations (reset, force push, history rewrite)")
    lines.append("  - Production / destructive database actions")
    lines.append("  - Secret / credential access")
    lines.append("  - Compliance / commercial rule changes")

    if result.post_verification:
        lines.append("-" * 64)
        lines.append("Post-worker verification:")
        status = "PASS" if result.post_verification.ok else "FAIL"
        lines.append(f"  Result: {status}")
        for msg in result.post_verification.messages:
            lines.append(f"  {msg}")
        if result.post_verification.changed_paths:
            lines.append("  Changed paths:")
            for changed_path in result.post_verification.changed_paths:
                lines.append(f"    {changed_path}")

    if result.worker_result:
        lines.append("-" * 64)
        lines.append("Worker result:")
        lines.append(f"  success: {result.worker_result.success}")
        lines.append(f"  message: {result.worker_result.message}")
        if result.worker_result.stdout:
            lines.append("  stdout:")
            for line in result.worker_result.stdout.splitlines():
                lines.append(f"    {line}")
        if result.worker_result.stderr:
            lines.append("  stderr:")
            for line in result.worker_result.stderr.splitlines():
                lines.append(f"    {line}")

    lines.append("-" * 64)
    lines.append("Messages:")
    if result.messages:
        for msg in result.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  (none)")

    lines.append("-" * 64)
    lines.append(f"Result status: {result.status.value}")

    if result.audit_path:
        rel_path = result.audit_path.relative_to(
            (result.pre_git_info or result.git_info).repo_root
        )
        lines.append(f"Audit record: {rel_path}")
    elif not result.audit_write_ok:
        lines.append("Audit record: NOT WRITTEN")
        if result.audit_write_error:
            lines.append(f"  error: {result.audit_write_error}")

    if result.review_bundle_path:
        rel_path = result.review_bundle_path.relative_to(
            (result.pre_git_info or result.git_info).repo_root
        )
        lines.append(f"Review bundle: {rel_path}")
    elif not result.review_bundle_write_ok:
        lines.append("Review bundle: NOT WRITTEN")
        if result.review_bundle_write_error:
            lines.append(f"  error: {result.review_bundle_write_error}")

    lines.append("=" * 64)
    return "\n".join(lines)


def _format_lifecycle_result(result: LifecycleResult) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Task Lifecycle Transition")
    lines.append("=" * 64)
    lines.append(f"Task:            {result.task_id or 'n/a'}")
    lines.append(f"File:            {result.task_filename or 'n/a'}")
    lines.append(f"Current state:   {result.previous_status or 'n/a'}")
    lines.append(f"Requested state: {result.requested_status or 'n/a'}")
    lines.append(f"Actor role:      {result.actor.value if result.actor else 'n/a'}")
    lines.append(f"Permitted:       {'yes' if result.allowed else 'no'}")
    lines.append(f"Mode:            {'applied' if result.applied else result.mode}")
    lines.append("-" * 64)
    lines.append("Messages:")
    if result.messages:
        for msg in result.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  (none)")
    if result.audit_path:
        lines.append(f"Audit record: {result.audit_path}")
    elif not result.audit_write_ok:
        lines.append("Audit record: NOT WRITTEN")
        if result.audit_write_error:
            lines.append(f"  error: {result.audit_write_error}")
    lines.append("=" * 64)
    return "\n".join(lines)


def _format_decision_record_result(
    decision_path: Path | None,
    audit_path: Path | None,
    audit_write_error: str | None,
    error: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Decision Record")
    lines.append("=" * 64)
    if error:
        lines.append(f"Result: FAIL")
        lines.append(f"Error:  {error}")
    elif decision_path:
        lines.append(f"Result: OK")
        lines.append(f"Decision record: {decision_path}")
    else:
        lines.append("Result: FAIL")
        lines.append("Error:  decision record was not created")
    if audit_path:
        rel_path = audit_path
        try:
            rel_path = audit_path.relative_to(Path.cwd())
        except ValueError:
            pass
        lines.append(f"Audit record: {rel_path}")
    elif audit_write_error:
        lines.append("Audit record: NOT WRITTEN")
        lines.append(f"  error: {audit_write_error}")
    lines.append("=" * 64)
    return "\n".join(lines)


def _format_finalize_result(result: FinalizationResult) -> str:
    return format_finalization_result(result)


def _format_orchestration_result(result: OrchestrationResult) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("AdvanCore End-to-End Controller Orchestration")
    lines.append("=" * 72)
    lines.append(f"Run ID:            {result.run_id}")
    lines.append(f"Task:              {result.task_id or 'n/a'}")
    lines.append(f"Task path:         {result.task_path or 'n/a'}")
    lines.append(f"Phase:             {result.phase}")
    lines.append(f"Status:            {result.status}")
    lines.append(f"Completed phases:  {', '.join(result.completed_phases) or '(none)'}")
    lines.append(f"Branch:            {result.branch or 'n/a'}")
    lines.append(f"HEAD:              {result.head or 'n/a'}")
    lines.append("-" * 72)
    lines.append("Evidence paths:")
    for key, value in result.evidence_paths.items():
        lines.append(f"  {key}: {value or 'n/a'}")
    lines.append("-" * 72)
    lines.append(f"Controller gate:   {result.controller_gate or 'n/a'}")
    lines.append(f"Mutations:         {', '.join(result.mutations_performed) or 'none'}")
    lines.append(f"Owner decision:    {'required' if result.owner_decision_required else 'no'}")
    if result.blocking_reason:
        lines.append(f"Blocking reason:   {result.blocking_reason}")
    lines.append("-" * 72)
    lines.append(f"Next action:       {result.next_action}")
    lines.append(f"Resume command:    {result.resume_command}")
    lines.append("-" * 72)
    lines.append("Messages:")
    if result.messages:
        for msg in result.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  (none)")
    lines.append("=" * 72)
    return "\n".join(lines)


def _format_bridge_result(result: DecisionLifecycleResult) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Decision Lifecycle Bridge")
    lines.append("=" * 64)
    lines.append(f"Task:            {result.task_id or 'n/a'}")
    lines.append(f"File:            {result.task_filename or 'n/a'}")
    lines.append(f"Current state:   {result.current_status or 'n/a'}")
    lines.append(f"Decision:        {result.decision or 'n/a'}")
    lines.append(f"Actor role:      {result.actor_role or 'n/a'}")
    lines.append(f"Target state:    {result.target_status or 'n/a'}")
    lines.append(f"Permitted:       {'yes' if result.transition_allowed else 'no'}")
    lines.append(f"Mode:            {'applied' if result.applied else result.mode}")
    if result.decision_path:
        lines.append(f"Decision record: {result.decision_path}")
    if result.bundle_path:
        lines.append(f"Review bundle:   {result.bundle_path}")
    head = result.head_evidence
    if head:
        lines.append(f"Current branch:  {head.get('current_branch') or 'n/a'}")
        lines.append(f"Current HEAD:    {head.get('current_head') or 'n/a'}")
        lines.append(f"Bundle pre HEAD: {head.get('bundle_pre_head') or 'n/a'}")
        lines.append(f"Bundle post HEAD: {head.get('bundle_post_head') or 'n/a'}")
    lines.append("-" * 64)
    lines.append("Messages:")
    if result.messages:
        for msg in result.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  (none)")
    if result.audit_path:
        try:
            rel_path = result.audit_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = result.audit_path
        lines.append(f"Bridge audit: {rel_path}")
    elif not result.audit_write_ok:
        lines.append("Bridge audit: NOT WRITTEN")
        if result.audit_write_error:
            lines.append(f"  error: {result.audit_write_error}")
    lines.append("=" * 64)
    return "\n".join(lines)


def _format_handoff_prepare_result(
    handoff_path: Path | None,
    audit_path: Path | None,
    audit_write_error: str | None,
    error: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Handoff")
    lines.append("=" * 64)
    if error:
        lines.append("Result: FAIL")
        lines.append(f"Error:  {error}")
    elif handoff_path:
        lines.append("Result: OK")
        lines.append(f"Handoff request: {handoff_path}")
    else:
        lines.append("Result: FAIL")
        lines.append("Error:  handoff request was not created")
    if audit_path:
        try:
            rel_path = audit_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = audit_path
        lines.append(f"Audit record: {rel_path}")
    elif audit_write_error:
        lines.append("Audit record: NOT WRITTEN")
        lines.append(f"  error: {audit_write_error}")
    lines.append("=" * 64)
    return "\n".join(lines)


def _format_handoff_reconcile_result(result: HandoffReconciliationResult) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Handoff Reconciliation")
    lines.append("=" * 64)
    lines.append(f"Result: {'OK' if result.ok else 'FAIL'}")
    if result.handoff:
        lines.append(f"Request ID: {result.handoff.request_id}")
        lines.append(f"State:      {result.handoff.state}")
        if result.handoff.decision:
            lines.append(f"Decision:   {result.handoff.decision}")
    lines.append("-" * 64)
    lines.append("Messages:")
    if result.messages:
        for msg in result.messages:
            lines.append(f"  {msg}")
    else:
        lines.append("  (none)")
    if result.audit_path:
        try:
            rel_path = result.audit_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = result.audit_path
        lines.append(f"Audit record: {rel_path}")
    elif not result.audit_write_ok:
        lines.append("Audit record: NOT WRITTEN")
        if result.audit_write_error:
            lines.append(f"  error: {result.audit_write_error}")
    lines.append("=" * 64)
    return "\n".join(lines)


def _format_controller_adapter_result(result: ControllerAdapterResult) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Adapter")
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
        try:
            rel_path = Path(result.audit_path).relative_to(Path.cwd())
        except ValueError:
            rel_path = result.audit_path
        lines.append(f"Audit record:  {rel_path}")
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


def _format_transport_request_result(
    envelope_path: Path | None,
    audit_path: Path | None,
    audit_write_error: str | None,
    error: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Transport Request")
    lines.append("=" * 64)
    if error:
        lines.append("Result: FAIL")
        lines.append(f"Error:  {error}")
    elif envelope_path:
        lines.append("Result: OK")
        lines.append(f"Envelope: {envelope_path}")
    else:
        lines.append("Result: FAIL")
        lines.append("Error:  transport request envelope was not created")
    if audit_path:
        try:
            rel_path = audit_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = audit_path
        lines.append(f"Audit record: {rel_path}")
    elif audit_write_error:
        lines.append("Audit record: NOT WRITTEN")
        lines.append(f"  error: {audit_write_error}")
    lines.append("=" * 64)
    return "\n".join(lines)


def _format_transport_response_result(result: ControllerAdapterResult) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Transport Response")
    lines.append("=" * 64)
    lines.append(f"Result state:  {result.state}")
    lines.append(f"Task:          {result.task_id or 'n/a'}")
    lines.append(f"File:          {result.task_filename or 'n/a'}")
    lines.append(f"Handoff:       {result.request_path or 'n/a'}")
    lines.append(f"Bundle:        {result.bundle_path or 'n/a'}")
    if result.decision_path:
        lines.append(f"Decision:      {result.decision or 'n/a'}")
        lines.append(f"Decision path: {result.decision_path}")
    lines.append(f"Reconciled:    {'yes' if result.reconciled else 'no'}")
    if result.audit_path:
        try:
            rel_path = Path(result.audit_path).relative_to(Path.cwd())
        except ValueError:
            rel_path = result.audit_path
        lines.append(f"Audit record:  {rel_path}")
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


def _format_driver_receive_result(response: ControllerTransportResponse) -> str:
    return format_transport_response_summary(response)


def _format_driver_send_result(path: Path | None, error: str | None = None) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("AdvanCore Local Agent Runner — Controller Transport Driver Send")
    lines.append("=" * 64)
    if error:
        lines.append("Result: FAIL")
        lines.append(f"Error:  {error}")
    elif path:
        lines.append("Result: OK")
        lines.append(f"Path:   {path}")
    else:
        lines.append("Result: FAIL")
        lines.append("Error:  request was not sent")
    lines.append("=" * 64)
    return "\n".join(lines)


def _resolve_transport_request_target(
    target: str,
    repo_root: Path,
    outbox_dir: Path,
    handoff_dir: Path,
    *,
    latest_from_outbox: bool = False,
) -> ControllerTransportRequest:
    """Resolve a CLI target into a validated transport request envelope.

    *target* may be:
      - ``latest``: the latest handoff request (or latest outbox request if
        *latest_from_outbox* is True) converted to/used as a transport request.
      - A request id: load the matching request from *outbox_dir*.
      - A path to a transport request envelope.
      - A path to a handoff request (converted to a transport request).
    """
    target_str = target.strip()
    if target_str.lower() == "latest":
        if latest_from_outbox:
            latest_request = find_latest_transport_request(outbox_dir)
            if latest_request is None:
                raise ControllerTransportDriverError(
                    f"No transport requests found in {outbox_dir}"
                )
            return load_transport_request(latest_request)

        latest_handoff = find_latest_handoff(handoff_dir)
        if latest_handoff is None:
            raise ControllerTransportDriverError(
                f"No handoff requests found in {handoff_dir}"
            )
        handoff = load_controller_handoff(latest_handoff)
        return handoff_to_transport_request(
            handoff_path=latest_handoff,
            handoff=handoff,
            adapter_name="manual",
            adapter_type="local",
            repo_root=repo_root,
        )

    # If the target looks like a path, try it first.
    if "/" in target_str or "\\" in target_str or Path(target_str).suffix:
        path = Path(target_str)
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists():
            # Try as a transport request envelope first.
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("schema") == TRANSPORT_REQUEST_SCHEMA:
                    return validate_transport_request(data)
            except Exception:
                pass
            # Otherwise treat as a handoff request.
            try:
                handoff = load_controller_handoff(path)
                return handoff_to_transport_request(
                    handoff_path=path,
                    handoff=handoff,
                    adapter_name="manual",
                    adapter_type="local",
                    repo_root=repo_root,
                )
            except Exception as exc:
                raise ControllerTransportDriverError(
                    f"Cannot resolve target as request or handoff: {path} ({exc})"
                ) from exc
        raise ControllerTransportDriverError(f"Target path does not exist: {path}")

    # Treat as a request id and load from the outbox.
    return load_driver_request_by_id(target_str, outbox_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m advancore.agent_runner",
        description="AdvanCore local agent runner (dry-run by default).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser(
        "plan", help="Generate a dry-run execution plan for a task."
    )
    plan_parser.add_argument("task_id", help="Task identifier, e.g. TASK-005")
    plan_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually launch the worker instead of just planning.",
    )
    plan_parser.add_argument(
        "--worker",
        choices=["dry-run", "kimi"],
        default="dry-run",
        help="Worker adapter to use (default: dry-run).",
    )

    auto_parser = subparsers.add_parser(
        "auto",
        help="Run the governed auto-pipeline (validate, worker, pytest, diff-check, scope).",
    )
    auto_parser.add_argument("task_id", help="Task identifier, e.g. TASK-018")
    auto_parser.add_argument(
        "--worker",
        choices=APPROVED_WORKER_NAMES,
        default="dry-run",
        help="Worker adapter to use (default: dry-run).",
    )
    auto_parser.add_argument(
        "--fallback-worker",
        choices=APPROVED_WORKER_NAMES,
        default=None,
        help="Optional explicit provider-availability fallback worker (default: none).",
    )
    auto_parser.add_argument(
        "--repair-attempts",
        type=int,
        default=0,
        help="Maximum autonomous repair attempts (0-2, default: 0).",
    )

    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Controller-gated finalization: stage, commit, and push the current feature branch (dry-run by default).",
    )
    finalize_parser.add_argument("task_id", help="Task identifier, e.g. TASK-020")
    finalize_parser.add_argument(
        "--decision",
        default="latest",
        help='Path to a controller decision record, or "latest" (default: latest).',
    )
    finalize_parser.add_argument(
        "--message",
        default=None,
        help="Optional bounded commit message (default: task-derived 'agent: <title>').",
    )
    finalize_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply lifecycle transitions, stage, commit, and push (default is preview only).",
    )

    goal_task_parser = subparsers.add_parser(
        "goal-task",
        help="Convert an owner goal into a bounded DRAFT task (dry-run by default).",
    )
    goal_task_parser.add_argument(
        "--goal",
        required=True,
        help="Bounded natural-language owner goal.",
    )
    goal_task_parser.add_argument(
        "--planner",
        choices=["dry-run", "kimi", "kimi-swarm"],
        default="dry-run",
        help="Planner adapter to use (default: dry-run).",
    )
    goal_task_parser.add_argument(
        "--execute",
        action="store_true",
        help="Launch the planner and write the DRAFT task after validation.",
    )

    orchestrate_parser = subparsers.add_parser(
        "orchestrate",
        help="Run the governed end-to-end orchestration from owner goal to feature-branch publication (preview by default).",
    )
    orchestrate_parser.add_argument(
        "--goal",
        default=None,
        help="Bounded natural-language owner goal for a new run.",
    )
    orchestrate_parser.add_argument(
        "--resume",
        dest="resume_run_id",
        default=None,
        help="Resume an existing orchestration run by ID.",
    )
    orchestrate_parser.add_argument(
        "--planner",
        choices=["dry-run", "kimi", "kimi-swarm"],
        default="dry-run",
        help="Planner adapter to use for goal-task generation (default: dry-run).",
    )
    orchestrate_parser.add_argument(
        "--worker",
        choices=APPROVED_WORKER_NAMES,
        default="dry-run",
        help="Implementation worker adapter to use (default: dry-run).",
    )
    orchestrate_parser.add_argument(
        "--fallback-worker",
        choices=APPROVED_WORKER_NAMES,
        default=None,
        help="Optional explicit provider-availability fallback worker (default: none).",
    )
    orchestrate_parser.add_argument(
        "--controller",
        default="manual",
        help="Controller adapter to use for implementation review (default: manual).",
    )
    orchestrate_parser.add_argument(
        "--repair-attempts",
        type=int,
        default=0,
        help="Maximum autonomous repair attempts during execution (0-2, default: 0).",
    )
    orchestrate_parser.add_argument(
        "--max-rework",
        type=int,
        default=0,
        help="Maximum controller-driven rework cycles after REWORK decision (0-1, default: 0).",
    )
    orchestrate_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually launch planners/workers, write checkpoints, mutate lifecycle, and delegate finalization.",
    )

    transition_parser = subparsers.add_parser(
        "transition",
        help="Preview or apply a task-status transition (dry-run by default).",
    )
    transition_parser.add_argument("task_id", help="Task identifier, e.g. TASK-009")
    transition_parser.add_argument(
        "--to",
        required=True,
        choices=[s.value for s in TaskStatus],
        help="Requested task status.",
    )
    transition_parser.add_argument(
        "--actor",
        required=True,
        choices=[r.value for r in ActorRole],
        help="Actor role requesting the transition (controller = controller/reviewer).",
    )
    transition_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rewrite the task file (default is preview only).",
    )

    review_bundle_parser = subparsers.add_parser(
        "review-bundle",
        help="Inspect a controller review bundle (read-only).",
    )
    review_bundle_subparsers = review_bundle_parser.add_subparsers(
        dest="review_bundle_command", required=True
    )
    show_parser = review_bundle_subparsers.add_parser(
        "show", help="Show a review bundle summary."
    )
    show_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a bundle file, or "latest" for the most recent bundle (default: latest).',
    )

    controller_decision_parser = subparsers.add_parser(
        "controller-decision",
        help="Record or inspect a controller decision against a review bundle.",
    )
    controller_decision_subparsers = controller_decision_parser.add_subparsers(
        dest="controller_decision_command", required=True
    )
    record_parser = controller_decision_subparsers.add_parser(
        "record", help="Record a controller decision against a review bundle."
    )
    record_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a review bundle, or "latest" for the most recent bundle (default: latest).',
    )
    record_parser.add_argument(
        "--decision",
        required=True,
        choices=[d.value for d in DecisionValue],
        help="Controller decision value.",
    )
    record_parser.add_argument(
        "--actor",
        required=True,
        choices=[r.value for r in ActorRole],
        help="Actor role recording the decision (controller = controller/reviewer).",
    )
    record_parser.add_argument(
        "--note",
        default=None,
        help="Optional bounded rationale for the decision.",
    )
    decision_show_parser = controller_decision_subparsers.add_parser(
        "show", help="Show a controller decision record (read-only)."
    )
    decision_show_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a decision record, or "latest" for the most recent record (default: latest).',
    )
    apply_parser = controller_decision_subparsers.add_parser(
        "apply", help="Preview or apply a controller decision to a task lifecycle."
    )
    apply_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a decision record, or "latest" for the most recent record (default: latest).',
    )
    apply_parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply_bridge",
        help="Actually request the lifecycle transition (default is preview only).",
    )

    controller_handoff_parser = subparsers.add_parser(
        "controller-handoff",
        help="Prepare, inspect, or reconcile a controller handoff request.",
    )
    controller_handoff_subparsers = controller_handoff_parser.add_subparsers(
        dest="controller_handoff_command", required=True
    )
    handoff_prepare_parser = controller_handoff_subparsers.add_parser(
        "prepare", help="Prepare a handoff request from a review bundle."
    )
    handoff_prepare_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a review bundle, or "latest" for the most recent bundle (default: latest).',
    )
    handoff_show_parser = controller_handoff_subparsers.add_parser(
        "show", help="Show a handoff request (read-only)."
    )
    handoff_show_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a handoff request, or "latest" for the most recent request (default: latest).',
    )
    handoff_reconcile_parser = controller_handoff_subparsers.add_parser(
        "reconcile", help="Reconcile a handoff request with a controller decision."
    )
    handoff_reconcile_parser.add_argument(
        "request_target",
        nargs="?",
        default="latest",
        help='Path to a handoff request, or "latest" for the most recent request (default: latest).',
    )
    handoff_reconcile_parser.add_argument(
        "decision_target",
        nargs="?",
        default="latest",
        help='Path to a decision record, or "latest" for the most recent record (default: latest).',
    )

    controller_adapter_parser = subparsers.add_parser(
        "controller-adapter",
        help="Dispatch or inspect a controller adapter against a handoff request.",
    )
    controller_adapter_subparsers = controller_adapter_parser.add_subparsers(
        dest="controller_adapter_command", required=True
    )
    adapter_dispatch_parser = controller_adapter_subparsers.add_parser(
        "dispatch",
        help="Dispatch a controller adapter for a handoff request.",
    )
    adapter_dispatch_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a handoff request, or "latest" for the most recent request (default: latest).',
    )
    adapter_dispatch_parser.add_argument(
        "--adapter",
        default="manual",
        help="Controller adapter to use (default: manual).",
    )
    adapter_status_parser = controller_adapter_subparsers.add_parser(
        "status",
        help="Inspect a handoff request through the controller adapter (read-only).",
    )
    adapter_status_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a handoff request, or "latest" for the most recent request (default: latest).',
    )

    controller_transport_parser = subparsers.add_parser(
        "controller-transport",
        help="Create, inspect, or validate controller transport envelopes.",
    )
    controller_transport_subparsers = controller_transport_parser.add_subparsers(
        dest="controller_transport_command", required=True
    )
    transport_request_parser = controller_transport_subparsers.add_parser(
        "request",
        help="Create a transport request envelope from a handoff request.",
    )
    transport_request_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a handoff request, or "latest" for the most recent request (default: latest).',
    )
    transport_request_parser.add_argument(
        "--adapter",
        default="manual",
        help="Controller adapter name the envelope is addressed to (default: manual).",
    )
    transport_request_parser.add_argument(
        "--adapter-type",
        default=None,
        help="Optional transport adapter type hint (e.g. local, remote).",
    )
    transport_show_parser = controller_transport_subparsers.add_parser(
        "show",
        help="Show a transport request or response envelope (read-only).",
    )
    transport_show_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a transport envelope, or "latest" for the most recent envelope (default: latest).',
    )
    transport_validate_parser = controller_transport_subparsers.add_parser(
        "validate-response",
        help="Validate a transport response envelope and reconcile any decision.",
    )
    transport_validate_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a transport response envelope, or "latest" for the most recent response (default: latest).',
    )

    driver_send_parser = controller_transport_subparsers.add_parser(
        "driver-send",
        help="Send a transport request envelope through the local driver.",
    )
    driver_send_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a request envelope or handoff request, or "latest" for the latest handoff (default: latest).',
    )

    driver_receive_parser = controller_transport_subparsers.add_parser(
        "driver-receive",
        help="Receive a transport response envelope through the local driver.",
    )
    driver_receive_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a request envelope, a request id, or "latest" for the latest outbox request (default: latest).',
    )

    driver_show_parser = controller_transport_subparsers.add_parser(
        "driver-show",
        help="Show local driver artifacts for a request id (read-only).",
    )
    driver_show_parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help='Path to a request envelope, a request id, or "latest" for the latest outbox request (default: latest).',
    )

    args = parser.parse_args(argv)

    if args.command == "controller-transport":
        try:
            git_info = get_git_info(cwd=Path.cwd())
        except Exception as exc:
            print(
                _format_transport_request_result(
                    None, None, None, error=f"cannot inspect Git repository: {exc}"
                ),
                file=sys.stderr,
            )
            return 1

        transport_dir = default_transport_dir(git_info.repo_root)

        if args.controller_transport_command == "request":
            handoff_dir = git_info.repo_root / ".agent_runner" / "controller_handoff"
            target = args.target
            if target.lower() == "latest":
                handoff_path = find_latest_handoff(handoff_dir)
                if handoff_path is None:
                    print(
                        _format_transport_request_result(
                            None, None, None,
                            error=f"no handoff requests found in {handoff_dir}",
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                handoff_path = Path(target)
                if not handoff_path.is_absolute():
                    handoff_path = Path.cwd() / handoff_path

            try:
                handoff = load_controller_handoff(handoff_path)
            except ControllerHandoffError as exc:
                print(
                    _format_transport_request_result(
                        None, None, None, error=f"cannot load handoff request: {exc}"
                    ),
                    file=sys.stderr,
                )
                return 1

            try:
                envelope = handoff_to_transport_request(
                    handoff_path=handoff_path,
                    handoff=handoff,
                    adapter_name=args.adapter,
                    adapter_type=args.adapter_type,
                    repo_root=git_info.repo_root,
                )
            except ControllerTransportError as exc:
                print(
                    _format_transport_request_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            try:
                envelope_path = write_transport_request(envelope, transport_dir)
            except ControllerTransportWriteError as exc:
                print(
                    _format_transport_request_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            audit_path: Path | None = None
            audit_write_error: str | None = None
            try:
                audit_payload = build_controller_transport_audit_payload(
                    task_id=envelope.task_id,
                    task_filename=envelope.task_filename,
                    request_id=envelope.request_id,
                    state=envelope.handoff_state,
                    request_path=envelope.handoff_request_path,
                    bundle_path=envelope.review_bundle_path,
                    branch=git_info.current_branch,
                    head_sha=git_info.head_sha,
                )
                audit_path = write_audit_record(
                    audit_payload, default_audit_dir(git_info.repo_root)
                )
            except AuditWriteError as exc:
                audit_write_error = str(exc)

            rel_envelope_path = envelope_path
            try:
                rel_envelope_path = envelope_path.relative_to(git_info.repo_root)
            except ValueError:
                pass

            print(
                _format_transport_request_result(
                    rel_envelope_path, audit_path, audit_write_error
                )
            )
            return 0

        if args.controller_transport_command == "show":
            target = args.target
            if target.lower() == "latest":
                envelope_path = find_latest_transport_request(transport_dir)
                if envelope_path is None:
                    envelope_path = find_latest_transport_response(transport_dir)
                if envelope_path is None:
                    print(
                        f"FAIL: no transport envelopes found in {transport_dir}",
                        file=sys.stderr,
                    )
                    return 1
            else:
                envelope_path = Path(target)
                if not envelope_path.is_absolute():
                    envelope_path = Path.cwd() / envelope_path

            try:
                data = json.loads(envelope_path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(
                    f"FAIL: cannot read transport envelope {envelope_path}: {exc}",
                    file=sys.stderr,
                )
                return 1

            schema = data.get("schema")
            try:
                if schema == TRANSPORT_REQUEST_SCHEMA:
                    request = validate_transport_request(data)
                    print(format_transport_request_summary(request))
                elif schema == TRANSPORT_RESPONSE_SCHEMA:
                    response = validate_transport_response(data)
                    print(format_transport_response_summary(response))
                else:
                    print(
                        f"FAIL: unknown transport envelope schema: {schema!r}",
                        file=sys.stderr,
                    )
                    return 1
            except ControllerTransportError as exc:
                print(
                    f"FAIL: invalid transport envelope: {exc}",
                    file=sys.stderr,
                )
                return 1

            return 0

        if args.controller_transport_command == "validate-response":
            target = args.target
            if target.lower() == "latest":
                envelope_path = find_latest_transport_response(transport_dir)
                if envelope_path is None:
                    print(
                        f"FAIL: no transport response envelopes found in {transport_dir}",
                        file=sys.stderr,
                    )
                    return 1
            else:
                envelope_path = Path(target)
                if not envelope_path.is_absolute():
                    envelope_path = Path.cwd() / envelope_path

            try:
                response = load_transport_response(envelope_path)
            except ControllerTransportError as exc:
                print(
                    _format_transport_response_result(
                        ControllerAdapterResult(
                            adapter_name="transport",
                            state=AdapterResultState.BLOCKED.value,
                            messages=[f"cannot load transport response: {exc}"],
                        )
                    ),
                    file=sys.stderr,
                )
                return 1

            result = apply_transport_response(
                response, repo_root=git_info.repo_root, git_info=git_info
            )
            print(_format_transport_response_result(result))
            return 0 if result else 1

        if args.controller_transport_command == "driver-send":
            outbox_dir, inbox_dir = default_driver_dirs(git_info.repo_root)
            handoff_dir = git_info.repo_root / ".agent_runner" / "controller_handoff"
            driver = LocalFilesystemTransportDriver(git_info.repo_root)

            try:
                request = _resolve_transport_request_target(
                    args.target,
                    git_info.repo_root,
                    outbox_dir,
                    handoff_dir,
                    latest_from_outbox=False,
                )
            except ControllerTransportDriverError as exc:
                print(
                    _format_driver_send_result(None, error=str(exc)),
                    file=sys.stderr,
                )
                return 1

            try:
                sent_path = driver.send(request)
            except ControllerTransportDriverConflictError as exc:
                print(
                    _format_driver_send_result(None, error=f"conflict: {exc}"),
                    file=sys.stderr,
                )
                return 1
            except (ControllerTransportError, ControllerTransportWriteError) as exc:
                print(
                    _format_driver_send_result(None, error=str(exc)),
                    file=sys.stderr,
                )
                return 1

            audit_path: Path | None = None
            audit_write_error: str | None = None
            try:
                audit_payload = build_controller_transport_audit_payload(
                    task_id=request.task_id,
                    task_filename=request.task_filename,
                    request_id=request.request_id,
                    state=request.handoff_state,
                    request_path=request.handoff_request_path,
                    bundle_path=request.review_bundle_path,
                    branch=git_info.current_branch,
                    head_sha=git_info.head_sha,
                )
                audit_path = write_audit_record(
                    audit_payload, default_audit_dir(git_info.repo_root)
                )
            except AuditWriteError as exc:
                audit_write_error = str(exc)

            rel_path = sent_path
            try:
                rel_path = sent_path.relative_to(git_info.repo_root)
            except ValueError:
                pass

            print(_format_driver_send_result(rel_path))
            if audit_path:
                print(f"Audit record: {audit_path}")
            elif audit_write_error:
                print(f"Audit record: NOT WRITTEN ({audit_write_error})")
            return 0

        if args.controller_transport_command == "driver-receive":
            outbox_dir, inbox_dir = default_driver_dirs(git_info.repo_root)
            handoff_dir = git_info.repo_root / ".agent_runner" / "controller_handoff"
            driver = LocalFilesystemTransportDriver(git_info.repo_root)

            try:
                request = _resolve_transport_request_target(
                    args.target,
                    git_info.repo_root,
                    outbox_dir,
                    handoff_dir,
                    latest_from_outbox=True,
                )
            except ControllerTransportDriverError as exc:
                print(
                    _format_driver_send_result(None, error=str(exc)),
                    file=sys.stderr,
                )
                return 1

            try:
                response = driver.receive(request)
            except (
                ControllerTransportDriverNotFoundError,
                ControllerTransportDriverAmbiguousError,
                ControllerTransportValidationError,
            ) as exc:
                print(
                    _format_driver_send_result(None, error=str(exc)),
                    file=sys.stderr,
                )
                return 1

            audit_path = None
            audit_write_error = None
            try:
                audit_payload = build_controller_transport_audit_payload(
                    task_id=request.task_id,
                    task_filename=request.task_filename,
                    request_id=request.request_id,
                    state=response.result_state,
                    request_path=request.handoff_request_path,
                    bundle_path=request.review_bundle_path,
                    decision_path=response.decision_path,
                    decision=response.decision,
                    branch=git_info.current_branch,
                    head_sha=git_info.head_sha,
                )
                audit_path = write_audit_record(
                    audit_payload, default_audit_dir(git_info.repo_root)
                )
            except AuditWriteError as exc:
                audit_write_error = str(exc)

            print(_format_driver_receive_result(response))
            if audit_path:
                print(f"Audit record: {audit_path}")
            elif audit_write_error:
                print(f"Audit record: NOT WRITTEN ({audit_write_error})")
            return 0

        if args.controller_transport_command == "driver-show":
            outbox_dir, inbox_dir = default_driver_dirs(git_info.repo_root)
            handoff_dir = git_info.repo_root / ".agent_runner" / "controller_handoff"
            driver = LocalFilesystemTransportDriver(git_info.repo_root)

            try:
                request = _resolve_transport_request_target(
                    args.target,
                    git_info.repo_root,
                    outbox_dir,
                    handoff_dir,
                    latest_from_outbox=True,
                )
            except ControllerTransportDriverError as exc:
                print(
                    _format_driver_send_result(None, error=str(exc)),
                    file=sys.stderr,
                )
                return 1

            view = driver.show(request.request_id)
            print(format_driver_view_summary(view))
            return 0

        print(
            f"FAIL: unknown controller-transport command: {args.controller_transport_command}",
            file=sys.stderr,
        )
        return 1

    if args.command == "controller-adapter":
        try:
            git_info = get_git_info(cwd=Path.cwd())
        except Exception as exc:
            print(
                _format_controller_adapter_result(
                    ControllerAdapterResult(
                        adapter_name="manual",
                        state=AdapterResultState.BLOCKED.value,
                        messages=[f"cannot inspect Git repository: {exc}"],
                    )
                ),
                file=sys.stderr,
            )
            return 1

        if args.controller_adapter_command == "dispatch":
            result = dispatch_controller_adapter(
                handoff_target=args.target,
                adapter=args.adapter,
                repo_root=git_info.repo_root,
                git_info=git_info,
            )
            print(_format_controller_adapter_result(result))
            return 0 if result else 1

        if args.controller_adapter_command == "status":
            result = inspect_controller_adapter_status(
                handoff_target=args.target,
                repo_root=git_info.repo_root,
                git_info=git_info,
            )
            print(_format_controller_adapter_result(result))
            return 0 if result else 1

        print(
            f"FAIL: unknown controller-adapter command: {args.controller_adapter_command}",
            file=sys.stderr,
        )
        return 1

    if args.command == "controller-handoff":
        try:
            git_info = get_git_info(cwd=Path.cwd())
        except Exception as exc:
            print(
                _format_handoff_prepare_result(
                    None, None, None, error=f"cannot inspect Git repository: {exc}"
                ),
                file=sys.stderr,
            )
            return 1

        if args.controller_handoff_command == "prepare":
            review_dir = git_info.repo_root / ".agent_runner" / "review"
            target = args.target
            if target.lower() == "latest":
                bundle_path = find_latest_bundle(review_dir)
                if bundle_path is None:
                    print(
                        _format_handoff_prepare_result(
                            None, None, None, error=f"no review bundles found in {review_dir}"
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                bundle_path = Path(target)
                if not bundle_path.is_absolute():
                    bundle_path = Path.cwd() / bundle_path

            try:
                bundle = load_review_bundle(bundle_path)
            except ReviewBundleError as exc:
                print(
                    _format_handoff_prepare_result(
                        None, None, None, error=f"cannot load review bundle: {exc}"
                    ),
                    file=sys.stderr,
                )
                return 1

            try:
                handoff = build_controller_handoff(
                    bundle_path,
                    bundle,
                    git_info=git_info,
                    repo_root=git_info.repo_root,
                )
            except ControllerHandoffError as exc:
                print(
                    _format_handoff_prepare_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            handoff_dir = default_handoff_dir(git_info.repo_root)
            try:
                handoff_path = write_controller_handoff(handoff, handoff_dir)
            except ControllerHandoffWriteError as exc:
                print(
                    _format_handoff_prepare_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            audit_path: Path | None = None
            audit_write_error: str | None = None
            try:
                audit_payload = build_handoff_audit_payload(
                    task_id=handoff.task_id,
                    task_filename=handoff.task_filename,
                    request_id=handoff.request_id,
                    mode="handoff_prepare",
                    state=handoff.state,
                    bundle_path=handoff.bundle_path,
                    bundle_branch=handoff.bundle_branch,
                    bundle_pre_head=handoff.bundle_pre_head,
                    bundle_post_head=handoff.bundle_post_head,
                    branch=git_info.current_branch,
                    head_sha=git_info.head_sha,
                )
                audit_path = write_audit_record(
                    audit_payload, default_audit_dir(git_info.repo_root)
                )
            except AuditWriteError as exc:
                audit_write_error = str(exc)

            rel_handoff_path = handoff_path
            try:
                rel_handoff_path = handoff_path.relative_to(git_info.repo_root)
            except ValueError:
                pass

            print(
                _format_handoff_prepare_result(
                    rel_handoff_path, audit_path, audit_write_error
                )
            )
            return 0

        if args.controller_handoff_command == "show":
            handoff_dir = git_info.repo_root / ".agent_runner" / "controller_handoff"
            target = args.target
            if target.lower() == "latest":
                handoff_path = find_latest_handoff(handoff_dir)
                if handoff_path is None:
                    print(
                        _format_handoff_prepare_result(
                            None, None, None, error=f"no handoff requests found in {handoff_dir}"
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                handoff_path = Path(target)
                if not handoff_path.is_absolute():
                    handoff_path = Path.cwd() / handoff_path

            try:
                handoff = load_controller_handoff(handoff_path)
            except ControllerHandoffError as exc:
                print(
                    _format_handoff_prepare_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            print(format_handoff_summary(handoff))
            return 0

        if args.controller_handoff_command == "reconcile":
            handoff_dir = git_info.repo_root / ".agent_runner" / "controller_handoff"
            decisions_dir = git_info.repo_root / ".agent_runner" / "decisions"

            request_target = args.request_target
            if request_target.lower() == "latest":
                request_path = find_latest_handoff(handoff_dir)
                if request_path is None:
                    print(
                        _format_handoff_reconcile_result(
                            HandoffReconciliationResult(
                                ok=False,
                                messages=[f"no handoff requests found in {handoff_dir}"],
                            )
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                request_path = Path(request_target)
                if not request_path.is_absolute():
                    request_path = Path.cwd() / request_path

            decision_target = args.decision_target
            if decision_target.lower() == "latest":
                decision_path = find_latest_decision(decisions_dir)
                if decision_path is None:
                    print(
                        _format_handoff_reconcile_result(
                            HandoffReconciliationResult(
                                ok=False,
                                messages=[f"no decision records found in {decisions_dir}"],
                            )
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                decision_path = Path(decision_target)
                if not decision_path.is_absolute():
                    decision_path = Path.cwd() / decision_path

            result = reconcile_controller_handoff(
                request_path=request_path,
                decision_path=decision_path,
                repo_root=git_info.repo_root,
                git_info=git_info,
            )
            print(_format_handoff_reconcile_result(result))
            return 0 if result.ok else 1

        print(
            f"FAIL: unknown controller-handoff command: {args.controller_handoff_command}",
            file=sys.stderr,
        )
        return 1

    if args.command == "controller-decision":
        try:
            git_info = get_git_info(cwd=Path.cwd())
        except Exception as exc:
            print(
                _format_decision_record_result(None, None, None, error=f"cannot inspect Git repository: {exc}"),
                file=sys.stderr,
            )
            return 1

        if args.controller_decision_command == "record":
            review_dir = git_info.repo_root / ".agent_runner" / "review"
            target = args.target
            if target.lower() == "latest":
                bundle_path = find_latest_bundle(review_dir)
                if bundle_path is None:
                    print(
                        _format_decision_record_result(
                            None, None, None, error=f"no review bundles found in {review_dir}"
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                bundle_path = Path(target)
                if not bundle_path.is_absolute():
                    bundle_path = Path.cwd() / bundle_path

            try:
                bundle = load_review_bundle(bundle_path)
            except ReviewBundleError as exc:
                print(
                    _format_decision_record_result(
                        None, None, None, error=f"cannot load review bundle: {exc}"
                    ),
                    file=sys.stderr,
                )
                return 1

            try:
                decision = build_controller_decision(
                    bundle_path,
                    bundle,
                    decision=args.decision,
                    actor_role=args.actor,
                    note=args.note,
                    repo_root=git_info.repo_root,
                )
            except ControllerDecisionError as exc:
                print(
                    _format_decision_record_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            decisions_dir = default_decisions_dir(git_info.repo_root)
            try:
                decision_path = write_controller_decision(decision, decisions_dir)
            except ControllerDecisionWriteError as exc:
                print(
                    _format_decision_record_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            audit_path: Path | None = None
            audit_write_error: str | None = None
            try:
                audit_payload = build_controller_decision_audit_payload(
                    task_id=decision.task_id,
                    task_filename=decision.task_filename,
                    actor_role=decision.actor_role,
                    decision=decision.decision,
                    bundle_path=decision.bundle_path,
                    bundle_branch=decision.bundle_branch,
                    bundle_pre_head=decision.bundle_pre_head,
                    bundle_post_head=decision.bundle_post_head,
                    decision_path=str(decision_path.relative_to(git_info.repo_root)),
                )
                audit_path = write_audit_record(
                    audit_payload, default_audit_dir(git_info.repo_root)
                )
            except AuditWriteError as exc:
                audit_write_error = str(exc)

            rel_decision_path = decision_path
            try:
                rel_decision_path = decision_path.relative_to(git_info.repo_root)
            except ValueError:
                pass

            print(_format_decision_record_result(rel_decision_path, audit_path, audit_write_error))
            return 0

        if args.controller_decision_command == "show":
            decisions_dir = git_info.repo_root / ".agent_runner" / "decisions"
            target = args.target
            if target.lower() == "latest":
                decision_path = find_latest_decision(decisions_dir)
                if decision_path is None:
                    print(
                        _format_decision_record_result(
                            None, None, None, error=f"no decision records found in {decisions_dir}"
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                decision_path = Path(target)
                if not decision_path.is_absolute():
                    decision_path = Path.cwd() / decision_path

            try:
                decision = load_controller_decision(decision_path)
            except ControllerDecisionError as exc:
                print(
                    _format_decision_record_result(
                        None, None, None, error=str(exc)
                    ),
                    file=sys.stderr,
                )
                return 1

            print(format_decision_summary(decision))
            return 0

        if args.controller_decision_command == "apply":
            decisions_dir = git_info.repo_root / ".agent_runner" / "decisions"
            tasks_dir = git_info.repo_root / "tasks"
            target = args.target
            if target.lower() == "latest":
                decision_path = find_latest_decision(decisions_dir)
                if decision_path is None:
                    print(
                        _format_bridge_result(
                            DecisionLifecycleResult(
                                ok=False,
                                messages=[f"no decision records found in {decisions_dir}"],
                            )
                        ),
                        file=sys.stderr,
                    )
                    return 1
            else:
                decision_path = Path(target)
                if not decision_path.is_absolute():
                    decision_path = Path.cwd() / decision_path

            result = apply_controller_decision(
                repo_root=git_info.repo_root,
                tasks_dir=tasks_dir,
                decision_path=decision_path,
                apply=args.apply_bridge,
                git_info=git_info,
            )
            print(_format_bridge_result(result))
            return 0 if result.ok else 1

        print(
            f"FAIL: unknown controller-decision command: {args.controller_decision_command}",
            file=sys.stderr,
        )
        return 1

    if args.command == "review-bundle":
        if args.review_bundle_command != "show":
            print(f"FAIL: unknown review-bundle command: {args.review_bundle_command}", file=sys.stderr)
            return 1

        try:
            git_info = get_git_info(cwd=Path.cwd())
        except Exception as exc:
            print(f"FAIL: cannot inspect Git repository: {exc}", file=sys.stderr)
            return 1

        review_dir = git_info.repo_root / ".agent_runner" / "review"
        target = args.target
        if target.lower() == "latest":
            bundle_path = find_latest_bundle(review_dir)
            if bundle_path is None:
                print(
                    f"FAIL: no review bundles found in {review_dir}",
                    file=sys.stderr,
                )
                return 1
        else:
            bundle_path = Path(target)
            if not bundle_path.is_absolute():
                bundle_path = Path.cwd() / bundle_path

        try:
            bundle = load_review_bundle(bundle_path)
        except ReviewBundleError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1

        print(format_bundle_summary(bundle))
        return 0

    tasks_dir = Path.cwd() / "tasks"

    if args.command == "goal-task":
        try:
            git_info = get_git_info(cwd=tasks_dir)
        except Exception as exc:
            result = GoalTaskGenerationResult(
                ok=False,
                status=GoalTaskGenerationStatus.PRECONDITION_FAILED,
                messages=[f"FAIL: cannot inspect Git repository: {exc}"],
            )
            print(format_goal_task_report(result), file=sys.stderr)
            return 1

        if args.planner == "kimi":
            planner: WorkerAdapter = KimiWorkerAdapter()
        elif args.planner == "kimi-swarm":
            planner = KimiSwarmWorkerAdapter()
        else:
            planner = DryRunWorkerAdapter()

        result = generate_goal_task(
            repo_root=git_info.repo_root,
            tasks_dir=tasks_dir,
            goal=args.goal,
            planner=planner,
            execute=args.execute,
        )
        print(format_goal_task_report(result))
        success = result.ok or result.status == GoalTaskGenerationStatus.DRY_RUN
        return 0 if success else 1

    if args.command == "orchestrate":
        try:
            git_info = get_git_info(cwd=tasks_dir)
        except Exception as exc:
            print(
                _format_orchestration_result(
                    OrchestrationResult(
                        ok=False,
                        run_id="n/a",
                        task_id=None,
                        task_path=None,
                        phase=OrchestrationPhase.FAILED.value,
                        status=OrchestrationStatus.FAILED.value,
                        completed_phases=[],
                        branch=None,
                        head=None,
                        evidence_paths={},
                        controller_gate=None,
                        mutations_performed=[],
                        blocking_reason=f"cannot inspect Git repository: {exc}",
                        owner_decision_required=False,
                        next_action="inspect repository and retry",
                        resume_command="n/a",
                    )
                ),
                file=sys.stderr,
            )
            return 1

        if args.goal and args.resume_run_id:
            print(
                "FAIL: --goal and --resume are mutually exclusive",
                file=sys.stderr,
            )
            return 1
        if not args.goal and not args.resume_run_id:
            print(
                "FAIL: either --goal or --resume is required",
                file=sys.stderr,
            )
            return 1

        config = OrchestrationConfig(
            goal=args.goal,
            resume_run_id=args.resume_run_id,
            planner=args.planner,
            worker=args.worker,
            fallback_worker=args.fallback_worker,
            controller=args.controller,
            repair_attempts=args.repair_attempts,
            max_rework=args.max_rework,
            apply=args.apply,
        )
        try:
            result = run_orchestration(config, repo_root=git_info.repo_root)
        except OrchestrationError as exc:
            print(
                _format_orchestration_result(
                    OrchestrationResult(
                        ok=False,
                        run_id=args.resume_run_id or "n/a",
                        task_id=None,
                        task_path=None,
                        phase=OrchestrationPhase.FAILED.value,
                        status=OrchestrationStatus.FAILED.value,
                        completed_phases=[],
                        branch=git_info.current_branch,
                        head=git_info.head_sha,
                        evidence_paths={},
                        controller_gate=None,
                        mutations_performed=[],
                        blocking_reason=str(exc),
                        owner_decision_required=False,
                        next_action="inspect error and resume or start a new run",
                        resume_command=(
                            f".venv/bin/python -m advancore.agent_runner orchestrate "
                            f"--resume {args.resume_run_id} --apply"
                            if args.resume_run_id
                            else "n/a"
                        ),
                    )
                ),
                file=sys.stderr,
            )
            return 1

        print(_format_orchestration_result(result))
        return 0 if result.ok else 1

    if args.command == "transition":
        try:
            git_info = get_git_info(cwd=tasks_dir)
        except Exception as exc:
            print(f"FAIL: cannot inspect Git repository: {exc}", file=sys.stderr)
            return 1

        result = transition_task(
            tasks_dir,
            args.task_id,
            args.to,
            args.actor,
            apply=args.apply,
            git_info=git_info,
        )
        print(_format_lifecycle_result(result))
        return 0 if result.ok else 1

    if args.command == "auto":
        try:
            git_info = get_git_info(cwd=tasks_dir)
        except Exception as exc:
            print(
                f"FAIL: cannot inspect Git repository: {exc}", file=sys.stderr
            )
            return 1

        try:
            validate_worker_policy(args.worker, args.fallback_worker)
            worker = build_worker_adapter(args.worker)
            fallback_worker = (
                build_worker_adapter(args.fallback_worker)
                if args.fallback_worker else None
            )
        except WorkerError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1

        result = run_auto_pipeline(
            tasks_dir,
            args.task_id,
            worker=worker,
            fallback_worker=fallback_worker,
            max_repair_attempts=args.repair_attempts,
        )
        print(format_auto_pipeline_report(result))
        return 0 if result.status == AutoPipelineStatus.READY_FOR_APPROVAL else 1

    if args.command == "finalize":
        try:
            git_info = get_git_info(cwd=tasks_dir)
        except Exception as exc:
            print(
                f"FAIL: cannot inspect Git repository: {exc}", file=sys.stderr
            )
            return 1

        decision_target = args.decision if args.decision != "latest" else None
        result = run_finalization(
            repo_root=git_info.repo_root,
            tasks_dir=tasks_dir,
            task_id=args.task_id,
            decision_path=decision_target,
            commit_message=args.message,
            apply=args.apply,
        )
        print(_format_finalize_result(result))
        return 0 if result.ok else 1

    worker = KimiWorkerAdapter() if args.worker == "kimi" else DryRunWorkerAdapter()

    if args.execute:
        result = execute(tasks_dir, args.task_id, worker=worker)
    else:
        result = plan(tasks_dir, args.task_id, worker=worker)

    print(_format_result(result))

    if result.status in (
        RunnerStatus.FAILED,
        RunnerStatus.WORKER_FAILED,
        RunnerStatus.POST_WORKER_VERIFICATION_FAILED,
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
