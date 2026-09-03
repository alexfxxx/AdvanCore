"""Daily official diesel benchmark and contract-bound draft adjustment logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import threading
from zoneinfo import ZoneInfo

from advancore.models import FuelMarketSnapshot, RecurringServiceFuelRule
from advancore.repositories import FuelMarketRepository, RecurringServiceRepository
from advancore.services.fuel_market_sources import FuelSourceError, OfficialFuelMarketCollector


SINGAPORE = ZoneInfo("Asia/Singapore")
MONEY = Decimal("0.01")
PERCENT = Decimal("0.0001")


class FuelMarketValidationError(ValueError):
    pass


class FuelMarketNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class RefreshOutcome:
    attempted: bool
    succeeded: bool
    code: str


@dataclass(frozen=True)
class FuelMarketView:
    snapshot: FuelMarketSnapshot | None
    history: tuple[FuelMarketSnapshot, ...]
    stale: bool
    status: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    failure_summary: str | None


@dataclass(frozen=True)
class FuelAdjustmentDraft:
    rule: RecurringServiceFuelRule | None
    rules: tuple[RecurringServiceFuelRule, ...]
    benchmark: FuelMarketSnapshot | None
    stale: bool
    calculation_status: str
    price_variance_percent: Decimal | None
    draft_adjustment_amount: Decimal | None
    adjusted_monthly_amount: Decimal | None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _decimal(value: Decimal, label: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FuelMarketValidationError(f"{label} must be a number.") from exc
    if not result.is_finite():
        raise FuelMarketValidationError(f"{label} must be finite.")
    return result


class FuelMarketService:
    def __init__(
        self,
        repository: FuelMarketRepository,
        recurring_services: RecurringServiceRepository | None = None,
        collector: OfficialFuelMarketCollector | None = None,
    ):
        self._repo = repository
        self._recurring = recurring_services
        self._collector = collector

    def refresh_if_due(self, now: datetime | None = None) -> RefreshOutcome:
        instant = _aware(now) or datetime.now(timezone.utc)
        local_day = instant.astimezone(SINGAPORE).date()
        state = self._repo.refresh_state()
        prior_attempt = _aware(state.last_attempt_at)
        if prior_attempt and prior_attempt.astimezone(SINGAPORE).date() == local_day:
            return RefreshOutcome(False, state.last_success_at == state.last_attempt_at, "ALREADY_ATTEMPTED_TODAY")

        state.last_attempt_at = instant
        collector = self._collector or OfficialFuelMarketCollector()
        try:
            prices = collector.collect()
            benchmark = (
                prices.shell.price_per_litre + prices.spc.price_per_litre
            ) / Decimal("2")
            existing = self._repo.snapshot_on(local_day)
            if existing is None:
                self._repo.add_snapshot(
                    FuelMarketSnapshot(
                        observed_on=local_day,
                        shell_price_per_litre=prices.shell.price_per_litre,
                        spc_price_per_litre=prices.spc.price_per_litre,
                        benchmark_price_per_litre=benchmark.quantize(Decimal("0.0001")),
                        shell_source_updated_at=prices.shell.source_updated_at,
                        spc_source_updated_at=prices.spc.source_updated_at,
                        refreshed_at=instant,
                    )
                )
            state.last_success_at = instant
            state.consecutive_failures = 0
            state.last_failure_code = None
            state.last_failure_summary = None
            return RefreshOutcome(True, True, "REFRESHED")
        except FuelSourceError as exc:
            state.consecutive_failures += 1
            state.last_failure_code = exc.code[:40]
            state.last_failure_summary = str(exc)[:240]
            return RefreshOutcome(True, False, exc.code)
        except Exception:
            state.consecutive_failures += 1
            state.last_failure_code = "UNEXPECTED_REFRESH_FAILURE"
            state.last_failure_summary = "The daily fuel refresh failed safely."
            return RefreshOutcome(True, False, "UNEXPECTED_REFRESH_FAILURE")

    def market_view(self, on_date: date | None = None) -> FuelMarketView:
        local_day = on_date or datetime.now(timezone.utc).astimezone(SINGAPORE).date()
        snapshot = self._repo.latest_snapshot()
        state = self._repo.refresh_state()
        last_attempt = _aware(state.last_attempt_at)
        last_success = _aware(state.last_success_at)
        failed_after_success = bool(last_attempt and (last_success is None or last_attempt > last_success))
        stale = snapshot is None or snapshot.observed_on < local_day or failed_after_success
        if snapshot is None:
            status = "unavailable"
        elif stale:
            status = "stale"
        else:
            status = "current"
        return FuelMarketView(
            snapshot=snapshot,
            history=tuple(reversed(self._repo.recent_snapshots())),
            stale=stale,
            status=status,
            last_attempt_at=last_attempt,
            last_success_at=last_success,
            failure_summary=state.last_failure_summary,
        )

    def configure_rule(
        self,
        recurring_service_id: int,
        *,
        effective_from: date,
        baseline_price_per_litre: Decimal,
        fuel_cost_share_percent: Decimal,
        tolerance_percent: Decimal,
    ) -> RecurringServiceFuelRule:
        if self._recurring is None:
            raise RuntimeError("Recurring-service access is unavailable.")
        recurring = self._recurring.get_by_id(recurring_service_id)
        if recurring is None:
            raise FuelMarketNotFoundError("The selected recurring service could not be found.")
        if recurring.status == "archived":
            raise FuelMarketValidationError("An archived recurring service cannot receive new contract terms.")

        baseline = _decimal(baseline_price_per_litre, "Baseline price")
        share = _decimal(fuel_cost_share_percent, "Fuel cost share")
        tolerance = _decimal(tolerance_percent, "Tolerance")
        if baseline <= 0:
            raise FuelMarketValidationError("Baseline price must be greater than zero.")
        if share < 0 or share > 100:
            raise FuelMarketValidationError("Fuel cost share must be between 0 and 100 percent.")
        if tolerance < 0 or tolerance > 100:
            raise FuelMarketValidationError("Tolerance must be between 0 and 100 percent.")

        prior = self._repo.latest_rule(recurring_service_id)
        if prior is not None:
            if effective_from <= prior.effective_from:
                raise FuelMarketValidationError("New contract terms must start after the current terms.")
            if prior.effective_to is not None:
                raise FuelMarketValidationError("The latest contract terms are already closed.")
            prior.effective_to = effective_from - timedelta(days=1)

        return self._repo.add_rule(
            RecurringServiceFuelRule(
                recurring_service_id=recurring_service_id,
                effective_from=effective_from,
                baseline_price_per_litre=baseline.quantize(Decimal("0.0001")),
                fuel_cost_share_percent=share.quantize(PERCENT),
                tolerance_percent=tolerance.quantize(PERCENT),
            )
        )

    def adjustment_draft(
        self, recurring_service_id: int, on_date: date | None = None
    ) -> FuelAdjustmentDraft:
        if self._recurring is None:
            raise RuntimeError("Recurring-service access is unavailable.")
        recurring = self._recurring.get_by_id(recurring_service_id)
        if recurring is None:
            raise FuelMarketNotFoundError("The selected recurring service could not be found.")
        if recurring.status == "archived":
            raise FuelMarketValidationError(
                "An archived recurring service cannot produce a current fuel adjustment."
            )
        local_day = on_date or datetime.now(timezone.utc).astimezone(SINGAPORE).date()
        rule = self._repo.applicable_rule(recurring_service_id, local_day)
        rules = tuple(self._repo.list_rules(recurring_service_id))
        market = self.market_view(local_day)
        if rule is None:
            return FuelAdjustmentDraft(None, rules, market.snapshot, market.stale, "contract_terms_not_configured", None, None, None)
        if market.snapshot is None:
            return FuelAdjustmentDraft(rule, rules, None, True, "benchmark_unavailable", None, None, None)
        if market.stale:
            return FuelAdjustmentDraft(rule, rules, market.snapshot, True, "benchmark_stale", None, None, None)

        variance = (
            (market.snapshot.benchmark_price_per_litre - rule.baseline_price_per_litre)
            / rule.baseline_price_per_litre
            * Decimal("100")
        )
        if abs(variance) <= rule.tolerance_percent:
            adjustment = Decimal("0.00")
        else:
            adjustment = (
                recurring.monthly_amount
                * (rule.fuel_cost_share_percent / Decimal("100"))
                * (variance / Decimal("100"))
            ).quantize(MONEY, rounding=ROUND_HALF_UP)
        adjusted = (recurring.monthly_amount + adjustment).quantize(MONEY, rounding=ROUND_HALF_UP)
        return FuelAdjustmentDraft(
            rule,
            rules,
            market.snapshot,
            False,
            "draft_ready",
            variance.quantize(PERCENT, rounding=ROUND_HALF_UP),
            adjustment,
            adjusted,
        )


class DailyFuelMarketRefresher:
    """Daemon scheduler: check hourly, attempt externally at most once a day."""

    def __init__(self, interval_seconds: int = 3600):
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _refresh(self) -> None:
        try:
            from advancore.services.database import session_scope
            with session_scope() as session:
                FuelMarketService(FuelMarketRepository(session)).refresh_if_due()
        except Exception:
            # Startup and the primary UI stay available when the optional
            # external refresh or an unapplied migration is unavailable.
            return

    def _run(self) -> None:
        while not self._stop.is_set():
            self._refresh()
            self._stop.wait(self._interval_seconds)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="advancore-daily-fuel-refresh",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def daily_refresh_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL")) and os.getenv(
        "ADVANCORE_FUEL_REFRESH_ENABLED", "1"
    ) not in {"0", "false", "False"}
