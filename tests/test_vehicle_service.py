from contextlib import contextmanager, nullcontext

import pytest
from sqlalchemy import create_engine

from advancore.models import Base, Vehicle
from advancore.repositories import VehicleRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.vehicle_service import (
    DuplicateVehicleError,
    VehicleService,
    VehicleValidationError,
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
        vehicle_id = vehicle.id

    assert activity.calls == [
        ("vehicle_created", "vehicle", vehicle_id),
        ("vehicle_status_changed", "vehicle", vehicle_id),
    ]
    assert "Sensitive" not in repr(activity.calls)
