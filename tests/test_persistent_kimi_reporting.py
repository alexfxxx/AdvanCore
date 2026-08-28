"""Unit tests for the persistent Kimi launch result formatter."""

import pytest

from advancore.agent_runner import format_persistent_kimi_launch_result
from advancore.agent_runner.persistent_kimi_launch import (
    PersistentKimiLaunchReason,
    PersistentKimiLaunchResult,
    PersistentKimiLaunchStatus,
)
from advancore.agent_runner.worker import RUNTIME_ERROR


def test_success_result_with_all_worker_metadata():
    result = PersistentKimiLaunchResult(
        ok=True,
        status=PersistentKimiLaunchStatus.COMPLETED,
        reason=PersistentKimiLaunchReason.COMPLETED,
        changed_paths=("target.py",),
        scope_count=1,
        worker_terminal_reason="completed",
        worker_failure_classification=None,
        worker_returncode=0,
        worker_elapsed_seconds=2.5,
        worker_cli_version="Kimi v0.39.0",
    )

    output = format_persistent_kimi_launch_result(result)

    expected = (
        "status: COMPLETED\n"
        "reason: COMPLETED\n"
        "scope_count: 1\n"
        "changed_path_count: 1\n"
        "worker_terminal_reason: completed\n"
        "worker_failure_classification: not-reported\n"
        "worker_returncode: 0\n"
        "worker_elapsed_seconds: 2.500000\n"
        "worker_cli_version: Kimi v0.39.0\n"
    )
    assert output == expected


def test_preflight_failure_with_no_worker_metadata():
    result = PersistentKimiLaunchResult(
        ok=False,
        status=PersistentKimiLaunchStatus.PREFLIGHT_FAILED,
        reason=PersistentKimiLaunchReason.WORKSPACE_NOT_READY,
        changed_paths=(),
        scope_count=0,
    )

    output = format_persistent_kimi_launch_result(result)

    expected = (
        "status: PREFLIGHT_FAILED\n"
        "reason: WORKSPACE_NOT_READY\n"
        "scope_count: 0\n"
        "changed_path_count: 0\n"
        "worker_terminal_reason: not-reported\n"
        "worker_failure_classification: not-reported\n"
        "worker_returncode: not-reported\n"
        "worker_elapsed_seconds: not-reported\n"
        "worker_cli_version: not-reported\n"
    )
    assert output == expected


def test_worker_failure_with_partial_metadata():
    result = PersistentKimiLaunchResult(
        ok=False,
        status=PersistentKimiLaunchStatus.WORKER_FAILED,
        reason=PersistentKimiLaunchReason.WORKER_FAILED,
        changed_paths=("outside.py",),
        scope_count=1,
        worker_terminal_reason="runtime_error",
        worker_failure_classification=RUNTIME_ERROR,
        worker_returncode=3,
    )

    output = format_persistent_kimi_launch_result(result)

    assert output.splitlines() == [
        "status: WORKER_FAILED",
        "reason: WORKER_FAILED",
        "scope_count: 1",
        "changed_path_count: 1",
        "worker_terminal_reason: runtime_error",
        "worker_failure_classification: RUNTIME_ERROR",
        "worker_returncode: 3",
        "worker_elapsed_seconds: not-reported",
        "worker_cli_version: not-reported",
    ]


def test_absent_metadata_result():
    result = PersistentKimiLaunchResult(
        ok=True,
        status=PersistentKimiLaunchStatus.COMPLETED,
        reason=PersistentKimiLaunchReason.COMPLETED,
        changed_paths=(),
        scope_count=0,
        worker_terminal_reason=None,
        worker_failure_classification=None,
        worker_returncode=None,
        worker_elapsed_seconds=None,
        worker_cli_version=None,
    )

    output = format_persistent_kimi_launch_result(result)

    assert all(line.endswith(": not-reported") for line in output.splitlines()[4:])
    assert "changed_path_count: 0" in output


def test_invalid_input_does_not_echo_value():
    with pytest.raises(TypeError) as exc_info:
        format_persistent_kimi_launch_result("secret")  # type: ignore[arg-type]

    assert "secret" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("worker_terminal_reason", "DATABASE_URL=secret\ncommand: publish-main"),
        ("worker_failure_classification", "DATABASE_URL=secret"),
        ("worker_returncode", "DATABASE_URL=secret"),
        ("worker_returncode", 9999),
        ("worker_elapsed_seconds", float("nan")),
        ("worker_elapsed_seconds", -1.0),
        ("worker_cli_version", "Kimi v0.39.0\nDATABASE_URL=secret"),
        ("worker_cli_version", "secret" * 1000),
        ("scope_count", -1),
    ],
)
def test_malformed_fields_are_rejected_without_echo(field, value):
    values = {
        "ok": False,
        "status": PersistentKimiLaunchStatus.WORKER_FAILED,
        "reason": PersistentKimiLaunchReason.WORKER_FAILED,
        "changed_paths": (),
        "scope_count": 0,
        "worker_terminal_reason": "runtime_error",
        "worker_failure_classification": RUNTIME_ERROR,
        "worker_returncode": 3,
        "worker_elapsed_seconds": 1.0,
        "worker_cli_version": "Kimi v0.39.0",
    }
    values[field] = value
    result = PersistentKimiLaunchResult(**values)

    with pytest.raises(TypeError) as exc_info:
        format_persistent_kimi_launch_result(result)

    assert "secret" not in str(exc_info.value).lower()
    assert "database_url" not in str(exc_info.value).lower()


def test_malicious_field_object_cannot_run_during_formatting():
    class Explosive:
        def __str__(self):
            raise RuntimeError("private object text")

        def __format__(self, specification):
            raise RuntimeError("private object format")

    result = PersistentKimiLaunchResult(
        ok=True,
        status=PersistentKimiLaunchStatus.COMPLETED,
        reason=PersistentKimiLaunchReason.COMPLETED,
        changed_paths=(),
        scope_count=0,
        worker_cli_version=Explosive(),  # type: ignore[arg-type]
    )

    with pytest.raises(TypeError) as exc_info:
        format_persistent_kimi_launch_result(result)

    assert "private" not in str(exc_info.value).lower()


def test_large_out_of_scope_observation_still_formats_bounded_count():
    observed = tuple(
        f"DATABASE_URL=secret-{index}\ncommand: publish-main"
        for index in range(65)
    )
    result = PersistentKimiLaunchResult(
        ok=False,
        status=PersistentKimiLaunchStatus.POSTCHECK_FAILED,
        reason=PersistentKimiLaunchReason.OUT_OF_SCOPE_CHANGES,
        changed_paths=observed,
        scope_count=1,
    )

    output = format_persistent_kimi_launch_result(result)

    assert "changed_path_count: 65" in output
    assert "secret" not in output.lower()
    assert "publish-main" not in output.lower()
