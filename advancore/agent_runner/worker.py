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

Do not commit or push until explicitly approved.

Stop with the completion report and git status."""


def build_worker_instruction(task_path: str) -> str:
    """Return the canonical bounded worker instruction for *task_path*.

    *task_path* is the repository-relative path to the task file, e.g.
    ``tasks/TASK-005-local-agent-runner-foundation.md``.
    """
    return WORKER_INSTRUCTION_TEMPLATE.format(task_path=task_path)


class KimiWorkerAdapter(WorkerAdapter):
    """Adapter for the local Kimi Code CLI.

    Uses ``kimi --prompt <instruction>`` for non-interactive, single-prompt
    execution. This is a bounded invocation mode documented by the local
    ``kimi --help`` output. The adapter never adds autonomous flags such as
    ``--auto`` or ``--yolo``; those remain gated for explicit future policy.
    """

    DEFAULT_EXECUTABLE: ClassVar[str] = "kimi"

    def __init__(self, executable: str | None = None):
        self.executable = executable or self.DEFAULT_EXECUTABLE

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

        command = self.build_command(instruction, working_dir)
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

        command = self.build_command(instruction, working_dir)
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
