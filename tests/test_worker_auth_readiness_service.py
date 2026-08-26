from pathlib import Path
import subprocess

from advancore.services import worker_auth_readiness_service as module
from advancore.services.worker_auth_readiness_service import (
    WorkerAuthReadinessService,
    WorkerAuthState,
)


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_checks_use_fixed_non_generative_commands_and_minimal_environment(monkeypatch):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return completed()

    monkeypatch.setattr(module, "_candidate_executable", lambda worker: Path(f"/bin/{worker}"))
    results = WorkerAuthReadinessService(runner=runner).check_all()

    assert all(result.state == WorkerAuthState.AUTHENTICATED for result in results)
    assert [call[0][1:] for call in calls] == [
        ["provider", "list"],
        ["models"],
        ["login", "status"],
    ]
    for _, kwargs in calls:
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["timeout"] == 10
        assert set(kwargs["env"]) == {"HOME", "USER", "LOGNAME", "PATH", "LANG"}


def test_login_failure_is_bounded_and_never_returns_raw_output(monkeypatch):
    monkeypatch.setattr(module, "_candidate_executable", lambda worker: Path("/bin/tool"))
    service = WorkerAuthReadinessService(
        runner=lambda *_args, **_kwargs: completed(
            1, stderr="login required secret-account@example.com token=hidden"
        )
    )

    result = service.check("gemini")

    assert result.state == WorkerAuthState.LOGIN_REQUIRED
    assert "agy models" in result.login_instruction
    rendered = repr(result)
    assert "secret-account" not in rendered
    assert "token=hidden" not in rendered


def test_missing_or_timed_out_probe_is_unavailable_without_crashing(monkeypatch):
    monkeypatch.setattr(module, "_candidate_executable", lambda worker: None)
    assert WorkerAuthReadinessService().check("kimi").state == WorkerAuthState.UNAVAILABLE

    monkeypatch.setattr(module, "_candidate_executable", lambda worker: Path("/bin/tool"))
    service = WorkerAuthReadinessService(
        runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("tool", 10)
        )
    )
    assert service.check("codex").state == WorkerAuthState.UNAVAILABLE
