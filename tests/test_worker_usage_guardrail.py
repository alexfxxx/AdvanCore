"""Worker-boundary tests for runtime-authoritative Kimi routing."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
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
    _kimi_runtime_preflight,
    _probe_kimi_cli_version,
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
    kimi_oauth = owner_home / ".kimi-code" / "oauth" / "kimi-code"
    kimi_oauth_lock = owner_home / ".kimi-code" / "oauth" / "kimi-code.lock"
    kimi_credentials = owner_home / ".kimi-code" / "credentials"
    kimi_credential_file = kimi_credentials / "kimi-code.json"
    trust_root = owner_home / ".kimi-code" / "workspace-trust"
    assert f'(literal "{exact_trust}")' in profile
    assert f'(literal "{registry}")' in profile
    assert f'(literal "{kimi_oauth}")' in profile
    assert f'(literal "{kimi_oauth_lock}")' in profile
    assert f'(literal "{kimi_credentials}")' in profile
    assert f'(literal "{kimi_credential_file}")' in profile
    assert f'(subpath "{trust_root}")' not in profile
    assert f'(subpath "{owner_home / ".kimi-code" / "oauth"}")' not in profile
    assert f'(subpath "{kimi_credentials}")' not in profile
    assert "workspaces\\.json\\.tmp\\." in profile
    assert workspace_id in profile
    assert "wd_unrelated_000000000000" not in profile


def _create_prewarmed_kimi_home(tmp_path):
    owner_home = tmp_path / "owner"
    executable = owner_home / ".kimi-code" / "bin" / "kimi"
    executable.parent.mkdir(parents=True)
    executable.write_text("binary", encoding="utf-8")
    executable.chmod(0o700)
    for relative in ("oauth/kimi-code", "credentials/kimi-code.json"):
        target = owner_home / ".kimi-code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prewarmed", encoding="utf-8")
        target.chmod(0o600)
    repository = owner_home / "work" / "AdvanCore"
    repository.mkdir(parents=True)
    trust_root = owner_home / ".kimi-code" / "workspace-trust"
    trust_root.mkdir()
    trust_file = trust_root / _kimi_workspace_id(owner_home)
    trust_file.write_text(
        json.dumps({"root": str(owner_home), "trustedAt": 1}),
        encoding="utf-8",
    )
    trust_file.chmod(0o600)
    return owner_home, executable, repository


def test_kimi_runtime_preflight_accepts_prewarmed_auth_and_ancestor_trust(tmp_path):
    owner_home, executable, repository = _create_prewarmed_kimi_home(tmp_path)
    with patch(
        "advancore.agent_runner.worker.pwd.getpwuid",
        return_value=SimpleNamespace(pw_dir=str(owner_home), pw_name="owner"),
    ):
        assert _kimi_runtime_preflight(str(executable), repository, 60) is None


def test_kimi_runtime_preflight_requires_auth_without_starting_login(tmp_path):
    owner_home, executable, repository = _create_prewarmed_kimi_home(tmp_path)
    (owner_home / ".kimi-code" / "oauth" / "kimi-code").unlink()
    with patch(
        "advancore.agent_runner.worker.pwd.getpwuid",
        return_value=SimpleNamespace(pw_dir=str(owner_home), pw_name="owner"),
    ):
        result = _kimi_runtime_preflight(str(executable), repository, 60)
    assert result is not None
    assert result.terminal_reason == "credential_access_required"
    assert "login required" in result.message.lower()


def test_kimi_runtime_preflight_requires_existing_workspace_trust(tmp_path):
    owner_home, executable, repository = _create_prewarmed_kimi_home(tmp_path)
    trust_file = next((owner_home / ".kimi-code" / "workspace-trust").iterdir())
    trust_file.unlink()
    with patch(
        "advancore.agent_runner.worker.pwd.getpwuid",
        return_value=SimpleNamespace(pw_dir=str(owner_home), pw_name="owner"),
    ):
        result = _kimi_runtime_preflight(str(executable), repository, 60)
    assert result is not None
    assert result.terminal_reason == "authority_blocked"


def test_kimi_version_probe_is_isolated_and_bounded(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with patch(
        "advancore.agent_runner.worker._isolate_kimi_command",
        return_value=["/usr/bin/sandbox-exec", "kimi", "--version"],
    ) as isolate, patch(
        "advancore.agent_runner.worker.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "0.38.0\n", ""),
    ) as run:
        version = _probe_kimi_cli_version(
            "/owner/.kimi-code/bin/kimi", tmp_path, scratch, {"HOME": "/owner"}
        )
    assert version == "Kimi v0.38.0"
    isolate.assert_called_once()
    assert run.call_args.kwargs["timeout"] == 5


def test_kimi_environment_never_inherits_unsupported_swarm_concurrency(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KIMI_CODE_AGENT_SWARM_MAX_CONCURRENCY", "10")
    environment = _kimi_environment(tmp_path)
    assert "KIMI_CODE_AGENT_SWARM_MAX_CONCURRENCY" not in environment


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
