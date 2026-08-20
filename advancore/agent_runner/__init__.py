"""AdvanCore local agent runner foundation.

This package provides a fail-closed orchestration control plane for bounded
AI-assisted development tasks. It discovers task files, validates repository
safety preconditions, generates canonical worker instructions, and abstracts
worker execution behind a replaceable adapter.

The default behaviour is dry-run / planning only. Actual worker execution is
opt-in and still leaves commit, push, merge, and other high-impact actions
gated for explicit human approval.
"""

from advancore.agent_runner.git_info import GitInfo, get_git_info
from advancore.agent_runner.lifecycle import (
    ActorRole,
    LifecycleResult,
    TaskStatus,
    is_transition_allowed,
    transition_task,
)
from advancore.agent_runner.runner import (
    PostWorkerVerification,
    RunnerResult,
    RunnerStatus,
    execute,
    plan,
)
from advancore.agent_runner.task import Task, TaskError, discover_tasks, find_task, parse_task
from advancore.agent_runner.validation import ValidationResult, validate
from advancore.agent_runner.worker import (
    DryRunWorkerAdapter,
    KimiWorkerAdapter,
    WorkerAdapter,
    WorkerResult,
    build_worker_instruction,
)

__all__ = [
    "ActorRole",
    "GitInfo",
    "LifecycleResult",
    "PostWorkerVerification",
    "RunnerResult",
    "RunnerStatus",
    "Task",
    "TaskError",
    "TaskStatus",
    "ValidationResult",
    "WorkerAdapter",
    "WorkerResult",
    "build_worker_instruction",
    "discover_tasks",
    "execute",
    "find_task",
    "get_git_info",
    "is_transition_allowed",
    "parse_task",
    "plan",
    "transition_task",
    "validate",
    "DryRunWorkerAdapter",
    "KimiWorkerAdapter",
]
