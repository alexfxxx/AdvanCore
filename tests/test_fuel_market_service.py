from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from advancore.models import Base, Customer, RecurringService, Route
from advancore.repositories import FuelMarketRepository, RecurringServiceRepository
from advancore.services.fuel_market_service import (
    FuelMarketService,
    FuelMarketValidationError,
)
from advancore.services.fuel_market_sources import (
    CollectedFuelPrices,
    FuelSourceError,
    SourcePrice,
)


class Collector:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = 0

    def collect(self):
        self.calls += 1
        if self.fail:
            raise FuelSourceError("SOURCE_UNAVAILABLE", "An approved fuel source was unavailable.")
        return CollectedFuelPrices(
            shell=SourcePrice("Shell", Decimal("4.10"), "shell date"),
            spc=SourcePrice("SPC", Decimal("3.90"), "spc date"),
        )


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    value = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield value
    finally:
        value.close()


def _recurring_service(session):
    customer = Customer(name="Synthetic Customer", status="active")
    route = Route(route_code="SYN", origin="A", destination="B", status="active")
    session.add_all([customer, route])
    session.flush()
    recurring = RecurringService(
        customer_id=customer.id,
        route_id=route.id,
        service_reference="SYN-MONTHLY",
        monthly_amount=Decimal("10000.00"),
        currency_code="SGD",
        effective_start_date=date(2026, 1, 1),
        status="active",
    )
    session.add(recurring)
    session.flush()
    return recurring


def test_daily_refresh_saves_atomic_shell_spc_midpoint_only_once(session):
    collector = Collector()
    service = FuelMarketService(FuelMarketRepository(session), collector=collector)
    now = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)
    first = service.refresh_if_due(now)
    second = service.refresh_if_due(now)
    view = service.market_view(date(2026, 9, 3))
    assert first.succeeded is True
    assert second.attempted is False
    assert collector.calls == 1
    assert view.status == "current"
    assert view.snapshot.benchmark_price_per_litre == Decimal("4.0000")


def test_failed_next_day_refresh_keeps_last_snapshot_and_marks_it_stale(session):
    repository = FuelMarketRepository(session)
    FuelMarketService(repository, collector=Collector()).refresh_if_due(
        datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)
    )
    failed = FuelMarketService(repository, collector=Collector(fail=True)).refresh_if_due(
        datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)
    )
    view = FuelMarketService(repository).market_view(date(2026, 9, 4))
    assert failed.succeeded is False
    assert view.status == "stale"
    assert view.snapshot.observed_on == date(2026, 9, 3)
    assert view.failure_summary == "An approved fuel source was unavailable."


def test_draft_requires_contract_facts_and_current_verified_benchmark(session):
    recurring = _recurring_service(session)
    repository = FuelMarketRepository(session)
    service = FuelMarketService(repository, RecurringServiceRepository(session), Collector())
    service.refresh_if_due(datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc))
    assert service.adjustment_draft(recurring.id, date(2026, 9, 3)).calculation_status == "contract_terms_not_configured"

    rule = service.configure_rule(
        recurring.id,
        effective_from=date(2026, 9, 1),
        baseline_price_per_litre=Decimal("3.00"),
        fuel_cost_share_percent=Decimal("30"),
        tolerance_percent=Decimal("5"),
    )
    draft = service.adjustment_draft(recurring.id, date(2026, 9, 3))
    assert rule.baseline_price_per_litre == Decimal("3.0000")
    assert draft.calculation_status == "draft_ready"
    assert draft.price_variance_percent == Decimal("33.3333")
    assert draft.draft_adjustment_amount == Decimal("1000.00")
    assert draft.adjusted_monthly_amount == Decimal("11000.00")


def test_new_rule_is_forward_only_and_closes_prior_rule(session):
    recurring = _recurring_service(session)
    service = FuelMarketService(
        FuelMarketRepository(session), RecurringServiceRepository(session)
    )
    first = service.configure_rule(
        recurring.id,
        effective_from=date(2026, 1, 1),
        baseline_price_per_litre=Decimal("3"),
        fuel_cost_share_percent=Decimal("20"),
        tolerance_percent=Decimal("5"),
    )
    service.configure_rule(
        recurring.id,
        effective_from=date(2026, 7, 1),
        baseline_price_per_litre=Decimal("3.50"),
        fuel_cost_share_percent=Decimal("20"),
        tolerance_percent=Decimal("5"),
    )
    assert first.effective_to == date(2026, 6, 30)
    with pytest.raises(FuelMarketValidationError, match="after the current terms"):
        service.configure_rule(
            recurring.id,
            effective_from=date(2026, 6, 1),
            baseline_price_per_litre=Decimal("3.20"),
            fuel_cost_share_percent=Decimal("20"),
            tolerance_percent=Decimal("5"),
        )


def test_archived_recurring_service_cannot_produce_current_adjustment(session):
    recurring = _recurring_service(session)
    recurring.status = "archived"
    service = FuelMarketService(
        FuelMarketRepository(session), RecurringServiceRepository(session)
    )

    with pytest.raises(FuelMarketValidationError, match="archived recurring service"):
        service.adjustment_draft(recurring.id, date(2026, 9, 3))
