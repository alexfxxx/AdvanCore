"""Bounded, non-generative start-of-session AI authentication checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from typing import Callable


class WorkerAuthState(str, Enum):
    AUTHENTICATED = "AUTHENTICATED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class WorkerAuthReadiness:
    worker: str
    label: str
    state: WorkerAuthState
    message: str
    login_instruction: str | None


_PROBES = {
    "kimi": (
        "Kimi",
        ("provider", "list"),
        "Open Terminal and run: ~/.kimi-code/bin/kimi login --region global",
    ),
    "gemini": (
        "Gemini",
        ("models",),
        "Open Terminal and run: ~/.local/bin/agy models, then complete Google login.",
    ),
    "codex": (
        "Codex",
        ("login", "status"),
        "Open Terminal and run: codex login",
    ),
}


def _candidate_executable(worker: str) -> Path | None:
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    fixed = {
        "kimi": account_home / ".kimi-code" / "bin" / "kimi",
        "gemini": account_home / ".local" / "bin" / "agy",
        "codex": Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
    }
    discovered = shutil.which("agy" if worker == "gemini" else worker)
    candidate = Path(discovered) if discovered else fixed[worker]
    return candidate if candidate.is_file() else None


def _probe_environment() -> dict[str, str]:
    account = pwd.getpwuid(os.getuid())
    return {
        "HOME": account.pw_dir,
        "USER": account.pw_name,
        "LOGNAME": account.pw_name,
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }


class WorkerAuthReadinessService:
    """Check local CLI authentication without sending a model prompt."""

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout_seconds: int = 10,
    ):
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def check(self, worker: str) -> WorkerAuthReadiness:
        if worker not in _PROBES:
            raise ValueError("Unknown authentication probe")
        label, arguments, login = _PROBES[worker]
        executable = _candidate_executable(worker)
        if executable is None:
            return WorkerAuthReadiness(
                worker,
                label,
                WorkerAuthState.UNAVAILABLE,
                "The local worker application was not found.",
                login,
            )
        try:
            completed = self._runner(
                [str(executable), *arguments],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
                env=_probe_environment(),
            )
        except (OSError, subprocess.SubprocessError):
            return WorkerAuthReadiness(
                worker,
                label,
                WorkerAuthState.UNAVAILABLE,
                "Authentication could not be checked safely.",
                login,
            )
        if completed.returncode == 0:
            return WorkerAuthReadiness(
                worker,
                label,
                WorkerAuthState.AUTHENTICATED,
                "Authenticated and ready for governed work.",
                None,
            )
        evidence = f"{completed.stdout or ''} {completed.stderr or ''}".lower()[:2000]
        login_required = any(
            token in evidence
            for token in ("login", "not authenticated", "unauthorized", "expired")
        )
        return WorkerAuthReadiness(
            worker,
            label,
            WorkerAuthState.LOGIN_REQUIRED if login_required else WorkerAuthState.UNAVAILABLE,
            "Login is required before this worker can be used."
            if login_required
            else "Authentication could not be confirmed.",
            login,
        )

    def check_all(self) -> tuple[WorkerAuthReadiness, ...]:
        return tuple(self.check(worker) for worker in ("kimi", "gemini", "codex"))
