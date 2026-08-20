"""CLI entry point for the local agent runner.

Default behaviour is dry-run planning. Use ``--execute`` to actually invoke
a worker adapter, and choose the worker with ``--worker``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

    args = parser.parse_args(argv)

    tasks_dir = Path.cwd() / "tasks"
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
