"""Controller-owned worker usage evidence and fail-closed policy checks.

Provider quota readings are written by an approved local controller/operator.
Authoritative evidence lives outside the implementation worker's repository
workspace. AdvanCore validates and enforces the bounded evidence; it does not
scrape vendor accounts, store credentials, or infer balances from transcripts.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import pwd
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TextIO


USAGE_SCHEMA_VERSION = 2
SUPPORTED_PROVIDERS = ("kimi",)
APPROVED_USAGE_SOURCES = ("kimi-cli", "kimi-web", "owner-verified")
KIMI_WEEKLY_PERCENT_LIMIT = 20.0
KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS = 60 * 60
USAGE_SNAPSHOT_MAX_AGE_SECONDS = 15 * 60
MIN_NEW_PERIOD_RESET_ADVANCE = timedelta(days=1)
RESET_BOUNDARY_GUARD_SECONDS = 5
MAX_EVIDENCE_BYTES = 16 * 1024
USAGE_PROBE_SCHEMA_VERSION = 1
USAGE_PROBE_TIMEOUT_SECONDS = 10
MAX_USAGE_PROBE_OUTPUT_BYTES = 16 * 1024


class UsageBudgetError(ValueError):
    """Raised when local usage evidence is invalid or policy blocks a launch."""


class UsageState(str, Enum):
    AVAILABLE = "AVAILABLE"
    PAUSED = "PAUSED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class UsageSnapshot:
    schema_version: int
    provider: str
    period_id: str
    weekly_used_percent: float
    checked_at: datetime
    reset_at: datetime
    source: str


@dataclass(frozen=True)
class RuntimeLedger:
    schema_version: int
    provider: str
    period_id: str
    reset_at: datetime
    runtime_seconds: int
    carryover_seconds: int


@dataclass(frozen=True)
class UsageSummary:
    provider: str
    state: UsageState
    weekly_used_percent: float | None
    weekly_percent_limit: float
    runtime_seconds: int | None
    runtime_limit_seconds: int
    checked_at: datetime | None
    reset_at: datetime | None
    source: str | None
    message: str

    @property
    def allowed(self) -> bool:
        return self.state == UsageState.AVAILABLE


@dataclass(frozen=True)
class UsagePreflight:
    provider: str
    period_id: str
    allowed_timeout_seconds: int
    reserved_seconds: int
    reset_at: datetime
    launch_deadline: datetime
    summary: UsageSummary


@dataclass
class _ActiveReservation:
    preflight: UsagePreflight
    lock_handle: TextIO
    evidence_fingerprint: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise UsageBudgetError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UsageBudgetError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise UsageBudgetError(f"invalid {field}")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _strict_number(value: Any, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UsageBudgetError(f"invalid {field}")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise UsageBudgetError(f"invalid {field}")
    return number


def _strict_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UsageBudgetError(f"invalid {field}")
    if not minimum <= value <= maximum:
        raise UsageBudgetError(f"invalid {field}")
    return value


def _validate_period_id(value: Any) -> str:
    if not isinstance(value, str):
        raise UsageBudgetError("usage evidence period is invalid")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise UsageBudgetError("usage evidence period is invalid") from exc
    if str(parsed) != value:
        raise UsageBudgetError("usage evidence period is invalid")
    return value


def _validate_provider(provider: str) -> str:
    if provider not in SUPPORTED_PROVIDERS:
        raise UsageBudgetError("unsupported provider")
    return provider


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise UsageBudgetError("usage evidence is unavailable")
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise UsageBudgetError("usage evidence is invalid")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UsageBudgetError("usage evidence is invalid") from exc
    if not isinstance(payload, dict):
        raise UsageBudgetError("usage evidence is invalid")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    handle = None
    temporary_name = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".usage-", delete=False
        )
        temporary_name = handle.name
        os.chmod(temporary_name, 0o600)
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        if handle is not None and not handle.closed:
            handle.close()
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise UsageBudgetError("cannot write usage evidence") from exc


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _default_usage_dir(_repo_root: Path) -> Path:
    """Return one OS-account-wide usage store shared by every checkout."""
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    if sys.platform == "darwin":
        state_root = account_home / "Library" / "Application Support" / "AdvanCore"
    else:
        state_root = account_home / ".local" / "state" / "advancore"
    return state_root / "agent_runner" / "usage"


class WorkerUsageService:
    """Read, write and enforce controller-owned worker usage evidence."""

    def __init__(
        self,
        repo_root: Path,
        now_provider=_utc_now,
        usage_dir: Path | None = None,
    ):
        self.repo_root = repo_root.resolve()
        proposed = usage_dir or _default_usage_dir(self.repo_root)
        self.usage_dir = proposed.resolve()
        if _is_within(self.usage_dir, self.repo_root):
            raise UsageBudgetError("usage evidence must be outside the worker workspace")
        self._now_provider = now_provider
        self._active_reservation: _ActiveReservation | None = None

    def snapshot_path(self, provider: str) -> Path:
        return self.usage_dir / f"{_validate_provider(provider)}-reported.json"

    def runtime_path(self, provider: str) -> Path:
        return self.usage_dir / f"{_validate_provider(provider)}-runtime.json"

    def quarantine_path(self, provider: str) -> Path:
        return self.usage_dir / f"{_validate_provider(provider)}-quarantine.json"

    def lock_path(self, provider: str) -> Path:
        return self.usage_dir / f"{_validate_provider(provider)}.lock"

    def controller_probe_path(self, provider: str) -> Path:
        """Return the fixed controller-owned executable used for usage refresh."""
        return self.protected_state_root / "probes" / f"{_validate_provider(provider)}-usage"

    @property
    def protected_state_root(self) -> Path:
        """Directory that an implementation worker must be denied write access to."""
        return self.usage_dir.parent

    def _ensure_usage_dir(self) -> None:
        try:
            self.usage_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
            if self.usage_dir.is_symlink() or not self.usage_dir.is_dir():
                raise UsageBudgetError("usage evidence location is invalid")
            if (
                self.protected_state_root.is_symlink()
                or not self.protected_state_root.is_dir()
            ):
                raise UsageBudgetError("usage evidence location is invalid")
            os.chmod(self.protected_state_root, 0o700)
            os.chmod(self.usage_dir, 0o700)
        except OSError as exc:
            raise UsageBudgetError("usage evidence location is unavailable") from exc

    def _validated_controller_probe(self, provider: str) -> Path:
        """Validate the fixed probe without accepting worker-controlled commands."""
        path = self.controller_probe_path(provider)
        try:
            root = self.protected_state_root
            relative = path.relative_to(root)
            current = root
            for component in relative.parts[:-1]:
                current = current / component
                parent_metadata = current.lstat()
                if (
                    stat.S_ISLNK(parent_metadata.st_mode)
                    or not stat.S_ISDIR(parent_metadata.st_mode)
                    or parent_metadata.st_uid != os.getuid()
                    or parent_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                ):
                    raise UsageBudgetError(
                        "automatic provider usage refresh is unsafe"
                    )
            metadata = path.lstat()
        except OSError as exc:
            raise UsageBudgetError(
                "automatic provider usage refresh is unavailable"
            ) from exc
        except ValueError as exc:
            raise UsageBudgetError(
                "automatic provider usage refresh is unsafe"
            ) from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or not metadata.st_mode & stat.S_IXUSR
        ):
            raise UsageBudgetError("automatic provider usage refresh is unsafe")
        try:
            if path.resolve(strict=True) != path:
                raise UsageBudgetError(
                    "automatic provider usage refresh is unsafe"
                )
        except OSError as exc:
            raise UsageBudgetError(
                "automatic provider usage refresh is unavailable"
            ) from exc
        return path

    @staticmethod
    def _stop_probe_process(process: subprocess.Popen[bytes]) -> None:
        """Terminate and reap a failed probe and any descendants."""
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

    def _run_controller_probe(
        self, probe: Path, environment: dict[str, str]
    ) -> tuple[int, bytes, bytes]:
        """Run a probe while bounding both output streams during collection."""
        process: subprocess.Popen[bytes] | None = None
        selector = selectors.DefaultSelector()
        stdout = bytearray()
        stderr = bytearray()
        completed = False
        try:
            process = subprocess.Popen(
                [str(probe)],
                cwd=self.protected_state_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            if process.stdout is None or process.stderr is None:
                raise UsageBudgetError("automatic provider usage refresh failed")
            selector.register(process.stdout, selectors.EVENT_READ, stdout)
            selector.register(process.stderr, selectors.EVENT_READ, stderr)
            deadline = time.monotonic() + USAGE_PROBE_TIMEOUT_SECONDS
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise UsageBudgetError("automatic provider usage refresh failed")
                events = selector.select(remaining)
                if not events:
                    raise UsageBudgetError("automatic provider usage refresh failed")
                for key, _ in events:
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output: bytearray = key.data
                    output.extend(chunk)
                    if len(output) > MAX_USAGE_PROBE_OUTPUT_BYTES:
                        raise UsageBudgetError(
                            "automatic provider usage refresh failed"
                        )
            remaining = max(0.01, deadline - time.monotonic())
            returncode = process.wait(timeout=remaining)
            completed = True
            return returncode, bytes(stdout), bytes(stderr)
        except (OSError, subprocess.SubprocessError) as exc:
            raise UsageBudgetError(
                "automatic provider usage refresh failed"
            ) from exc
        finally:
            selector.close()
            if process is not None and not completed:
                self._stop_probe_process(process)

    def refresh_from_controller_probe(self, provider: str = "kimi") -> UsageSnapshot:
        """Refresh bounded evidence through a fixed, trusted local probe.

        The probe owns provider authentication and may emit only the documented
        bounded JSON fields. AdvanCore neither receives nor stores credentials.
        """
        provider = _validate_provider(provider)
        self._ensure_usage_dir()
        probe = self._validated_controller_probe(provider)
        account_home = pwd.getpwuid(os.getuid()).pw_dir
        environment = {
            "HOME": account_home,
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
        }
        returncode, stdout, stderr = self._run_controller_probe(probe, environment)
        if returncode != 0 or stderr:
            raise UsageBudgetError("automatic provider usage refresh failed")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UsageBudgetError(
                "automatic provider usage refresh is invalid"
            ) from exc
        expected = {
            "schema_version",
            "provider",
            "weekly_used_percent",
            "checked_at",
            "reset_at",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise UsageBudgetError("automatic provider usage refresh is invalid")
        if payload["schema_version"] != USAGE_PROBE_SCHEMA_VERSION:
            raise UsageBudgetError("automatic provider usage refresh is invalid")
        if payload["provider"] != provider:
            raise UsageBudgetError("automatic provider usage refresh is invalid")
        return self.record_snapshot(
            provider,
            payload["weekly_used_percent"],
            _timestamp(payload["checked_at"], "checked_at"),
            _timestamp(payload["reset_at"], "reset_at"),
            "kimi-cli",
        )

    def auto_refresh_if_needed(self, provider: str = "kimi") -> UsageSummary:
        """Refresh stale or unavailable evidence, then return current status."""
        provider = _validate_provider(provider)
        summary = self.get_summary(provider)
        if summary.state != UsageState.UNAVAILABLE:
            return summary
        if summary.message == "usage accounting is busy":
            raise UsageBudgetError("automatic provider usage refresh is busy")
        self.refresh_from_controller_probe(provider)
        return self.get_summary(provider)

    def _acquire_lock(self, provider: str) -> TextIO:
        self._ensure_usage_dir()
        path = self.lock_path(provider)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        handle: TextIO | None = None
        try:
            descriptor = os.open(path, flags, 0o600)
            handle = os.fdopen(descriptor, "a+", encoding="utf-8")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.chmod(path, 0o600)
            return handle
        except BlockingIOError as exc:
            if handle is not None:
                handle.close()
            raise UsageBudgetError("usage accounting is busy") from exc
        except OSError as exc:
            if handle is not None:
                handle.close()
            raise UsageBudgetError("usage accounting lock is unavailable") from exc

    @staticmethod
    def _release_lock(handle: TextIO) -> None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def _load_snapshot(
        self, provider: str, now: datetime, *, require_fresh: bool = True
    ) -> UsageSnapshot:
        provider = _validate_provider(provider)
        payload = _read_json(self.snapshot_path(provider))
        expected = {
            "schema_version", "provider", "period_id", "weekly_used_percent",
            "checked_at", "reset_at", "source",
        }
        if set(payload) != expected:
            raise UsageBudgetError("usage evidence is invalid")
        if payload["schema_version"] != USAGE_SCHEMA_VERSION:
            raise UsageBudgetError("usage evidence schema is unsupported")
        if payload["provider"] != provider:
            raise UsageBudgetError("usage evidence provider mismatch")
        source = payload["source"]
        if source not in APPROVED_USAGE_SOURCES:
            raise UsageBudgetError("usage evidence source is invalid")
        checked_at = _timestamp(payload["checked_at"], "checked_at")
        reset_at = _timestamp(payload["reset_at"], "reset_at")
        if checked_at > now + timedelta(seconds=30):
            raise UsageBudgetError("usage evidence is future-dated")
        if require_fresh and now - checked_at > timedelta(
            seconds=USAGE_SNAPSHOT_MAX_AGE_SECONDS
        ):
            raise UsageBudgetError("usage evidence is stale")
        if require_fresh and reset_at <= now:
            raise UsageBudgetError("usage evidence reset has passed")
        if reset_at <= checked_at or reset_at - checked_at > timedelta(days=8):
            raise UsageBudgetError("usage reset window is invalid")
        return UsageSnapshot(
            schema_version=USAGE_SCHEMA_VERSION,
            provider=provider,
            period_id=_validate_period_id(payload["period_id"]),
            weekly_used_percent=_strict_number(
                payload["weekly_used_percent"], "weekly_used_percent", 0, 100
            ),
            checked_at=checked_at,
            reset_at=reset_at,
            source=source,
        )

    def _load_runtime(self, provider: str, period_id: str) -> RuntimeLedger:
        provider = _validate_provider(provider)
        payload = _read_json(self.runtime_path(provider))
        expected = {
            "schema_version", "provider", "period_id", "reset_at",
            "runtime_seconds", "carryover_seconds",
        }
        if set(payload) != expected:
            raise UsageBudgetError("runtime evidence is invalid")
        if payload["schema_version"] != USAGE_SCHEMA_VERSION:
            raise UsageBudgetError("runtime evidence schema is unsupported")
        if payload["provider"] != provider:
            raise UsageBudgetError("runtime evidence provider mismatch")
        ledger_period = _validate_period_id(payload["period_id"])
        if ledger_period != period_id:
            raise UsageBudgetError("runtime evidence period mismatch")
        return RuntimeLedger(
            schema_version=USAGE_SCHEMA_VERSION,
            provider=provider,
            period_id=ledger_period,
            reset_at=_timestamp(payload["reset_at"], "reset_at"),
            runtime_seconds=_strict_int(
                payload["runtime_seconds"], "runtime_seconds", 0, 8 * 24 * 60 * 60
            ),
            carryover_seconds=_strict_int(
                payload["carryover_seconds"],
                "carryover_seconds",
                0,
                KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS,
            ),
        )

    def _write_runtime(
        self,
        provider: str,
        period_id: str,
        reset_at: datetime,
        runtime_seconds: int,
        carryover_seconds: int,
    ) -> None:
        _atomic_write_json(
            self.runtime_path(provider),
            {
                "schema_version": USAGE_SCHEMA_VERSION,
                "provider": provider,
                "period_id": period_id,
                "reset_at": _canonical_timestamp(reset_at),
                "runtime_seconds": runtime_seconds,
                "carryover_seconds": carryover_seconds,
            },
        )

    def _write_quarantine(self, provider: str, now: datetime) -> None:
        _atomic_write_json(
            self.quarantine_path(provider),
            {
                "schema_version": USAGE_SCHEMA_VERSION,
                "provider": provider,
                "detected_at": _canonical_timestamp(now),
                "reason": "usage accounting integrity failure",
            },
        )

    def _evidence_fingerprint(self, provider: str) -> str:
        digest = hashlib.sha256()
        for path in (self.snapshot_path(provider), self.runtime_path(provider)):
            if path.is_symlink() or not path.is_file():
                raise UsageBudgetError("usage evidence is unavailable")
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise UsageBudgetError("usage evidence is invalid") from exc
            if len(content) > MAX_EVIDENCE_BYTES:
                raise UsageBudgetError("usage evidence is invalid")
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content)
        return digest.hexdigest()

    def _summary_unlocked(self, provider: str, now: datetime) -> UsageSummary:
        quarantine = self.quarantine_path(provider)
        if quarantine.exists() or quarantine.is_symlink():
            raise UsageBudgetError("usage evidence is quarantined")
        snapshot = self._load_snapshot(provider, now, require_fresh=False)
        ledger = self._load_runtime(provider, snapshot.period_id)
        if ledger.reset_at != snapshot.reset_at:
            raise UsageBudgetError("runtime evidence reset mismatch")
        unavailable_reasons = []
        if now - snapshot.checked_at > timedelta(
            seconds=USAGE_SNAPSHOT_MAX_AGE_SECONDS
        ):
            unavailable_reasons.append("usage evidence is stale")
        if snapshot.reset_at <= now:
            unavailable_reasons.append("usage evidence reset has passed")
        paused_reasons = []
        if snapshot.weekly_used_percent >= KIMI_WEEKLY_PERCENT_LIMIT:
            paused_reasons.append("weekly usage limit reached")
        if ledger.runtime_seconds >= KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS:
            paused_reasons.append("weekly runtime limit reached")
        state = (
            UsageState.UNAVAILABLE
            if unavailable_reasons
            else UsageState.PAUSED if paused_reasons else UsageState.AVAILABLE
        )
        return UsageSummary(
            provider=provider,
            state=state,
            weekly_used_percent=snapshot.weekly_used_percent,
            weekly_percent_limit=KIMI_WEEKLY_PERCENT_LIMIT,
            runtime_seconds=ledger.runtime_seconds,
            runtime_limit_seconds=KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS,
            checked_at=snapshot.checked_at,
            reset_at=snapshot.reset_at,
            source=snapshot.source,
            message=(
                ", ".join(unavailable_reasons)
                if unavailable_reasons
                else ", ".join(paused_reasons)
                if paused_reasons
                else "usage budget available"
            ),
        )

    def get_summary(self, provider: str = "kimi") -> UsageSummary:
        provider = _validate_provider(provider)
        now = self._now_provider().astimezone(timezone.utc)
        handle = None
        try:
            handle = self._acquire_lock(provider)
            return self._summary_unlocked(provider, now)
        except UsageBudgetError as exc:
            return UsageSummary(
                provider=provider,
                state=UsageState.UNAVAILABLE,
                weekly_used_percent=None,
                weekly_percent_limit=KIMI_WEEKLY_PERCENT_LIMIT,
                runtime_seconds=None,
                runtime_limit_seconds=KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS,
                checked_at=None,
                reset_at=None,
                source=None,
                message=str(exc),
            )
        finally:
            if handle is not None:
                self._release_lock(handle)

    def preflight(self, provider: str, requested_timeout_seconds: int) -> UsagePreflight:
        provider = _validate_provider(provider)
        if self._active_reservation is not None:
            raise UsageBudgetError("usage accounting reservation is already active")
        if isinstance(requested_timeout_seconds, bool) or not isinstance(
            requested_timeout_seconds, int
        ) or requested_timeout_seconds <= 0:
            raise UsageBudgetError("provider quota/capacity check has invalid timeout")
        handle = self._acquire_lock(provider)
        try:
            now = self._now_provider().astimezone(timezone.utc)
            try:
                summary = self._summary_unlocked(provider, now)
            except UsageBudgetError as exc:
                raise UsageBudgetError(
                    f"provider quota/capacity paused: {exc}"
                ) from exc
            if not summary.allowed:
                raise UsageBudgetError(
                    f"provider quota/capacity paused: {summary.message}"
                )
            snapshot = self._load_snapshot(provider, now)
            ledger = self._load_runtime(provider, snapshot.period_id)
            remaining = summary.runtime_limit_seconds - ledger.runtime_seconds
            if remaining <= 0:
                raise UsageBudgetError(
                    "provider quota/capacity paused: weekly runtime limit reached"
                )
            reset_remaining = (
                math.floor((snapshot.reset_at - now).total_seconds())
                - RESET_BOUNDARY_GUARD_SECONDS
            )
            if reset_remaining <= 0:
                raise UsageBudgetError(
                    "provider quota/capacity paused: provider reset is too close"
                )
            reserved = min(requested_timeout_seconds, remaining, reset_remaining)
            self._write_runtime(
                provider,
                snapshot.period_id,
                snapshot.reset_at,
                ledger.runtime_seconds + reserved,
                min(
                    KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS,
                    ledger.carryover_seconds + reserved,
                ),
            )
            preflight = UsagePreflight(
                provider=provider,
                period_id=snapshot.period_id,
                allowed_timeout_seconds=reserved,
                reserved_seconds=reserved,
                reset_at=snapshot.reset_at,
                launch_deadline=snapshot.reset_at - timedelta(
                    seconds=RESET_BOUNDARY_GUARD_SECONDS
                ),
                summary=summary,
            )
            self._active_reservation = _ActiveReservation(
                preflight=preflight,
                lock_handle=handle,
                evidence_fingerprint=self._evidence_fingerprint(provider),
            )
            return preflight
        except Exception:
            self._release_lock(handle)
            raise

    def abandon_reservation(self, preflight: UsagePreflight) -> None:
        """Release the lock while retaining the full fail-closed reservation."""
        active = self._active_reservation
        if active is None or active.preflight != preflight:
            raise UsageBudgetError("runtime accounting reservation mismatch")
        self._active_reservation = None
        self._release_lock(active.lock_handle)

    def record_snapshot(
        self,
        provider: str,
        weekly_used_percent: float,
        checked_at: datetime,
        reset_at: datetime,
        source: str,
    ) -> UsageSnapshot:
        provider = _validate_provider(provider)
        now = self._now_provider().astimezone(timezone.utc)
        if source not in APPROVED_USAGE_SOURCES:
            raise UsageBudgetError("usage evidence source is invalid")
        if checked_at.tzinfo is None or reset_at.tzinfo is None:
            raise UsageBudgetError("usage evidence timestamps must include a timezone")
        used = _strict_number(weekly_used_percent, "weekly_used_percent", 0, 100)
        checked = checked_at.astimezone(timezone.utc)
        reset = reset_at.astimezone(timezone.utc)
        if checked > now + timedelta(seconds=30):
            raise UsageBudgetError("usage evidence is future-dated")
        if now - checked > timedelta(seconds=USAGE_SNAPSHOT_MAX_AGE_SECONDS):
            raise UsageBudgetError("usage evidence is stale")
        if reset <= now or reset <= checked or reset - checked > timedelta(days=8):
            raise UsageBudgetError("usage reset window is invalid")

        handle = self._acquire_lock(provider)
        try:
            snapshot_path = self.snapshot_path(provider)
            runtime_path = self.runtime_path(provider)
            if snapshot_path.exists() != runtime_path.exists():
                raise UsageBudgetError("usage evidence is incomplete")
            if snapshot_path.exists():
                current = self._load_snapshot(provider, now, require_fresh=False)
                ledger = self._load_runtime(provider, current.period_id)
                if ledger.reset_at != current.reset_at:
                    raise UsageBudgetError("runtime evidence reset mismatch")
                is_new_period = (
                    checked >= current.reset_at
                    and reset >= current.reset_at + MIN_NEW_PERIOD_RESET_ADVANCE
                )
                if not is_new_period and used < current.weekly_used_percent:
                    raise UsageBudgetError(
                        "weekly usage cannot decrease within the active provider period"
                    )
                period_id = str(uuid.uuid4()) if is_new_period else current.period_id
                runtime_seconds = (
                    ledger.carryover_seconds if is_new_period else ledger.runtime_seconds
                )
                carryover_seconds = 0 if is_new_period else ledger.carryover_seconds
            else:
                period_id = str(uuid.uuid4())
                runtime_seconds = 0
                carryover_seconds = 0

            snapshot_payload = {
                "schema_version": USAGE_SCHEMA_VERSION,
                "provider": provider,
                "period_id": period_id,
                "weekly_used_percent": used,
                "checked_at": _canonical_timestamp(checked),
                "reset_at": _canonical_timestamp(reset),
                "source": source,
            }
            self._write_runtime(
                provider, period_id, reset, runtime_seconds, carryover_seconds
            )
            _atomic_write_json(snapshot_path, snapshot_payload)
            loaded = self._load_snapshot(provider, now)
            self._load_runtime(provider, loaded.period_id)
            quarantine = self.quarantine_path(provider)
            if quarantine.exists():
                if quarantine.is_symlink():
                    raise UsageBudgetError("usage quarantine is invalid")
                quarantine.unlink()
            return loaded
        finally:
            self._release_lock(handle)

    def record_runtime(
        self, provider: str, elapsed_seconds: float, preflight: UsagePreflight
    ) -> RuntimeLedger:
        provider = _validate_provider(provider)
        active = self._active_reservation
        if active is None or active.preflight != preflight or preflight.provider != provider:
            raise UsageBudgetError("runtime accounting reservation mismatch")
        now = self._now_provider().astimezone(timezone.utc)
        try:
            if isinstance(elapsed_seconds, bool) or not isinstance(
                elapsed_seconds, (int, float)
            ):
                raise UsageBudgetError("runtime accounting is invalid")
            if not math.isfinite(float(elapsed_seconds)) or elapsed_seconds < 0:
                raise UsageBudgetError("runtime accounting is invalid")
            if self._evidence_fingerprint(provider) != active.evidence_fingerprint:
                raise UsageBudgetError("usage evidence changed during worker execution")
            # Freshness is a launch gate. A correctly reserved long run may
            # legitimately outlive the 15-minute snapshot freshness window.
            snapshot = self._load_snapshot(provider, now, require_fresh=False)
            if snapshot.period_id != preflight.period_id:
                raise UsageBudgetError("runtime accounting period changed")
            ledger = self._load_runtime(provider, snapshot.period_id)
            if ledger.reset_at != snapshot.reset_at:
                raise UsageBudgetError("runtime evidence reset mismatch")
            expected_reserved_total = (
                preflight.summary.runtime_seconds + preflight.reserved_seconds
                if preflight.summary.runtime_seconds is not None else None
            )
            if ledger.runtime_seconds != expected_reserved_total:
                raise UsageBudgetError("runtime accounting reservation changed")
            charged = min(
                preflight.reserved_seconds, max(1, math.ceil(elapsed_seconds))
            )
            updated = ledger.runtime_seconds - preflight.reserved_seconds + charged
            if ledger.carryover_seconds < preflight.reserved_seconds:
                raise UsageBudgetError("runtime carryover reservation changed")
            carryover = ledger.carryover_seconds - preflight.reserved_seconds
            if now >= snapshot.reset_at:
                # A suspended or delayed process may settle after the guarded
                # deadline. Conservatively carry its entire charge into the
                # next verified provider period so rollover cannot erase it.
                carryover = min(
                    KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS,
                    carryover + charged,
                )
            self._write_runtime(
                provider,
                snapshot.period_id,
                snapshot.reset_at,
                updated,
                carryover,
            )
            return RuntimeLedger(
                schema_version=USAGE_SCHEMA_VERSION,
                provider=provider,
                period_id=snapshot.period_id,
                reset_at=snapshot.reset_at,
                runtime_seconds=updated,
                carryover_seconds=carryover,
            )
        except UsageBudgetError:
            self._write_quarantine(provider, now)
            raise
        finally:
            self._active_reservation = None
            self._release_lock(active.lock_handle)


def _summary_payload(summary: UsageSummary) -> dict[str, Any]:
    payload = asdict(summary)
    payload["state"] = summary.state.value
    for field in ("checked_at", "reset_at"):
        value = payload[field]
        payload[field] = _canonical_timestamp(value) if value else None
    payload["allowed"] = summary.allowed
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record or show bounded worker usage status.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default="kimi")
    record.add_argument("--weekly-used", type=float, required=True)
    record.add_argument("--checked-at", required=True)
    record.add_argument("--reset-at", required=True)
    record.add_argument("--source", choices=APPROVED_USAGE_SOURCES, required=True)
    show = subparsers.add_parser("show")
    show.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default="kimi")
    args = parser.parse_args(argv)
    service = WorkerUsageService(args.repo_root)
    try:
        if args.command == "record":
            service.record_snapshot(
                args.provider,
                args.weekly_used,
                _timestamp(args.checked_at, "checked_at"),
                _timestamp(args.reset_at, "reset_at"),
                args.source,
            )
        print(json.dumps(_summary_payload(service.get_summary(args.provider)), sort_keys=True))
        return 0
    except UsageBudgetError as exc:
        print(json.dumps({"allowed": False, "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI boundary
    raise SystemExit(main())
