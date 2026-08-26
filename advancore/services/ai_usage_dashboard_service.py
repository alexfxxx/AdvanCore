"""Truthful, provider-neutral AI usage summaries for the local Dashboard."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import math
import os
from pathlib import Path
import pwd
import stat
import sys
import tempfile
from typing import Any, Callable

from advancore.agent_runner.worker_registry import get_worker_profile
from advancore.services.worker_usage_service import UsageState, WorkerUsageService


OBSERVATION_SCHEMA_VERSION = 1
OBSERVATION_MAX_AGE = timedelta(hours=24)
MAX_OBSERVATION_BYTES = 8 * 1024
OBSERVATION_PROVIDERS = ("codex", "gemini")
OBSERVATION_SOURCES = (
    "antigravity-cli-json",
    "codex-approved-export",
    "owner-verified",
)


class AiUsageEvidenceError(ValueError):
    """Raised when a provider observation is unsafe or invalid."""


class BalanceState(str, Enum):
    CURRENT = "CURRENT"
    OBSERVED_ONLY = "OBSERVED_ONLY"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ProviderUsageObservation:
    schema_version: int
    provider: str
    authentication_verified: bool
    observed_at: datetime
    source: str
    last_run_tokens: int | None
    weekly_used_percent: float | None
    reset_at: datetime | None


@dataclass(frozen=True)
class AiUsageCard:
    provider: str
    label: str
    role: str
    routing_status: str
    balance_state: BalanceState
    weekly_used_percent: float | None
    remaining_percent: float | None
    automation_limit_percent: float | None
    automation_remaining_percent: float | None
    runtime_seconds: int | None
    runtime_limit_seconds: int | None
    last_run_tokens: int | None
    checked_at: datetime | None
    reset_at: datetime | None
    source: str | None
    authentication_verified: bool
    message: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_observation_dir() -> Path:
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    if sys.platform == "darwin":
        root = account_home / "Library" / "Application Support" / "AdvanCore"
    else:
        root = account_home / ".local" / "state" / "advancore"
    return root / "agent_runner" / "provider-usage"


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            details = os.lstat(current)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(details.st_mode):
            return True
    return False


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise AiUsageEvidenceError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AiUsageEvidenceError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise AiUsageEvidenceError(f"invalid {field}")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _provider(value: Any) -> str:
    if not isinstance(value, str) or value not in OBSERVATION_PROVIDERS:
        raise AiUsageEvidenceError("unsupported provider")
    return value


def _tokens(value: Any) -> int | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 1_000_000_000
    ):
        raise AiUsageEvidenceError("invalid token observation")
    return value


def _percentage(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AiUsageEvidenceError("invalid weekly percentage")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 100:
        raise AiUsageEvidenceError("invalid weekly percentage")
    return result


class ProviderUsageObservationStore:
    """Store bounded, non-secret controller observations outside workspaces."""

    def __init__(
        self,
        repo_root: Path,
        observation_dir: Path | None = None,
        now_provider: Callable[[], datetime] = _utc_now,
    ):
        self.repo_root = Path(repo_root).resolve()
        proposed = Path(observation_dir or _default_observation_dir()).expanduser()
        if not proposed.is_absolute():
            proposed = Path.cwd() / proposed
        try:
            if _has_symlink_component(proposed):
                raise AiUsageEvidenceError("provider evidence location is unsafe")
        except OSError as exc:
            raise AiUsageEvidenceError("provider evidence location is unavailable") from exc
        self._observation_path = proposed
        self.observation_dir = proposed.resolve()
        if (
            self.observation_dir == self.repo_root
            or self.repo_root in self.observation_dir.parents
        ):
            raise AiUsageEvidenceError("provider evidence must be outside the worker workspace")
        self._now_provider = now_provider

    def path(self, provider: str) -> Path:
        return self.observation_dir / f"{_provider(provider)}-observation.json"

    def _ensure_directory(self) -> None:
        try:
            self.observation_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
            if _has_symlink_component(self._observation_path) or not self.observation_dir.is_dir():
                raise AiUsageEvidenceError("provider evidence location is unsafe")
            details = self.observation_dir.stat()
            if details.st_uid != os.getuid():
                raise AiUsageEvidenceError("provider evidence location is unsafe")
            os.chmod(self.observation_dir, 0o700)
        except OSError as exc:
            raise AiUsageEvidenceError("provider evidence location is unavailable") from exc

    def record(
        self,
        provider: str,
        *,
        observed_at: datetime,
        source: str,
        last_run_tokens: int | None = None,
        weekly_used_percent: float | None = None,
        reset_at: datetime | None = None,
    ) -> ProviderUsageObservation:
        provider = _provider(provider)
        now = self._now_provider().astimezone(timezone.utc)
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            raise AiUsageEvidenceError("invalid observed_at")
        observed_at = observed_at.astimezone(timezone.utc)
        if observed_at > now + timedelta(minutes=5):
            raise AiUsageEvidenceError("provider observation is future-dated")
        if source not in OBSERVATION_SOURCES:
            raise AiUsageEvidenceError("invalid provider evidence source")
        last_run_tokens = _tokens(last_run_tokens)
        weekly_used_percent = _percentage(weekly_used_percent)
        if reset_at is not None:
            if reset_at.tzinfo is None:
                raise AiUsageEvidenceError("invalid reset_at")
            reset_at = reset_at.astimezone(timezone.utc)
        if (weekly_used_percent is None) != (reset_at is None):
            raise AiUsageEvidenceError("weekly percentage and reset must be recorded together")
        if reset_at is not None and reset_at <= observed_at:
            raise AiUsageEvidenceError("provider reset must follow the observation")
        if last_run_tokens is None and weekly_used_percent is None:
            raise AiUsageEvidenceError("provider observation contains no usage evidence")
        observation = ProviderUsageObservation(
            schema_version=OBSERVATION_SCHEMA_VERSION,
            provider=provider,
            authentication_verified=True,
            observed_at=observed_at,
            source=source,
            last_run_tokens=last_run_tokens,
            weekly_used_percent=weekly_used_percent,
            reset_at=reset_at,
        )
        payload = asdict(observation)
        payload["observed_at"] = _canonical_timestamp(observed_at)
        payload["reset_at"] = _canonical_timestamp(reset_at) if reset_at else None
        self._ensure_directory()
        destination = self.path(provider)
        if destination.is_symlink():
            raise AiUsageEvidenceError("provider evidence path is unsafe")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.observation_dir,
                prefix=".provider-usage-",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                os.chmod(temporary, 0o600)
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            os.chmod(destination, 0o600)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise AiUsageEvidenceError("provider evidence could not be recorded") from exc
        return observation

    def load(self, provider: str) -> ProviderUsageObservation | None:
        path = self.path(provider)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise AiUsageEvidenceError("provider evidence is unavailable")
        try:
            details = path.stat()
            if (
                details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) & 0o077
                or details.st_nlink != 1
                or details.st_size > MAX_OBSERVATION_BYTES
            ):
                raise AiUsageEvidenceError("provider evidence is invalid")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise AiUsageEvidenceError("provider evidence is invalid") from exc
        expected = {
            "schema_version",
            "provider",
            "authentication_verified",
            "observed_at",
            "source",
            "last_run_tokens",
            "weekly_used_percent",
            "reset_at",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise AiUsageEvidenceError("provider evidence is invalid")
        if payload["schema_version"] != OBSERVATION_SCHEMA_VERSION:
            raise AiUsageEvidenceError("provider evidence schema is unsupported")
        provider = _provider(provider)
        if payload["provider"] != provider or payload["authentication_verified"] is not True:
            raise AiUsageEvidenceError("provider evidence is invalid")
        if payload["source"] not in OBSERVATION_SOURCES:
            raise AiUsageEvidenceError("provider evidence source is invalid")
        observed_at = _timestamp(payload["observed_at"], "observed_at")
        now = self._now_provider().astimezone(timezone.utc)
        if observed_at > now + timedelta(minutes=5):
            raise AiUsageEvidenceError("provider evidence is future-dated")
        last_run_tokens = _tokens(payload["last_run_tokens"])
        weekly_used_percent = _percentage(payload["weekly_used_percent"])
        reset_at = (
            _timestamp(payload["reset_at"], "reset_at")
            if payload["reset_at"] is not None
            else None
        )
        if (weekly_used_percent is None) != (reset_at is None):
            raise AiUsageEvidenceError("provider evidence is incomplete")
        if reset_at is not None and reset_at <= observed_at:
            raise AiUsageEvidenceError("provider evidence reset is invalid")
        if last_run_tokens is None and weekly_used_percent is None:
            raise AiUsageEvidenceError("provider evidence is incomplete")
        return ProviderUsageObservation(
            schema_version=OBSERVATION_SCHEMA_VERSION,
            provider=provider,
            authentication_verified=True,
            observed_at=observed_at,
            source=payload["source"],
            last_run_tokens=last_run_tokens,
            weekly_used_percent=weekly_used_percent,
            reset_at=reset_at,
        )


class AiUsageDashboardService:
    """Build read-only cards from approved local evidence without provider probes."""

    def __init__(
        self,
        usage_service: WorkerUsageService,
        observation_store: ProviderUsageObservationStore,
        now_provider: Callable[[], datetime] = _utc_now,
    ):
        self._usage_service = usage_service
        self._observation_store = observation_store
        self._now_provider = now_provider

    @staticmethod
    def _role(provider: str) -> tuple[str, str, str]:
        worker = "kimi-swarm" if provider == "kimi" else provider
        profile = get_worker_profile(worker)
        if provider == "kimi":
            return "Kimi", "Primary worker", "Kimi-first when budget allows"
        if provider == "codex":
            return profile.label, "Approved fallback", "Available only through governed routing"
        return profile.label, "Candidate — not active", "Not eligible for automatic routing"

    def _kimi(self) -> AiUsageCard:
        label, role, routing = self._role("kimi")
        summary = self._usage_service.get_summary("kimi")
        used = summary.weekly_used_percent
        balance_state = (
            BalanceState.CURRENT
            if summary.state in {UsageState.AVAILABLE, UsageState.PAUSED}
            else BalanceState.STALE
            if used is not None
            else BalanceState.UNAVAILABLE
        )
        return AiUsageCard(
            provider="kimi",
            label=label,
            role=role,
            routing_status=routing,
            balance_state=balance_state,
            weekly_used_percent=used,
            remaining_percent=max(0.0, 100.0 - used) if used is not None else None,
            automation_limit_percent=summary.weekly_percent_limit,
            automation_remaining_percent=(
                max(0.0, summary.weekly_percent_limit - used)
                if used is not None
                else None
            ),
            runtime_seconds=summary.runtime_seconds,
            runtime_limit_seconds=summary.runtime_limit_seconds,
            last_run_tokens=None,
            checked_at=summary.checked_at,
            reset_at=summary.reset_at,
            source=summary.source,
            authentication_verified=summary.source is not None,
            message=summary.message,
        )

    def _observed_provider(self, provider: str) -> AiUsageCard:
        label, role, routing = self._role(provider)
        try:
            observation = self._observation_store.load(provider)
        except AiUsageEvidenceError:
            observation = None
        if observation is None:
            product = "Codex subscription" if provider == "codex" else "Google Pro"
            return AiUsageCard(
                provider=provider,
                label=label,
                role=role,
                routing_status=routing,
                balance_state=BalanceState.UNAVAILABLE,
                weekly_used_percent=None,
                remaining_percent=None,
                automation_limit_percent=None,
                automation_remaining_percent=None,
                runtime_seconds=None,
                runtime_limit_seconds=None,
                last_run_tokens=None,
                checked_at=None,
                reset_at=None,
                source=None,
                authentication_verified=False,
                message=f"{product} balance has no approved automatic reading.",
            )
        age = self._now_provider().astimezone(timezone.utc) - observation.observed_at
        state = (
            BalanceState.STALE
            if age > OBSERVATION_MAX_AGE
            else BalanceState.CURRENT
            if observation.weekly_used_percent is not None
            else BalanceState.OBSERVED_ONLY
        )
        used = observation.weekly_used_percent
        return AiUsageCard(
            provider=provider,
            label=label,
            role=role,
            routing_status=routing,
            balance_state=state,
            weekly_used_percent=used,
            remaining_percent=max(0.0, 100.0 - used) if used is not None else None,
            automation_limit_percent=None,
            automation_remaining_percent=None,
            runtime_seconds=None,
            runtime_limit_seconds=None,
            last_run_tokens=observation.last_run_tokens,
            checked_at=observation.observed_at,
            reset_at=observation.reset_at,
            source=observation.source,
            authentication_verified=True,
            message=(
                "Provider percentage is owner-verified."
                if used is not None
                else (
                    "Authentication and measured request usage are verified; "
                    "exact balance is unavailable."
                )
            ),
        )

    def get_cards(self) -> tuple[AiUsageCard, ...]:
        return (self._kimi(), self._observed_provider("codex"), self._observed_provider("gemini"))


def _card_payload(card: AiUsageCard) -> dict[str, Any]:
    payload = asdict(card)
    payload["balance_state"] = card.balance_state.value
    for field in ("checked_at", "reset_at"):
        value = payload[field]
        payload[field] = _canonical_timestamp(value) if value else None
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record bounded AI usage observations.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--provider", choices=OBSERVATION_PROVIDERS, required=True)
    record.add_argument("--observed-at", required=True)
    record.add_argument("--source", choices=OBSERVATION_SOURCES, required=True)
    record.add_argument("--last-run-tokens", type=int)
    record.add_argument("--weekly-used", type=float)
    record.add_argument("--reset-at")
    show = subparsers.add_parser("show")
    show.add_argument("--provider", choices=("kimi",) + OBSERVATION_PROVIDERS)
    args = parser.parse_args(argv)
    store = ProviderUsageObservationStore(args.repo_root)
    usage = WorkerUsageService(args.repo_root)
    try:
        if args.command == "record":
            store.record(
                args.provider,
                observed_at=_timestamp(args.observed_at, "observed_at"),
                source=args.source,
                last_run_tokens=args.last_run_tokens,
                weekly_used_percent=args.weekly_used,
                reset_at=_timestamp(args.reset_at, "reset_at") if args.reset_at else None,
            )
        cards = AiUsageDashboardService(usage, store).get_cards()
        selected = [
            card
            for card in cards
            if not getattr(args, "provider", None) or card.provider == args.provider
        ]
        print(json.dumps([_card_payload(card) for card in selected], sort_keys=True))
        return 0
    except AiUsageEvidenceError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
