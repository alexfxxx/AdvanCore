"""Worker-boundary tests for runtime-authoritative Kimi routing."""

from datetime import datetime, timedelta, timezone
import subprocess
from unittest.mock import patch

import pytest

from advancore.agent_runner.auto_pipeline import (
    ProviderFailure,
    classify_provider_failure,
)
from advancore.agent_runner.worker import (
    CodexWorkerAdapter,
    KimiSwarmWorkerAdapter,
    KimiWorkerAdapter,
    WorkerResult,
    _isolate_kimi_command,
    _kimi_environment,
    _kimi_workspace_id,
    run_bounded_worker_process,
)
from advancore.services.worker_usage_service import WorkerUsageService


def _usage_dir(tmp_path):
    return tmp_path.parent / f"{tmp_path.name}-controller" / "usage"


@pytest.mark.parametrize("evidence", ["missing", "stale", "over-limit", "unreadable"])
@pytest.mark.parametrize("adapter_type", [KimiWorkerAdapter, KimiSwarmWorkerAdapter])
def test_legacy_usage_evidence_never_gates_kimi_launch(
    tmp_path, evidence, adapter_type
):
    usage_dir = _usage_dir(tmp_path)
    if evidence != "missing":
        usage_dir.mkdir(parents=True)
        if evidence == "unreadable":
            (usage_dir / "kimi-reported.json").write_bytes(b"not-json-\xff")
        elif evidence == "stale":
            (usage_dir / "kimi-reported.json").write_text(
                '{"provider":"kimi","checked_at":"2020-01-01T00:00:00+00:00"}',
                encoding="utf-8",
            )
        else:
            now = datetime.now(timezone.utc)
            used = 44 if evidence == "over-limit" else 1
            WorkerUsageService(tmp_path, usage_dir=usage_dir).record_snapshot(
                "kimi", used, now, now + timedelta(days=4), "owner-verified"
            )
    expected = WorkerResult(True, message="attempted")
    adapter = adapter_type(timeout_seconds=321)
    with patch(
        "advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"
    ), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=True
    ), patch(
        "advancore.services.worker_usage_service.WorkerUsageService.auto_refresh_if_needed",
        side_effect=AssertionError("usage refresh must not run"),
    ), patch(
        "advancore.services.worker_usage_service.WorkerUsageService.preflight",
        side_effect=AssertionError("usage preflight must not run"),
    ), patch(
        "advancore.services.worker_usage_service.WorkerUsageService.record_runtime",
        side_effect=AssertionError("runtime accounting must not run"),
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process",
        return_value=expected,
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result is expected
    bounded.assert_called_once()
    assert bounded.call_args.args[0][0] == "/usr/bin/sandbox-exec"
    assert bounded.call_args.args[2] == 321
    assert bounded.call_args.args[3] is None
    assert bounded.call_args.args[4]["KIMI_DISABLE_TELEMETRY"] == "1"


def test_kimi_sandbox_and_environment_still_protect_credentials(tmp_path, monkeypatch):
    scratch = tmp_path.parent / "reviewed-kimi-scratch"
    scratch.mkdir()
    command = _isolate_kimi_command(
        ["/usr/bin/kimi", "--prompt", "instruction"], None, tmp_path, scratch
    )
    profile = command[2]
    assert "(deny file-link)" in profile
    assert f'(subpath "{tmp_path.resolve()}")' in profile
    for protected in (".git", ".agent_runner", ".venv", ".ssh"):
        assert str(tmp_path.resolve() / protected) in profile
    assert "agent_runner" in profile
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-worker")
    monkeypatch.setenv("DATABASE_URL", "must-not-reach-worker")
    environment = _kimi_environment(scratch)
    assert environment["TMPDIR"] == str(scratch)
    assert environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert "GITHUB_TOKEN" not in environment
    assert "DATABASE_URL" not in environment


def test_kimi_workspace_id_matches_v038_storage_name(tmp_path):
    workspace = tmp_path / "AdvanCore-task-144"
    workspace.mkdir()
    workspace_id = _kimi_workspace_id(workspace)
    assert workspace_id.startswith("wd_advancore-task-144_")
    assert len(workspace_id.rsplit("_", 1)[1]) == 12


def test_kimi_sandbox_allows_only_current_workspace_bookkeeping(tmp_path):
    from pathlib import Path

    scratch = tmp_path.parent / "kimi-scratch"
    scratch.mkdir()
    command = _isolate_kimi_command(
        ["/usr/bin/kimi", "--prompt", "instruction"], None, tmp_path, scratch
    )
    profile = command[2]
    owner_home = Path.home()
    workspace_id = _kimi_workspace_id(tmp_path)
    exact_trust = owner_home / ".kimi-code" / "workspace-trust" / workspace_id
    registry = owner_home / ".kimi-code" / "workspaces.json"
    trust_root = owner_home / ".kimi-code" / "workspace-trust"
    assert f'(literal "{exact_trust}")' in profile
    assert f'(literal "{registry}")' in profile
    assert f'(subpath "{trust_root}")' not in profile
    assert "wd_unrelated_000000000000" not in profile


@pytest.mark.parametrize("adapter_type", [KimiWorkerAdapter, KimiSwarmWorkerAdapter])
def test_kimi_blocks_without_os_isolation(tmp_path, adapter_type):
    adapter = adapter_type()
    with patch(
        "advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/kimi"
    ), patch(
        "advancore.agent_runner.worker._kimi_isolation_available", return_value=False
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process"
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result.success is False
    assert result.terminal_reason == "quota_or_capacity"
    assert classify_provider_failure(result) == ProviderFailure.QUOTA_OR_CAPACITY
    bounded.assert_not_called()


def test_kimi_isolation_probe_requires_successful_sandbox_start():
    from advancore.agent_runner.worker import _kimi_isolation_available

    with patch("advancore.agent_runner.worker.Path.is_file", return_value=True), patch(
        "advancore.agent_runner.worker.subprocess.run",
        return_value=subprocess.CompletedProcess([], 71),
    ) as run:
        assert _kimi_isolation_available() is False
    assert run.call_args.args[0][-1] == "/usr/bin/true"


def test_timeout_remains_terminal(tmp_path):
    with patch(
        "advancore.agent_runner.worker._git_evidence", return_value={"ambiguous": False}
    ), patch("advancore.agent_runner.worker.subprocess.Popen") as popen:
        process = popen.return_value
        process.pid = 123
        process.communicate.side_effect = subprocess.TimeoutExpired(["kimi"], 1)
        process.poll.return_value = None
        process.returncode = -15
        with patch(
            "advancore.agent_runner.worker._terminate_process_group", return_value=True
        ):
            result = run_bounded_worker_process(["kimi"], tmp_path, 1)
    assert not result.success
    assert result.terminal_reason == "timeout"


def test_codex_does_not_depend_on_kimi_usage_evidence(tmp_path):
    adapter = CodexWorkerAdapter()
    expected = WorkerResult(True, message="ok")
    with patch(
        "advancore.agent_runner.worker.shutil.which", return_value="/usr/bin/codex"
    ), patch(
        "advancore.agent_runner.worker.run_bounded_worker_process",
        return_value=expected,
    ) as bounded:
        result = adapter.run("instruction", tmp_path)
    assert result is expected
    bounded.assert_called_once()
