from contextlib import contextmanager, nullcontext
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from advancore.models import Base, LegalEntity, Vehicle
from advancore.repositories import VehicleRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.vehicle_service import (
    DuplicateVehicleError,
    HirePurchaseProjection,
    VehicleService,
    VehicleValidationError,
    calculate_hire_purchase_projection,
)


def build_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    return factory


def test_vehicle_register_normalizes_persists_lists_and_changes_status():
    factory = build_service()
    with session_scope(factory) as session:
        service = VehicleService(VehicleRepository(session))
        vehicle = service.create_vehicle(" sbs 1234-a ", "  Electric Bus  ")
        vehicle_id = vehicle.id
        assert vehicle.registration_number == "SBS 1234-A"
        assert vehicle.make_model == "Electric Bus"
        assert vehicle.status == "active"

    with session_scope(factory) as session:
        service = VehicleService(VehicleRepository(session))
        assert [item.id for item in service.list_vehicles()] == [vehicle_id]
        assert service.set_status(vehicle_id, "out_of_service").status == "out_of_service"


def test_vehicle_register_rejects_invalid_duplicate_and_unknown_status():
    factory = build_service()
    with session_scope(factory) as session:
        service = VehicleService(VehicleRepository(session))
        with pytest.raises(VehicleValidationError):
            service.create_vehicle(" ")
        service.create_vehicle("BUS-1")
        with pytest.raises(DuplicateVehicleError):
            service.create_vehicle(" bus-1 ")
        with pytest.raises(VehicleValidationError):
            service.set_status(1, "invented")


def test_vehicle_table_constraint_rejects_unknown_status():
    factory = build_service()
    with pytest.raises(Exception):
        with session_scope(factory) as session:
            session.add(Vehicle(registration_number="BUS-2", status="invented"))


def test_vehicle_mutations_record_only_bounded_activity_identifiers():
    class Activity:
        def __init__(self):
            self.calls = []

        def record_activity(self, action, entity_type, entity_id):
            self.calls.append((action, entity_type, entity_id))

    factory = build_service()
    activity = Activity()
    with session_scope(factory) as session:
        service = VehicleService(VehicleRepository(session), activity)
        vehicle = service.create_vehicle("BUS-PRIVATE", "Sensitive model note")
        service.set_status(vehicle.id, "retired")
        service.update_details(vehicle.id, passenger_capacity=13)
        vehicle_id = vehicle.id

    assert activity.calls == [
        ("vehicle_created", "vehicle", vehicle_id),
        ("vehicle_status_changed", "vehicle", vehicle_id),
        ("vehicle_details_updated", "vehicle", vehicle_id),
    ]
    assert "Sensitive" not in repr(activity.calls)

def test_vehicle_details_preserve_nulls_exact_capacity_costs_and_combined_filters():
    factory = build_service()
    with session_scope(factory) as session:
        owner = LegalEntity(name="Owner One", status="active")
        session.add(owner); session.flush()
        service = VehicleService(VehicleRepository(session))
        selected = service.create_vehicle("PC5234D")
        other = service.create_vehicle("LORRY-2")
        service.update_details(selected.id, registered_owner_id=owner.id, vehicle_type="Bus", passenger_capacity=19,
            parking_monthly_cost="120.50", insurance_annual_amount="1000", road_tax_amount="850", road_tax_period_months=6)
        service.update_details(other.id, vehicle_type="lorry", passenger_capacity=3)
        found = service.list_vehicles(owner.id, "Bus", 19)
        assert [item.registration_number for item in found] == ["PC5234D"]
        assert found[0].passenger_capacity == 19
        assert found[0].manufacture_year is None
        assert str(found[0].road_tax_amount) == "850.00"

@pytest.mark.parametrize("details", [
    {"vehicle_type": "van"}, {"passenger_capacity": 0}, {"parking_monthly_cost": "-1"},
    {"unladen_weight_kg": "100000000.00"},
    {"maximum_laden_weight_kg": "100000000.00"},
    {"road_tax_amount": "850"}, {"road_tax_period_months": 6},
])
def test_vehicle_details_reject_invalid_values_without_estimation(details):
    factory = build_service()
    with session_scope(factory) as session:
        service = VehicleService(VehicleRepository(session)); vehicle = service.create_vehicle("BUS-9")
        with pytest.raises(VehicleValidationError): service.update_details(vehicle.id, **details)
        assert vehicle.road_tax_amount is None


@pytest.mark.parametrize(
    ("start", "as_of", "term", "expected"),
    [
        (date(2024, 1, 31), date(2024, 2, 28), 12, 12),
        (date(2024, 1, 31), date(2024, 2, 29), 12, 11),
        (date(2023, 1, 31), date(2023, 2, 28), 12, 11),
        (date(2024, 1, 31), date(2024, 3, 30), 12, 11),
        (date(2024, 1, 31), date(2024, 3, 31), 12, 10),
        (date(2027, 1, 15), date(2026, 8, 30), 24, 24),
        (date(2024, 1, 15), date(2026, 8, 30), 24, 0),
    ],
)
def test_hire_purchase_projection_uses_approved_monthly_dates(
    start, as_of, term, expected
):
    projection = calculate_hire_purchase_projection(
        start,
        term,
        Decimal("1234.56"),
        as_of=as_of,
    )
    assert projection == HirePurchaseProjection(
        expected,
        Decimal("1234.56") * expected,
    )


def test_hire_purchase_projection_preserves_missing_inputs():
    assert calculate_hire_purchase_projection(
        None, 12, Decimal("1000"), as_of=date(2026, 8, 30)
    ) == HirePurchaseProjection(None, None)
    assert calculate_hire_purchase_projection(
        date(2026, 1, 1), None, Decimal("1000"), as_of=date(2026, 8, 30)
    ) == HirePurchaseProjection(None, None)
    assert calculate_hire_purchase_projection(
        date(2026, 1, 1), 12, None, as_of=date(2026, 8, 30)
    ) == HirePurchaseProjection(5, None)


def test_vehicle_finance_fields_are_nullable_and_persist_when_recorded():
    factory = build_service()
    with session_scope(factory) as session:
        service = VehicleService(VehicleRepository(session))
        vehicle = service.create_vehicle("BUS-FINANCE")
        updated = service.update_details(
            vehicle.id,
            finance_company="  Example Finance  ",
            original_loan_amount="120000.00",
            monthly_instalment="2500.00",
            loan_start_date=date(2026, 1, 31),
            loan_term_months=48,
        )
        assert updated.finance_company == "Example Finance"
        assert updated.original_loan_amount == Decimal("120000.00")
        assert updated.monthly_instalment == Decimal("2500.00")
        assert updated.loan_start_date == date(2026, 1, 31)
        assert updated.loan_term_months == 48


@pytest.mark.parametrize(
    "details",
    [
        {"original_loan_amount": "-0.01"},
        {"monthly_instalment": "-0.01"},
        {"loan_term_months": 0},
        {"loan_term_months": True},
        {"loan_start_date": "2026-01-01"},
        {"finance_company": "x" * 121},
    ],
)
def test_vehicle_finance_fields_reject_invalid_values(details):
    factory = build_service()
    with session_scope(factory) as session:
        service = VehicleService(VehicleRepository(session))
        vehicle = service.create_vehicle("BUS-INVALID-FINANCE")
        with pytest.raises(VehicleValidationError):
            service.update_details(vehicle.id, **details)
