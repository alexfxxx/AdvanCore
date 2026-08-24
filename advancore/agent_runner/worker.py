"""Worker adapter boundary for the local agent runner."""

from __future__ import annotations

import shutil
import math
import os
import pwd
import re
import signal
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from advancore.services.worker_usage_service import (
    UsageBudgetError,
    UsagePreflight,
    WorkerUsageService,
)


class WorkerError(Exception):
    """Raised when a worker adapter encounters an unsupported configuration."""


@dataclass
class WorkerResult:
    """Result of a worker invocation attempt."""

    success: bool
    command: list[str] | None = None
    stdout: str | None = None
    stderr: str | None = None
    returncode: int | None = None
    message: str = ""
    terminal_reason: str = "completed"
    timeout_seconds: int | None = None
    recovery_action: str | None = None
    repository_state: dict[str, object] | None = None


DEFAULT_WORKER_TIMEOUT_SECONDS = 30 * 60
MAX_WORKER_TIMEOUT_SECONDS = 2 * 60 * 60
WORKER_TERMINATION_GRACE_SECONDS = 1
WORKER_RECOVERY_ACTION = (
    "Explicitly resume or start a separately reviewed worker invocation."
)
KIMI_EXECUTABLE = "kimi"
KIMI_SANDBOX_EXECUTABLE = Path("/usr/bin/sandbox-exec")
KIMI_SANDBOX_PROBE_TIMEOUT_SECONDS = 5
KIMI_SANDBOX_PROBE_PROFILE = (
    '(version 1) (allow default) '
    '(deny file-write* (require-not (subpath "/private/tmp")))'
)
KIMI_RUNTIME_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
KIMI_INHERITED_LOCALE_VARIABLES: tuple[str, ...] = (
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
)


def _kimi_isolation_available() -> bool:
    """Prove that the approved local Kimi OS confinement can actually start."""
    if not KIMI_SANDBOX_EXECUTABLE.is_file():
        return False
    try:
        completed = subprocess.run(
            [
                str(KIMI_SANDBOX_EXECUTABLE),
                "-p",
                KIMI_SANDBOX_PROBE_PROFILE,
                "/usr/bin/true",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=KIMI_SANDBOX_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _sandbox_literal(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def _kimi_environment(scratch_dir: Path) -> dict[str, str]:
    """Return a minimal fixed environment for one governed Kimi launch.

    The controller environment can contain unrelated provider, database, GitHub,
    proxy, and loader credentials.  A governed implementation worker receives
    only fixed runtime paths plus non-sensitive locale values; any future
    task-required credential must cross a separately approved capability
    boundary instead of being inherited implicitly.
    """
    account = pwd.getpwuid(os.getuid())
    account_home = Path(account.pw_dir).resolve()
    environment = {
        "HOME": str(account_home),
        "USER": account.pw_name,
        "LOGNAME": account.pw_name,
        "PATH": KIMI_RUNTIME_PATH,
        "KIMI_CODE_HOME": str(account_home / ".kimi-code"),
        "KIMI_DISABLE_TELEMETRY": "1",
        "TMPDIR": str(scratch_dir),
        "TMP": str(scratch_dir),
        "TEMP": str(scratch_dir),
        "XDG_CACHE_HOME": str(scratch_dir / "cache"),
    }
    for name in KIMI_INHERITED_LOCALE_VARIABLES:
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _isolate_kimi_command(
    command: list[str],
    service: WorkerUsageService | None,
    working_dir: Path,
    scratch_dir: Path,
) -> list[str]:
    """Confine Kimi writes to the repository and reviewed runtime paths."""
    if service is None:
        return command
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    kimi_home = account_home / ".kimi-code"
    writable_subpaths = (
        working_dir.resolve(strict=True),
        scratch_dir.resolve(strict=True),
        kimi_home / "cache",
        kimi_home / "logs",
        kimi_home / "sessions",
        kimi_home / "user-history",
    )
    writable_literals = (kimi_home / "session_index.jsonl",)
    allow_filters = " ".join(
        [f'(subpath "{_sandbox_literal(path)}")' for path in writable_subpaths]
        + [f'(literal "{_sandbox_literal(path)}")' for path in writable_literals]
    )
    protected_subpaths = (
        service.protected_state_root,
        kimi_home / "bin",
        kimi_home / "credentials",
        kimi_home / "oauth",
        kimi_home / "plugins",
        kimi_home / "skills",
        kimi_home / "updates",
        Path("/opt/homebrew"),
        Path("/usr/local"),
    )
    deny_filters = " ".join(
        f'(deny file-write* (subpath "{_sandbox_literal(path)}"))'
        for path in protected_subpaths
    )
    profile = (
        "(version 1) (allow default) "
        f"(deny file-write* (require-not (require-any {allow_filters}))) "
        f"{deny_filters}"
    )
    return [str(KIMI_SANDBOX_EXECUTABLE), "-p", profile, *command]


def _kimi_usage_preflight(
    executable: str,
    working_dir: Path,
    timeout_seconds: int,
) -> tuple[WorkerUsageService | None, UsagePreflight | None, WorkerResult | None]:
    """Enforce the production Kimi budget before process launch.

    Custom executable overrides exist only as an injected deterministic test seam;
    registered production adapters always use the fixed ``kimi`` executable.
    """
    if executable != KIMI_EXECUTABLE:
        return None, None, None
    if not _kimi_isolation_available():
        return None, None, WorkerResult(
            success=False,
            message="provider quota/capacity paused: Kimi OS isolation is unavailable",
            terminal_reason="quota_or_capacity",
            timeout_seconds=timeout_seconds,
        )
    service = WorkerUsageService(working_dir)
    try:
        service.auto_refresh_if_needed("kimi")
        preflight = service.preflight("kimi", timeout_seconds)
    except UsageBudgetError as exc:
        message = str(exc)
        if not message.startswith("provider quota/capacity paused:"):
            message = f"provider quota/capacity paused: {message}"
        return service, None, WorkerResult(
            success=False,
            message=message,
            terminal_reason="quota_or_capacity",
            timeout_seconds=timeout_seconds,
        )
    return service, preflight, None


def _record_kimi_runtime(
    result: WorkerResult,
    service: WorkerUsageService | None,
    preflight: UsagePreflight | None,
    elapsed_seconds: float,
) -> WorkerResult:
    """Record bounded Kimi runtime and fail closed if accounting is ambiguous."""
    if service is None or preflight is None:
        return result
    try:
        service.record_runtime("kimi", elapsed_seconds, preflight)
    except UsageBudgetError:
        result.message = (
            f"{result.message}; provider quota/capacity runtime accounting failed"
        )
        if result.terminal_reason not in {"timeout", "cancelled"}:
            result.success = False
            result.terminal_reason = "usage_accounting_failed"
    return result


def validate_worker_timeout(value: int) -> int:
    """Return a safe timeout or reject non-integral/out-of-policy values."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkerError("worker timeout must be an unambiguous integer number of seconds")
    if value <= 0 or value > MAX_WORKER_TIMEOUT_SECONDS:
        raise WorkerError(
            f"worker timeout must be between 1 and {MAX_WORKER_TIMEOUT_SECONDS} seconds"
        )
    return value


def parse_worker_timeout(value: str) -> int:
    """Argparse-compatible strict timeout parser."""
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise WorkerError("worker timeout must be a canonical positive integer")
    return validate_worker_timeout(int(value))


def _git_evidence(repo_root: Path) -> dict[str, object]:
    """Independently capture bounded branch, HEAD, index, worktree, and remotes."""
    commands = {
        "branch": ["git", "branch", "--show-current"],
        "head": ["git", "rev-parse", "HEAD"],
        "index": ["git", "diff", "--cached", "--name-only"],
        "worktree": ["git", "status", "--porcelain=v1"],
        "remotes": ["git", "remote", "-v"],
    }
    evidence: dict[str, object] = {}
    ambiguous = False
    for name, command in commands.items():
        try:
            result = subprocess.run(
                command, cwd=repo_root, capture_output=True, text=True,
                check=False, timeout=10,
            )
            if result.returncode != 0:
                ambiguous = True
                evidence[name] = None
            else:
                evidence[name] = sorted(result.stdout.splitlines()) if name in {
                    "index", "worktree", "remotes"
                } else result.stdout.strip()
        except Exception:
            ambiguous = True
            evidence[name] = None
    evidence["ambiguous"] = ambiguous
    return evidence


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Terminate the complete worker group within a bounded grace period."""
    group_id = process.pid
    try:
        os.killpg(group_id, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + WORKER_TERMINATION_GRACE_SECONDS
    while time.monotonic() < deadline and _process_group_exists(group_id):
        time.sleep(0.02)
    if _process_group_exists(group_id):
        try:
            os.killpg(group_id, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=WORKER_TERMINATION_GRACE_SECONDS)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        pass


def run_bounded_worker_process(
    command: list[str],
    working_dir: Path,
    timeout_seconds: int,
    launch_deadline: datetime | None = None,
    environment: dict[str, str] | None = None,
) -> WorkerResult:
    """Run one local worker in an isolated session with governed termination."""
    timeout_seconds = validate_worker_timeout(timeout_seconds)
    repo_root = working_dir.resolve(strict=True)
    before = _git_evidence(repo_root)
    if launch_deadline is not None:
        if launch_deadline.tzinfo is None:
            return WorkerResult(
                success=False,
                command=command,
                message="provider quota/capacity paused: launch deadline is invalid",
                terminal_reason="quota_or_capacity",
                timeout_seconds=timeout_seconds,
            )
        deadline_remaining = math.floor(
            (
                launch_deadline.astimezone(timezone.utc)
                - datetime.now(timezone.utc)
            ).total_seconds()
        )
        if deadline_remaining <= 0:
            return WorkerResult(
                success=False,
                command=command,
                message="provider quota/capacity paused: provider reset reached before launch",
                terminal_reason="quota_or_capacity",
                timeout_seconds=timeout_seconds,
            )
        timeout_seconds = min(timeout_seconds, deadline_remaining)
    try:
        process = subprocess.Popen(
            command, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True, env=environment,
        )
    except Exception as exc:
        return WorkerResult(
            success=False, command=command,
            message=f"Worker launch failed: {type(exc).__name__}",
            terminal_reason="launch_failed", timeout_seconds=timeout_seconds,
        )
    terminal_reason: str | None = None
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        terminal_reason = "timeout"
        _terminate_process_group(process)
    except KeyboardInterrupt:
        terminal_reason = "cancelled"
        _terminate_process_group(process)

    if terminal_reason is not None:
        after = _git_evidence(repo_root)
        unchanged = not before.get("ambiguous") and not after.get("ambiguous") and before == after
        state = {
            "unchanged": unchanged,
            "ambiguous": bool(before.get("ambiguous") or after.get("ambiguous")),
            "branch": after.get("branch"),
            "head": after.get("head"),
            "index_changed": before.get("index") != after.get("index"),
            "worktree_changed": before.get("worktree") != after.get("worktree"),
            "remotes_changed": before.get("remotes") != after.get("remotes"),
        }
        message = f"Worker {terminal_reason}; repository state " + (
            "unchanged" if unchanged else "mutated or ambiguous; controller review required"
        )
        return WorkerResult(
            success=False, command=command, returncode=process.poll(), message=message,
            terminal_reason=terminal_reason, timeout_seconds=timeout_seconds,
            recovery_action=WORKER_RECOVERY_ACTION if unchanged else None,
            repository_state=state,
        )

    return WorkerResult(
        success=process.returncode == 0, command=command, stdout=stdout, stderr=stderr,
        returncode=process.returncode, timeout_seconds=timeout_seconds,
        message="Worker finished successfully" if process.returncode == 0
        else "Worker finished with non-zero exit code",
    )


APPROVED_WORKER_NAMES: tuple[str, ...] = (
    "dry-run",
    "kimi",
    "kimi-swarm",
    "codex",
)
APPROVED_PLANNER_NAMES: tuple[str, ...] = APPROVED_WORKER_NAMES
DEFAULT_PLANNER_TIMEOUT_SECONDS = 10 * 60


class WorkerAdapter(ABC):
    """Replaceable boundary between the runner and a concrete coding worker."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable worker adapter name."""
        ...

    @abstractmethod
    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        """Return the argument array that would be executed for *instruction*."""
        ...

    @abstractmethod
    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        """Run the worker for *instruction* and return a controlled result."""
        ...


WORKER_INSTRUCTION_TEMPLATE = """Read AGENTS.md.

Execute {task_path} completely.

Implementation-worker role limits:
- Modify ONLY the task's allowed paths.
- Do not commit until explicitly approved; never stage, push, merge, deploy, switch branches, alter remotes, or finalize.
- Do not decide/approve, transition DRAFT to READY, or self-approve.
- Do not access credentials, production data/systems, bypass the sandbox, use cloud/remote execution, or web search.

Stop with the completion report and git status."""


def build_worker_instruction(
    task_path: str, allowed_scope: list[str] | None = None
) -> str:
    """Return the canonical bounded worker instruction for *task_path*.

    *task_path* is the repository-relative path to the task file, e.g.
    ``tasks/TASK-005-local-agent-runner-foundation.md``.
    """
    instruction = WORKER_INSTRUCTION_TEMPLATE.format(task_path=task_path)
    if allowed_scope:
        instruction += "\n\nAllowed changed-file scope:\n- " + "\n- ".join(allowed_scope)
    return instruction


def _governed_instruction(instruction: str, allowed_scope: list[str]) -> str:
    """Add the code-owned scope when the runner supplied its base instruction."""
    if not allowed_scope or "Allowed changed-file scope:" in instruction:
        return instruction
    return instruction + "\n\nAllowed changed-file scope:\n- " + "\n- ".join(allowed_scope)


class KimiWorkerAdapter(WorkerAdapter):
    """Adapter for the local Kimi Code CLI.

    Uses ``kimi --prompt <instruction>`` for non-interactive, single-prompt
    execution. This is a bounded invocation mode documented by the local
    ``kimi --help`` output. The adapter never adds autonomous flags such as
    ``--auto`` or ``--yolo``; those remain gated for explicit future policy.
    """

    DEFAULT_EXECUTABLE: ClassVar[str] = KIMI_EXECUTABLE

    def __init__(
        self, executable: str | None = None, allowed_scope: list[str] | None = None,
        timeout_seconds: int = DEFAULT_WORKER_TIMEOUT_SECONDS,
        implementation_worker: bool = True,
    ):
        self.executable = executable or self.DEFAULT_EXECUTABLE
        self.allowed_scope = allowed_scope or []
        self.timeout_seconds = validate_worker_timeout(timeout_seconds)
        self.implementation_worker = implementation_worker

    @property
    def name(self) -> str:
        return "kimi"

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return [self.executable, "--prompt", instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        resolved_executable = shutil.which(self.executable)
        if not resolved_executable:
            return WorkerResult(
                success=False,
                message=f"Worker executable '{self.executable}' not found in PATH",
            )
        command = self.build_command(
            _governed_instruction(instruction, self.allowed_scope), working_dir
        )
        command[0] = resolved_executable
        with tempfile.TemporaryDirectory(
            prefix="advancore-kimi-", dir="/tmp"
        ) as scratch_name:
            scratch_dir = Path(scratch_name).resolve(strict=True)
            usage_service, usage_preflight, blocked = _kimi_usage_preflight(
                self.executable, working_dir, self.timeout_seconds
            )
            if blocked is not None:
                return blocked
            command = _isolate_kimi_command(
                command, usage_service, working_dir, scratch_dir
            )
            environment = (
                _kimi_environment(scratch_dir) if usage_service is not None else None
            )
            effective_timeout = (
                usage_preflight.allowed_timeout_seconds
                if usage_preflight is not None else self.timeout_seconds
            )
            started_at = time.monotonic()
            # Preserve the established injectable subprocess seam used by local
            # callers/tests; production uses the bounded Popen implementation.
            if (not self.implementation_worker
                    and getattr(subprocess.run, "__module__", "subprocess") != "subprocess"):
                completed = subprocess.run(
                    command, cwd=working_dir, capture_output=True, text=True,
                    check=False, env=environment,
                )
                result = WorkerResult(
                    success=completed.returncode == 0, command=command,
                    stdout=completed.stdout, stderr=completed.stderr,
                    returncode=completed.returncode, timeout_seconds=effective_timeout,
                    message="Worker finished successfully" if completed.returncode == 0
                    else "Worker finished with non-zero exit code",
                )
                return _record_kimi_runtime(
                    result, usage_service, usage_preflight, time.monotonic() - started_at
                )
            result = run_bounded_worker_process(
                command,
                working_dir,
                effective_timeout,
                usage_preflight.launch_deadline if usage_preflight is not None else None,
                environment,
            )
            return _record_kimi_runtime(
                result, usage_service, usage_preflight, time.monotonic() - started_at
            )


KIMI_SWARM_INSTRUCTION_TEMPLATE = """Read AGENTS.md.

Execute {task_path} completely using Kimi's AgentSwarm capability for implementation and review work.

Governance inherited by every swarm/sub-agent:
- Read approved repository files as needed.
- Modify ONLY paths authorized by the task's allowed changed-file scope.
- Run local tests/inspection necessary for implementation.
- Do NOT stage, commit, push, merge, switch branches, tag, reset, rebase, or rewrite history.
- Do NOT access credentials, secrets, or production databases.
- Do NOT deploy or alter production systems.
- Do NOT change commercial/compliance policy.
- Do NOT declare the work approved.
- Stop with a completion report and git status.

Do not commit or push until explicitly approved.

Stop with the completion report and git status."""


def build_kimi_swarm_instruction(task_path: str, allowed_scope: list[str] | None = None) -> str:
    """Return the canonical bounded swarm worker instruction for *task_path*.

    The instruction explicitly requests Kimi's AgentSwarm capability and
    restates the task's allowed changed-file scope and prohibited actions so
    that every sub-agent inherits the same governance boundary.
    """
    instruction = KIMI_SWARM_INSTRUCTION_TEMPLATE.format(task_path=task_path)
    scope_lines = list(allowed_scope) if allowed_scope else []
    if scope_lines:
        instruction += (
            "\n\nAllowed changed-file scope:\n- "
            + "\n- ".join(scope_lines)
            + "\n"
        )
    return instruction


class KimiSwarmWorkerAdapter(WorkerAdapter):
    """Bounded Kimi Swarm worker adapter.

    The installed Kimi CLI (as of the local inspection performed by TASK-017)
    does not expose a documented non-interactive ``AgentSwarm`` subcommand. This
    adapter therefore uses the same safe ``kimi --prompt <instruction>`` boundary
    as ``KimiWorkerAdapter`` but sends a canonical instruction that explicitly
    requires Kimi's AgentSwarm capability for implementation/review work.

    The adapter never adds autonomous flags such as ``--auto`` or ``--yolo``,
    and it never falls back to unrestricted permission-bypass modes.
    """

    DEFAULT_EXECUTABLE: ClassVar[str] = KIMI_EXECUTABLE

    def __init__(
        self,
        executable: str | None = None,
        allowed_scope: list[str] | None = None,
        timeout_seconds: int = DEFAULT_WORKER_TIMEOUT_SECONDS,
        implementation_worker: bool = True,
    ):
        self.executable = executable or self.DEFAULT_EXECUTABLE
        self.allowed_scope = allowed_scope or []
        self.timeout_seconds = validate_worker_timeout(timeout_seconds)
        self.implementation_worker = implementation_worker

    @property
    def name(self) -> str:
        return "kimi-swarm"

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return [self.executable, "--prompt", instruction]

    def build_swarm_command(self, task_path: str, working_dir: Path) -> list[str]:
        """Return the argument array for the bounded swarm instruction."""
        instruction = build_kimi_swarm_instruction(
            task_path=task_path,
            allowed_scope=self.allowed_scope,
        )
        return self.build_command(instruction, working_dir)

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        resolved_executable = shutil.which(self.executable)
        if not resolved_executable:
            return WorkerResult(
                success=False,
                message=f"Worker executable '{self.executable}' not found in PATH",
            )
        command = self.build_command(
            _governed_instruction(instruction, self.allowed_scope), working_dir
        )
        command[0] = resolved_executable
        with tempfile.TemporaryDirectory(
            prefix="advancore-kimi-", dir="/tmp"
        ) as scratch_name:
            scratch_dir = Path(scratch_name).resolve(strict=True)
            usage_service, usage_preflight, blocked = _kimi_usage_preflight(
                self.executable, working_dir, self.timeout_seconds
            )
            if blocked is not None:
                return blocked
            command = _isolate_kimi_command(
                command, usage_service, working_dir, scratch_dir
            )
            environment = (
                _kimi_environment(scratch_dir) if usage_service is not None else None
            )
            effective_timeout = (
                usage_preflight.allowed_timeout_seconds
                if usage_preflight is not None else self.timeout_seconds
            )
            started_at = time.monotonic()
            if (not self.implementation_worker
                    and getattr(subprocess.run, "__module__", "subprocess") != "subprocess"):
                completed = subprocess.run(
                    command, cwd=working_dir, capture_output=True, text=True,
                    check=False, env=environment,
                )
                result = WorkerResult(
                    success=completed.returncode == 0, command=command,
                    stdout=completed.stdout, stderr=completed.stderr,
                    returncode=completed.returncode, timeout_seconds=effective_timeout,
                    message="Worker finished successfully" if completed.returncode == 0
                    else "Worker finished with non-zero exit code",
                )
                return _record_kimi_runtime(
                    result, usage_service, usage_preflight, time.monotonic() - started_at
                )
            result = run_bounded_worker_process(
                command,
                working_dir,
                effective_timeout,
                usage_preflight.launch_deadline if usage_preflight is not None else None,
                environment,
            )
            return _record_kimi_runtime(
                result, usage_service, usage_preflight, time.monotonic() - started_at
            )


class DryRunWorkerAdapter(WorkerAdapter):
    """Adapter that never launches a real worker.

    This is the default worker. It reports success without executing anything,
    so the runner can produce a complete plan without side effects.
    """

    @property
    def name(self) -> str:
        return "dry-run"

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return []

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        return WorkerResult(
            success=True,
            message="Dry-run: worker would not be launched.",
        )


class CodexWorkerAdapter(WorkerAdapter):
    """Safe local Codex CLI implementation-worker adapter.

    The argv is entirely code-owned. Credentials remain external to AdvanCore,
    and no config, writable-root, network, cloud, or bypass options are exposed.
    """

    DEFAULT_EXECUTABLE: ClassVar[str] = "codex"

    def __init__(self, allowed_scope: list[str] | None = None,
                 timeout_seconds: int = DEFAULT_WORKER_TIMEOUT_SECONDS):
        self.executable = self.DEFAULT_EXECUTABLE
        self.allowed_scope = allowed_scope or []
        self.timeout_seconds = validate_worker_timeout(timeout_seconds)

    @property
    def name(self) -> str:
        return "codex"

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        repo_root = working_dir.resolve(strict=True)
        return [
            self.executable,
            "--ask-for-approval",
            "never",
            "exec",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(repo_root),
            instruction,
        ]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        if not shutil.which(self.executable):
            return WorkerResult(
                success=False,
                message=f"Worker executable '{self.executable}' not found in PATH",
            )
        bounded_instruction = _governed_instruction(instruction, self.allowed_scope)
        try:
            command = self.build_command(bounded_instruction, working_dir)
            return run_bounded_worker_process(command, working_dir, self.timeout_seconds)
        except Exception as exc:  # pragma: no cover - defensive
            return WorkerResult(
                success=False,
                message=f"Worker launch failed: {type(exc).__name__}",
            )


class CodexPlannerAdapter(WorkerAdapter):
    """Proposal-only Codex adapter with a fixed read-only local boundary."""

    DEFAULT_EXECUTABLE: ClassVar[str] = "codex"

    def __init__(self, timeout_seconds: int = DEFAULT_PLANNER_TIMEOUT_SECONDS):
        self.executable = self.DEFAULT_EXECUTABLE
        self.timeout_seconds = validate_worker_timeout(timeout_seconds)

    @property
    def name(self) -> str:
        return "codex"

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        repo_root = working_dir.resolve(strict=True)
        return [
            self.executable, "--ask-for-approval", "never", "exec", "--ephemeral",
            "--sandbox", "read-only", "--cd", str(repo_root), instruction,
        ]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        if not shutil.which(self.executable):
            return WorkerResult(
                success=False,
                message=f"Worker executable '{self.executable}' not found in PATH",
                terminal_reason="launch_failed",
                timeout_seconds=self.timeout_seconds,
            )
        return run_bounded_worker_process(
            self.build_command(instruction, working_dir), working_dir, self.timeout_seconds
        )


def validate_planner_policy(primary: str, fallback: str | None = None) -> None:
    """Validate a fixed, explicit, single-hop proposal planner policy."""
    if primary not in APPROVED_PLANNER_NAMES:
        raise WorkerError(f"Unknown planner adapter: {primary!r}")
    if fallback is None:
        return
    if fallback not in APPROVED_PLANNER_NAMES:
        raise WorkerError(f"Unknown fallback planner adapter: {fallback!r}")
    if primary == "dry-run" or fallback == "dry-run":
        raise WorkerError("dry-run cannot participate in planner fallback")
    if primary == fallback:
        raise WorkerError("primary and fallback planners must be different")


def build_planner_adapter(
    name: str, timeout_seconds: int = DEFAULT_PLANNER_TIMEOUT_SECONDS
) -> WorkerAdapter:
    """Build one registered proposal-only planner with no caller-supplied argv."""
    validate_planner_policy(name)
    if name == "kimi":
        return KimiWorkerAdapter(
            timeout_seconds=timeout_seconds, implementation_worker=False
        )
    if name == "kimi-swarm":
        return KimiSwarmWorkerAdapter(
            timeout_seconds=timeout_seconds, implementation_worker=False
        )
    if name == "codex":
        return CodexPlannerAdapter(timeout_seconds=timeout_seconds)
    return DryRunWorkerAdapter()


def validate_worker_policy(primary: str, fallback: str | None = None) -> None:
    """Reject unregistered, duplicate, dry-run, or otherwise unsafe fallback policy."""
    if primary not in APPROVED_WORKER_NAMES:
        raise WorkerError(f"Unknown worker adapter: {primary!r}")
    if fallback is None:
        return
    if fallback not in APPROVED_WORKER_NAMES:
        raise WorkerError(f"Unknown fallback worker adapter: {fallback!r}")
    if fallback == "dry-run":
        raise WorkerError("dry-run cannot be configured as a fallback worker")
    if primary == "dry-run":
        raise WorkerError("dry-run primary cannot have a fallback worker")
    if primary == fallback:
        raise WorkerError("primary and fallback workers must be different")


def build_worker_adapter(
    name: str, allowed_scope: list[str] | None = None,
    timeout_seconds: int = DEFAULT_WORKER_TIMEOUT_SECONDS,
) -> WorkerAdapter:
    """Build one fixed, registered adapter; never accept executable or argv input."""
    validate_worker_policy(name)
    scope = allowed_scope or []
    if name == "kimi":
        return KimiWorkerAdapter(allowed_scope=scope, timeout_seconds=timeout_seconds)
    if name == "kimi-swarm":
        return KimiSwarmWorkerAdapter(allowed_scope=scope, timeout_seconds=timeout_seconds)
    if name == "codex":
        return CodexWorkerAdapter(allowed_scope=scope, timeout_seconds=timeout_seconds)
    return DryRunWorkerAdapter()
