from datetime import date
import pytest
from sqlalchemy import create_engine
from advancore.models import Base, Driver, Route, Trip, Vehicle
from advancore.repositories import TripAssignmentRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.trip_assignment_service import DuplicateTripAssignmentError, TripAssignmentService, TripAssignmentValidationError

def setup():
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); db=create_session_factory(engine)
    with session_scope(db) as s:
        route=Route(route_code="R",origin="A",destination="B"); vehicle=Vehicle(registration_number="BUS"); driver=Driver(name="Driver")
        s.add_all([route,vehicle,driver]); s.flush(); trip=Trip(trip_reference="T",route_id=route.id,service_date=date(2026,8,27)); s.add(trip); s.flush(); ids=(trip.id,vehicle.id,driver.id)
    return db,ids

def test_assignment_requires_active_real_resources_and_releases():
    db,ids=setup()
    with session_scope(db) as s:
        service=TripAssignmentService(TripAssignmentRepository(s)); item=service.assign(*ids); identifier=item.id
        with pytest.raises(DuplicateTripAssignmentError): service.assign(*ids)
    with session_scope(db) as s:
        service=TripAssignmentService(TripAssignmentRepository(s)); assert service.release(identifier).status=="released"

def test_assignment_rejects_inactive_resource():
    db,ids=setup()
    with session_scope(db) as s:
        s.get(Vehicle,ids[1]).status="retired"
        with pytest.raises(TripAssignmentValidationError): TripAssignmentService(TripAssignmentRepository(s)).assign(*ids)
