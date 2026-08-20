"""Safety validation for agent-runner execution planning."""

from __future__ import annotations

from dataclasses import dataclass, field

from advancore.agent_runner.task import ALLOWED_STATUSES, Task


@dataclass
class ValidationResult:
    """Result of safety pre-flight checks."""

    ok: bool
    messages: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def validate(
    task: Task,
    current_branch: str,
    is_clean: bool,
    allowed_statuses: set[str] | None = None,
) -> ValidationResult:
    """Validate that *task* can be planned/executed safely.

    Checks:
      - current branch is not ``main``,
      - working tree is clean,
      - task status is in *allowed_statuses* (default ``READY``/``REWORK``).

    Returns a ``ValidationResult`` that is truthy iff all checks pass.
    """
    if allowed_statuses is None:
        allowed_statuses = ALLOWED_STATUSES

    messages: list[str] = []
    ok = True

    if current_branch == "main":
        messages.append("FAIL: execution on 'main' branch is not allowed")
        ok = False
    else:
        messages.append(f"PASS: current branch '{current_branch}' is not 'main'")

    if not is_clean:
        messages.append("FAIL: working tree has uncommitted changes")
        ok = False
    else:
        messages.append("PASS: working tree is clean")

    if task.status not in allowed_statuses:
        messages.append(
            f"FAIL: task status '{task.status}' is not executable "
            f"(must be one of {', '.join(sorted(allowed_statuses))})"
        )
        ok = False
    else:
        messages.append(f"PASS: task status '{task.status}' is executable")

    if ok:
        messages.append("PASS: all safety validations passed")

    return ValidationResult(ok=ok, messages=messages)
