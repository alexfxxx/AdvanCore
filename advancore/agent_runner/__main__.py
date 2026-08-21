"""CLI entry point for the local agent runner.

Default behaviour is dry-run planning. Use ``--execute`` to actually invoke
a worker adapter, and choose the worker with ``--worker``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from advancore.agent_runner.audit import (
    AuditWriteError,
    build_controller_decision_audit_payload,
    build_handoff_audit_payload,
    default_audit_dir,
    write_audit_record,
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
from advancore.agent_runner.worker import DryRunWorkerAdapter, KimiWorkerAdapter


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

    args = parser.parse_args(argv)

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
