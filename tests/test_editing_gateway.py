from contextlib import contextmanager
from datetime import date, timezone
from decimal import Decimal
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from advancore.api.editing_gateway import DatabaseEditingGateway, EditingConflictError
from advancore.api.schemas import VehicleDetailsRequest
from advancore.models import ActivityLog, Base


def _gateway():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    class IsolatedEditingGateway(DatabaseEditingGateway):
        @staticmethod
        @contextmanager
        def _session():
            session = factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    return IsolatedEditingGateway(), factory


def test_gateway_reuses_services_and_activity_log_without_live_database():
    gateway, factory = _gateway()

    project = gateway.create_project("Operations", "Confirmed local edit")
    gateway.edit_project(project.id, "Operations", "Updated safely")
    knowledge = gateway.create_knowledge("Runbook", "Draft content")
    reviewed_at = knowledge.updated_at.replace(tzinfo=timezone.utc)
    with pytest.raises(EditingConflictError, match="changed after it was reviewed"):
        gateway.approve_knowledge(knowledge.id, reviewed_at, "0" * 64)
    approved = gateway.approve_knowledge(
        knowledge.id,
        reviewed_at,
        sha256(knowledge.content.encode("utf-8")).hexdigest(),
    )
    replacement = gateway.replace_knowledge(approved.id)
    company = gateway.create_legal_entity("Advan Transport")
    vehicle = gateway.create_vehicle("TEST-170", "Test bus")
    updated = gateway.update_vehicle_details(
        vehicle.id,
        VehicleDetailsRequest(
            confirmed=True,
            registered_owner_id=company.id,
            manufacture_year=2026,
            passenger_capacity=40,
            vehicle_type="Bus",
            parking_provider="P-Park",
            parking_location="Test location",
            parking_monthly_cost="100.00",
            road_tax_amount="850.00",
            road_tax_period_months=12,
        ),
    )
    driver = gateway.create_driver("Test Driver", "DR-170")
    customer = gateway.create_customer("Test Customer", "CU-170")
    route = gateway.create_route("RT-170", "Origin", "Destination")
    trip = gateway.create_trip("TRIP-175", route.id, date(2026, 9, 2))
    assignment = gateway.create_trip_assignment(trip.id, vehicle.id, driver.id)
    fuel_entry = gateway.create_fuel_entry(
        vehicle.id, date(2026, 9, 2), "45.25", "120.00", "12345.6"
    )
    financial_entry = gateway.create_financial_entry(
        date(2026, 9, 2),
        "expense",
        "120.00",
        "sgd",
        "Test fuel fact",
        trip.id,
        customer.id,
    )

    assert replacement.status == "draft"
    assert replacement.replaces_knowledge_item_id == approved.id
    assert updated.registered_owner_id == company.id
    assert updated.passenger_capacity == 40
    assert gateway.set_driver_status(driver.id, "unavailable").status == "unavailable"
    assert gateway.set_customer_status(customer.id, "inactive").status == "inactive"
    assert gateway.set_route_status(route.id, "inactive").status == "inactive"
    assert gateway.set_trip_status(trip.id, "completed").status == "completed"
    assert gateway.release_trip_assignment(assignment.id).status == "released"
    assert fuel_entry.litres == Decimal("45.25")
    assert financial_entry.currency_code == "SGD"

    with factory() as session:
        actions = [item.action for item in session.scalars(select(ActivityLog)).all()]
    assert "project_created" in actions
    assert "knowledge_created" in actions
    assert "vehicle_created" in actions
    assert "driver_created" in actions
    assert "customer_created" in actions
