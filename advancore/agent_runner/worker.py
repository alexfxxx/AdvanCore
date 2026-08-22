"""Worker adapter boundary for the local agent runner."""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


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


APPROVED_WORKER_NAMES: tuple[str, ...] = (
    "dry-run",
    "kimi",
    "kimi-swarm",
    "codex",
)


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

    DEFAULT_EXECUTABLE: ClassVar[str] = "kimi"

    def __init__(
        self, executable: str | None = None, allowed_scope: list[str] | None = None
    ):
        self.executable = executable or self.DEFAULT_EXECUTABLE
        self.allowed_scope = allowed_scope or []

    @property
    def name(self) -> str:
        return "kimi"

    def build_command(self, instruction: str, working_dir: Path) -> list[str]:
        return [self.executable, "--prompt", instruction]

    def run(self, instruction: str, working_dir: Path) -> WorkerResult:
        if not shutil.which(self.executable):
            return WorkerResult(
                success=False,
                message=f"Worker executable '{self.executable}' not found in PATH",
            )

        command = self.build_command(
            _governed_instruction(instruction, self.allowed_scope), working_dir
        )
        try:
            result = subprocess.run(
                command,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return WorkerResult(
                success=False,
                command=command,
                message=f"Worker launch failed: {exc}",
            )

        return WorkerResult(
            success=result.returncode == 0,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            message=(
                "Worker finished successfully"
                if result.returncode == 0
                else "Worker finished with non-zero exit code"
            ),
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

    DEFAULT_EXECUTABLE: ClassVar[str] = "kimi"

    def __init__(
        self,
        executable: str | None = None,
        allowed_scope: list[str] | None = None,
    ):
        self.executable = executable or self.DEFAULT_EXECUTABLE
        self.allowed_scope = allowed_scope or []

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
        if not shutil.which(self.executable):
            return WorkerResult(
                success=False,
                message=f"Worker executable '{self.executable}' not found in PATH",
            )

        command = self.build_command(
            _governed_instruction(instruction, self.allowed_scope), working_dir
        )
        try:
            result = subprocess.run(
                command,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return WorkerResult(
                success=False,
                command=command,
                message=f"Worker launch failed: {exc}",
            )

        return WorkerResult(
            success=result.returncode == 0,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            message=(
                "Swarm worker finished successfully"
                if result.returncode == 0
                else "Swarm worker finished with non-zero exit code"
            ),
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

    def __init__(self, allowed_scope: list[str] | None = None):
        self.executable = self.DEFAULT_EXECUTABLE
        self.allowed_scope = allowed_scope or []

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
            result = subprocess.run(
                command,
                cwd=working_dir.resolve(strict=True),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return WorkerResult(
                success=False,
                message=f"Worker launch failed: {type(exc).__name__}",
            )
        return WorkerResult(
            success=result.returncode == 0,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            message=(
                "Worker finished successfully"
                if result.returncode == 0
                else "Worker finished with non-zero exit code"
            ),
        )


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
    name: str, allowed_scope: list[str] | None = None
) -> WorkerAdapter:
    """Build one fixed, registered adapter; never accept executable or argv input."""
    validate_worker_policy(name)
    scope = allowed_scope or []
    if name == "kimi":
        return KimiWorkerAdapter(allowed_scope=scope)
    if name == "kimi-swarm":
        return KimiSwarmWorkerAdapter(allowed_scope=scope)
    if name == "codex":
        return CodexWorkerAdapter(allowed_scope=scope)
    return DryRunWorkerAdapter()
