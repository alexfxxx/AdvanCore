"""Deterministic, bounded formatter for persistent Kimi launch results.

This module produces controller-facing display evidence from a
`PersistentKimiLaunchResult`.  The output contains only the bounded metadata
fields carried by the result and never includes repository paths, prompts,
commands, PATH values, stdout/stderr, credentials, environment values, or
arbitrary exception text.
"""

from __future__ import annotations

import math
import re

from advancore.agent_runner.kimi_swarm_eligibility import SwarmEligibilityReason
from advancore.agent_runner.persistent_kimi_launch import (
    PersistentKimiLaunchReason,
    PersistentKimiLaunchResult,
    PersistentKimiLaunchStatus,
)
from advancore.agent_runner.worker import (
    EXECUTABLE_NOT_FOUND,
    MAX_WORKER_TIMEOUT_SECONDS,
    RUNTIME_ERROR,
    SPAWN_ERROR,
)


_TERMINAL_REASONS = frozenset(
    {
        "completed",
        "launch_failed",
        "credential_access_required",
        "authority_blocked",
        "quota_or_capacity",
        "timeout",
        "cancelled",
        "runtime_error",
    }
)
_FAILURE_CLASSIFICATIONS = frozenset(
    {EXECUTABLE_NOT_FOUND, SPAWN_ERROR, RUNTIME_ERROR}
)
_CLI_VERSION = re.compile(r"^Kimi v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$")
_MAX_SCOPE_COUNT = 64
_MAX_OUTPUT_BYTES = 1024


def _malformed() -> TypeError:
    return TypeError("malformed PersistentKimiLaunchResult")


def _validate(result: PersistentKimiLaunchResult) -> None:
    if (
        type(result) is not PersistentKimiLaunchResult
        or type(result.ok) is not bool
        or type(result.status) is not PersistentKimiLaunchStatus
        or type(result.reason)
        not in {PersistentKimiLaunchReason, SwarmEligibilityReason}
        or type(result.scope_count) is not int
        or not 0 <= result.scope_count <= _MAX_SCOPE_COUNT
        or type(result.changed_paths) is not tuple
        or (
            result.worker_terminal_reason is not None
            and (
                type(result.worker_terminal_reason) is not str
                or result.worker_terminal_reason not in _TERMINAL_REASONS
            )
        )
        or (
            result.worker_failure_classification is not None
            and (
                type(result.worker_failure_classification) is not str
                or result.worker_failure_classification
                not in _FAILURE_CLASSIFICATIONS
            )
        )
        or (
            result.worker_returncode is not None
            and (
                type(result.worker_returncode) is not int
                or not -255 <= result.worker_returncode <= 255
            )
        )
        or (
            result.worker_elapsed_seconds is not None
            and (
                type(result.worker_elapsed_seconds) not in {int, float}
                or not math.isfinite(result.worker_elapsed_seconds)
                or not 0
                <= result.worker_elapsed_seconds
                <= MAX_WORKER_TIMEOUT_SECONDS + 5
            )
        )
        or (
            result.worker_cli_version is not None
            and (
                type(result.worker_cli_version) is not str
                or _CLI_VERSION.fullmatch(result.worker_cli_version) is None
            )
        )
    ):
        raise _malformed()


def format_persistent_kimi_launch_result(result: PersistentKimiLaunchResult) -> str:
    """Return a deterministic plain-text rendering of `result`.

    Only the bounded fields exposed by `PersistentKimiLaunchResult` are
    rendered.  Optional worker metadata that is ``None`` is represented as the
    literal string ``not-reported``.  Elapsed seconds, when present, are
    formatted with exactly six decimal places.

    Args:
        result: A ``PersistentKimiLaunchResult`` instance.

    Returns:
        Deterministic plain text with one key/value pair per line.

    Raises:
        TypeError: If ``result`` is not an actual ``PersistentKimiLaunchResult``.
    """
    _validate(result)

    def _or_not_reported(value: object | None) -> str:
        return "not-reported" if value is None else str(value)

    elapsed = (
        "not-reported"
        if result.worker_elapsed_seconds is None
        else f"{result.worker_elapsed_seconds:.6f}"
    )

    lines = [
        f"status: {result.status.value}",
        f"reason: {result.reason.value}",
        f"scope_count: {result.scope_count}",
        f"changed_path_count: {len(result.changed_paths)}",
        f"worker_terminal_reason: {_or_not_reported(result.worker_terminal_reason)}",
        f"worker_failure_classification: {_or_not_reported(result.worker_failure_classification)}",
        f"worker_returncode: {_or_not_reported(result.worker_returncode)}",
        f"worker_elapsed_seconds: {elapsed}",
        f"worker_cli_version: {_or_not_reported(result.worker_cli_version)}",
    ]
    rendered = "\n".join(lines) + "\n"
    if len(rendered.encode("ascii")) > _MAX_OUTPUT_BYTES:
        raise _malformed()
    return rendered


__all__ = ["format_persistent_kimi_launch_result"]
