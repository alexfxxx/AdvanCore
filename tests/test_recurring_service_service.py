from datetime import date, time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from advancore.models import Base, Customer, RecurringService, Route
from advancore.repositories import CustomerRepository, RecurringServiceRepository, RouteRepository
from advancore.services.recurring_service_service import (
    RecurringServiceConflictError,
    RecurringServiceService,
    RecurringServiceValidationError,
)


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    customer = Customer(name="Synthetic Customer", customer_reference="SYN-C", status="active")
    route = Route(route_code="SYN-R", origin="Alpha", destination="Omega", status="active")
    session.add_all((customer, route))
    session.flush()
    service = RecurringServiceService(
        RecurringServiceRepository(session), CustomerRepository(session), RouteRepository(session)
    )
    return session, service, customer.id, route.id


def _create(service, customer_id, route_id, **overrides):
    values = {
        "customer_id": customer_id,
        "route_id": route_id,
        "service_reference": "SYN-MORNING",
        "vehicle_requirement": "Synthetic 40-seat requirement",
        "monthly_amount": Decimal("1234.50"),
        "currency_code": "SGD",
        "effective_start_date": date(2026, 1, 1),
        "effective_end_date": None,
        "weekdays": [0, 1, 2, 3, 4],
        "stops": [
            {"stop_order": 0, "location_name": "Synthetic A", "scheduled_time": time(7, 0)},
            {"stop_order": 1, "location_name": "Synthetic B", "scheduled_time": time(7, 20)},
        ],
    }
    values.update(overrides)
    return service.create_service(**values)


def test_create_lists_nested_fixed_monthly_service_without_proration():
    session, service, customer_id, route_id = _setup()
    saved = _create(service, customer_id, route_id)

    listed = service.list_by_customer(customer_id)
    assert [item.id for item in listed] == [saved.id]
    assert saved.monthly_amount == Decimal("1234.50")
    assert [item.weekday for item in saved.days] == [0, 1, 2, 3, 4]
    assert [item.location_name for item in saved.stops] == ["Synthetic A", "Synthetic B"]
    session.close()


def test_forward_replacement_archives_prior_and_preserves_reference_history():
    session, service, customer_id, route_id = _setup()
    prior = _create(service, customer_id, route_id)

    replacement = service.replace_service(
        prior.id,
        service_reference="SYN-MORNING",
        route_id=route_id,
        vehicle_requirement="Synthetic 45-seat requirement",
        monthly_amount=Decimal("1400.00"),
        currency_code="SGD",
        effective_start_date=date(2026, 7, 1),
        effective_end_date=None,
        weekdays=[0, 1, 2, 3, 4],
        stops=[{"stop_order": 0, "location_name": "Synthetic C", "scheduled_time": time(7, 15)}],
    )

    session.refresh(prior)
    assert prior.status == "archived"
    assert prior.effective_end_date == date(2026, 6, 30)
    assert replacement.replaces_recurring_service_id == prior.id
    assert replacement.service_reference == prior.service_reference
    assert len(session.scalars(select(RecurringService)).all()) == 2
    session.close()


def test_forward_replacement_never_extends_a_previously_ended_service():
    session, service, customer_id, route_id = _setup()
    prior = _create(
        service,
        customer_id,
        route_id,
        effective_end_date=date(2026, 6, 30),
    )

    service.replace_service(
        prior.id,
        service_reference="SYN-MORNING",
        route_id=route_id,
        vehicle_requirement="Synthetic 45-seat requirement",
        monthly_amount=Decimal("1400.00"),
        currency_code="SGD",
        effective_start_date=date(2026, 8, 1),
        effective_end_date=None,
        weekdays=[0, 1, 2, 3, 4],
        stops=[
            {
                "stop_order": 0,
                "location_name": "Synthetic C",
                "scheduled_time": time(7, 15),
            }
        ],
    )

    session.refresh(prior)
    assert prior.effective_end_date == date(2026, 6, 30)
    session.close()


def test_database_rejects_more_than_one_successor_for_a_service():
    session, service, customer_id, route_id = _setup()
    prior = _create(service, customer_id, route_id)
    prior.status = "archived"
    first = RecurringService(
        customer_id=customer_id,
        route_id=route_id,
        service_reference="SYN-FIRST",
        monthly_amount=Decimal("1000.00"),
        currency_code="SGD",
        effective_start_date=date(2026, 7, 1),
        status="active",
        replaces_recurring_service_id=prior.id,
    )
    second = RecurringService(
        customer_id=customer_id,
        route_id=route_id,
        service_reference="SYN-SECOND",
        monthly_amount=Decimal("1100.00"),
        currency_code="SGD",
        effective_start_date=date(2026, 8, 1),
        status="active",
        replaces_recurring_service_id=prior.id,
    )
    session.add_all((first, second))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.close()


def test_database_rejects_duplicate_live_reference_with_different_start_dates():
    session, service, customer_id, route_id = _setup()
    first = RecurringService(
        customer_id=customer_id,
        route_id=route_id,
        service_reference="SYN-LIVE",
        monthly_amount=Decimal("1000.00"),
        currency_code="SGD",
        effective_start_date=date(2026, 1, 1),
        status="active",
    )
    second = RecurringService(
        customer_id=customer_id,
        route_id=route_id,
        service_reference="SYN-LIVE",
        monthly_amount=Decimal("1100.00"),
        currency_code="SGD",
        effective_start_date=date(2026, 2, 1),
        status="paused",
    )
    session.add_all((first, second))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.close()


def test_replacement_lookup_locks_the_predecessor_row():
    session = MagicMock()
    session.execute.return_value.unique.return_value.scalar_one_or_none.return_value = None
    repository = RecurringServiceRepository(session)

    repository.get_by_id_for_update(41)

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert " JOIN " not in sql


def test_duplicate_active_reference_and_archived_reactivation_fail_closed():
    session, service, customer_id, route_id = _setup()
    saved = _create(service, customer_id, route_id)
    with pytest.raises(RecurringServiceConflictError):
        _create(service, customer_id, route_id, effective_start_date=date(2026, 2, 1))

    service.set_status(saved.id, "archived")
    with pytest.raises(RecurringServiceConflictError):
        service.set_status(saved.id, "active")
    session.close()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"monthly_amount": Decimal("1.234")}, "two decimal"),
        ({"weekdays": [0, 0]}, "selected once"),
        ({"stops": []}, "one stop"),
        ({"currency_code": "S1D"}, "three letters"),
        ({"effective_end_date": date(2025, 12, 31)}, "before the start"),
    ],
)
def test_invalid_commercial_inputs_are_rejected_before_write(override, message):
    session, service, customer_id, route_id = _setup()
    with pytest.raises(RecurringServiceValidationError, match=message):
        _create(service, customer_id, route_id, **override)
    assert session.scalars(select(RecurringService)).all() == []
    session.close()
