from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from advancore.models import Base, Driver
from advancore.repositories import DriverEmploymentRepository
from advancore.services.driver_employment_service import (
    DriverEmploymentConflictError,
    DriverEmploymentService,
    DriverEmploymentValidationError,
)


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    driver = Driver(name="Synthetic Driver", employee_reference="SYN-D", status="active")
    session.add(driver)
    session.flush()
    return session, DriverEmploymentService(DriverEmploymentRepository(session)), driver


def _create(service, driver_id, **overrides):
    values = {
        "driver_id": driver_id,
        "effective_month": date(2026, 7, 1),
        "worker_category": "local_pr",
        "basic_salary": Decimal("3000.00"),
        "employer_cpf_amount": Decimal("510.00"),
        "monthly_levy_amount": None,
        "monthly_allowance": Decimal("100.00"),
        "employment_status": "active",
    }
    values.update(overrides)
    return service.create_record(**values)


def test_local_and_foreign_history_is_newest_first_and_does_not_change_driver_status():
    session, service, driver = _setup()
    local = _create(service, driver.id)
    foreign = _create(
        service,
        driver.id,
        effective_month=date(2026, 8, 1),
        worker_category="foreign_levy",
        employer_cpf_amount=None,
        monthly_levy_amount=Decimal("450.00"),
        employment_status="inactive",
    )

    records = service.list_by_driver(driver.id)
    assert [item.id for item in records] == [foreign.id, local.id]
    assert records[0].monthly_levy_amount == Decimal("450.00")
    assert records[1].employer_cpf_amount == Decimal("510.00")
    assert driver.status == "active"
    session.close()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"effective_month": date(2026, 7, 2)}, "first calendar day"),
        ({"basic_salary": Decimal("-1")}, "non-negative"),
        ({"monthly_allowance": Decimal("1.234")}, "two decimal"),
        ({"monthly_levy_amount": Decimal("10")}, "cannot contain"),
        ({"worker_category": "foreign_levy", "employer_cpf_amount": Decimal("10")}, "cannot contain"),
        ({"employment_status": "unavailable"}, "status is invalid"),
    ],
)
def test_invalid_payroll_facts_fail_before_write(overrides, message):
    session, service, driver = _setup()
    with pytest.raises(DriverEmploymentValidationError, match=message):
        _create(service, driver.id, **overrides)
    assert service.list_by_driver(driver.id) == []
    session.close()


def test_duplicate_effective_month_is_rejected_without_overwrite():
    session, service, driver = _setup()
    original = _create(service, driver.id)
    with pytest.raises(DriverEmploymentConflictError):
        _create(service, driver.id, basic_salary=Decimal("3200.00"))
    records = service.list_by_driver(driver.id)
    assert len(records) == 1
    assert records[0].id == original.id
    assert records[0].basic_salary == Decimal("3000.00")
    session.close()
