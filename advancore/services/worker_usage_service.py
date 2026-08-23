"""Local, provider-neutral worker usage evidence and policy checks.

Provider quota readings are written by an approved local controller/operator.
AdvanCore validates and enforces the bounded evidence; it does not scrape vendor
accounts, store credentials, or infer provider balances from model transcripts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


USAGE_SCHEMA_VERSION = 1
SUPPORTED_PROVIDERS = ("kimi",)
APPROVED_USAGE_SOURCES = ("kimi-cli", "kimi-web", "owner-verified")
KIMI_WEEKLY_PERCENT_LIMIT = 20.0
KIMI_WEEKLY_RUNTIME_LIMIT_SECONDS = 60 * 60
USAGE_SNAPSHOT_MAX_AGE_SECONDS = 15 * 60
MAX_EVIDENCE_BYTES = 16 * 1024


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
    weekly_used_percent: float
    checked_at: datetime
    reset_at: datetime
    source: str


@dataclass(frozen=True)
class RuntimeLedger:
    schema_version: int
    provider: str
    reset_at: datetime
    runtime_seconds: int


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
    allowed_timeout_seconds: int
    reset_at: datetime
    summary: UsageSummary


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
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    temporary_name = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".usage-", delete=False
        )
        temporary_name = handle.name
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temporary_name, path)
    except OSError as exc:
        if handle is not None and not handle.closed:
            handle.close()
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise UsageBudgetError("cannot write usage evidence") from exc


class WorkerUsageService:
    """Read, write and enforce bounded local worker usage evidence."""

    def __init__(self, repo_root: Path, now_provider=_utc_now):
        self.repo_root = repo_root.resolve()
        self.usage_dir = self.repo_root / ".agent_runner" / "usage"
        self._now_provider = now_provider

    def snapshot_path(self, provider: str) -> Path:
        return self.usage_dir / f"{_validate_provider(provider)}-reported.json"

    def runtime_path(self, provider: str) -> Path:
        return self.usage_dir / f"{_validate_provider(provider)}-runtime.json"

    def _load_snapshot(
        self, provider: str, now: datetime, *, require_fresh: bool = True
    ) -> UsageSnapshot:
        provider = _validate_provider(provider)
        payload = _read_json(self.snapshot_path(provider))
        expected = {
            "schema_version", "provider", "weekly_used_percent",
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
            weekly_used_percent=_strict_number(
                payload["weekly_used_percent"], "weekly_used_percent", 0, 100
            ),
            checked_at=checked_at,
            reset_at=reset_at,
            source=source,
        )

    def _load_runtime(self, provider: str, reset_at: datetime) -> RuntimeLedger:
        provider = _validate_provider(provider)
        payload = _read_json(self.runtime_path(provider))
        expected = {"schema_version", "provider", "reset_at", "runtime_seconds"}
        if set(payload) != expected:
            raise UsageBudgetError("runtime evidence is invalid")
        if payload["schema_version"] != USAGE_SCHEMA_VERSION:
            raise UsageBudgetError("runtime evidence schema is unsupported")
        if payload["provider"] != provider:
            raise UsageBudgetError("runtime evidence provider mismatch")
        ledger_reset = _timestamp(payload["reset_at"], "reset_at")
        if ledger_reset != reset_at:
            raise UsageBudgetError("runtime evidence period mismatch")
        return RuntimeLedger(
            schema_version=USAGE_SCHEMA_VERSION,
            provider=provider,
            reset_at=ledger_reset,
            runtime_seconds=_strict_int(
                payload["runtime_seconds"],
                "runtime_seconds",
                0,
                8 * 24 * 60 * 60,
            ),
        )

    def get_summary(self, provider: str = "kimi") -> UsageSummary:
        provider = _validate_provider(provider)
        now = self._now_provider().astimezone(timezone.utc)
        try:
            snapshot = self._load_snapshot(provider, now, require_fresh=False)
            ledger = self._load_runtime(provider, snapshot.reset_at)
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

    def preflight(self, provider: str, requested_timeout_seconds: int) -> UsagePreflight:
        if isinstance(requested_timeout_seconds, bool) or not isinstance(
            requested_timeout_seconds, int
        ) or requested_timeout_seconds <= 0:
            raise UsageBudgetError("provider quota/capacity check has invalid timeout")
        summary = self.get_summary(provider)
        if not summary.allowed:
            raise UsageBudgetError(
                f"provider quota/capacity paused: {summary.message}"
            )
        assert summary.runtime_seconds is not None
        assert summary.reset_at is not None
        remaining = summary.runtime_limit_seconds - summary.runtime_seconds
        if remaining <= 0:
            raise UsageBudgetError("provider quota/capacity paused: weekly runtime limit reached")
        return UsagePreflight(
            provider=provider,
            allowed_timeout_seconds=min(requested_timeout_seconds, remaining),
            reset_at=summary.reset_at,
            summary=summary,
        )

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
        snapshot_payload = {
            "schema_version": USAGE_SCHEMA_VERSION,
            "provider": provider,
            "weekly_used_percent": _strict_number(
                weekly_used_percent, "weekly_used_percent", 0, 100
            ),
            "checked_at": _canonical_timestamp(checked_at),
            "reset_at": _canonical_timestamp(reset_at),
            "source": source,
        }
        # Validate the proposed evidence through the same strict reader by checking
        # its timestamps before any write occurs.
        checked = checked_at.astimezone(timezone.utc)
        reset = reset_at.astimezone(timezone.utc)
        if checked > now + timedelta(seconds=30):
            raise UsageBudgetError("usage evidence is future-dated")
        if now - checked > timedelta(seconds=USAGE_SNAPSHOT_MAX_AGE_SECONDS):
            raise UsageBudgetError("usage evidence is stale")
        if reset <= now or reset <= checked or reset - checked > timedelta(days=8):
            raise UsageBudgetError("usage reset window is invalid")

        runtime_seconds = 0
        runtime_path = self.runtime_path(provider)
        if runtime_path.exists():
            current_payload = _read_json(runtime_path)
            expected_runtime_fields = {
                "schema_version", "provider", "reset_at", "runtime_seconds"
            }
            if set(current_payload) != expected_runtime_fields:
                raise UsageBudgetError("runtime evidence is invalid")
            if current_payload["schema_version"] != USAGE_SCHEMA_VERSION:
                raise UsageBudgetError("runtime evidence schema is unsupported")
            if current_payload["provider"] != provider:
                raise UsageBudgetError("runtime evidence provider mismatch")
            if _timestamp(current_payload.get("reset_at"), "reset_at") == reset:
                runtime_seconds = _strict_int(
                    current_payload.get("runtime_seconds"),
                    "runtime_seconds",
                    0,
                    8 * 24 * 60 * 60,
                )
        runtime_payload = {
            "schema_version": USAGE_SCHEMA_VERSION,
            "provider": provider,
            "reset_at": _canonical_timestamp(reset),
            "runtime_seconds": runtime_seconds,
        }
        _atomic_write_json(runtime_path, runtime_payload)
        _atomic_write_json(self.snapshot_path(provider), snapshot_payload)
        return self._load_snapshot(provider, now)

    def record_runtime(
        self, provider: str, elapsed_seconds: float, expected_reset_at: datetime
    ) -> RuntimeLedger:
        provider = _validate_provider(provider)
        if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)):
            raise UsageBudgetError("runtime accounting is invalid")
        if not math.isfinite(float(elapsed_seconds)) or elapsed_seconds < 0:
            raise UsageBudgetError("runtime accounting is invalid")
        if expected_reset_at.tzinfo is None:
            raise UsageBudgetError("runtime accounting period is invalid")
        now = self._now_provider().astimezone(timezone.utc)
        snapshot = self._load_snapshot(provider, now)
        expected_reset = expected_reset_at.astimezone(timezone.utc)
        if snapshot.reset_at != expected_reset:
            raise UsageBudgetError("runtime accounting period changed")
        ledger = self._load_runtime(provider, snapshot.reset_at)
        updated = ledger.runtime_seconds + max(1, math.ceil(elapsed_seconds))
        payload = {
            "schema_version": USAGE_SCHEMA_VERSION,
            "provider": provider,
            "reset_at": _canonical_timestamp(snapshot.reset_at),
            "runtime_seconds": updated,
        }
        _atomic_write_json(self.runtime_path(provider), payload)
        return RuntimeLedger(
            schema_version=USAGE_SCHEMA_VERSION,
            provider=provider,
            reset_at=snapshot.reset_at,
            runtime_seconds=updated,
        )


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
