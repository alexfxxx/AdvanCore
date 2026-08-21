"""AdvanCore local agent runner foundation.

This package provides a fail-closed orchestration control plane for bounded
AI-assisted development tasks. It discovers task files, validates repository
safety preconditions, generates canonical worker instructions, and abstracts
worker execution behind a replaceable adapter.

The default behaviour is dry-run / planning only. Actual worker execution is
opt-in and still leaves commit, push, merge, and other high-impact actions
gated for explicit human approval.
"""

from advancore.agent_runner.controller_decision import (
    ControllerDecision,
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
    ControllerHandoff,
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
    DecisionLifecycleBridgeError,
    DecisionLifecycleResult,
    apply_controller_decision,
)
from advancore.agent_runner.git_info import GitInfo, get_git_info
from advancore.agent_runner.review_bundle import (
    ControllerAction,
    ReviewBundle,
    ReviewBundleError,
    ReviewBundleWriteError,
    build_review_bundle,
    default_review_dir,
    find_latest_bundle,
    format_bundle_summary,
    load_review_bundle,
    write_review_bundle,
)
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
    "ControllerAction",
    "ControllerDecision",
    "ControllerDecisionError",
    "ControllerDecisionWriteError",
    "ControllerHandoff",
    "ControllerHandoffError",
    "ControllerHandoffWriteError",
    "DecisionLifecycleBridgeError",
    "DecisionLifecycleResult",
    "DecisionValue",
    "GitInfo",
    "HandoffReconciliationResult",
    "HandoffState",
    "LifecycleResult",
    "apply_controller_decision",
    "ReviewBundle",
    "ReviewBundleError",
    "ReviewBundleWriteError",
    "build_controller_decision",
    "build_controller_handoff",
    "build_review_bundle",
    "default_decisions_dir",
    "default_handoff_dir",
    "default_review_dir",
    "find_latest_decision",
    "find_latest_handoff",
    "find_latest_bundle",
    "format_decision_summary",
    "format_bundle_summary",
    "format_handoff_summary",
    "load_controller_decision",
    "load_controller_handoff",
    "load_review_bundle",
    "reconcile_controller_handoff",
    "write_controller_decision",
    "write_controller_handoff",
    "write_review_bundle",
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
