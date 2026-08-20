"""CLI entry point for the local agent runner.

Default behaviour is dry-run planning. Use ``--execute`` to actually invoke
a worker adapter, and choose the worker with ``--worker``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

    args = parser.parse_args(argv)

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
