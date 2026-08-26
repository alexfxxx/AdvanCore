from datetime import date, datetime
import pytest
from sqlalchemy import create_engine
from advancore.models import Base,Route
from advancore.repositories import TripRepository
from advancore.services.database import create_session_factory,session_scope
from advancore.services.trip_service import TripService,TripValidationError
def test_trip_create_and_status():
    e=create_engine("sqlite:///:memory:");Base.metadata.create_all(e);db=create_session_factory(e)
    with session_scope(db) as s:
        r=Route(route_code="R",origin="A",destination="B");s.add(r);s.flush();service=TripService(TripRepository(s));t=service.create_trip(" t-1 ",r.id,date(2026,8,27));i=t.id;assert t.trip_reference=="T-1"
    with session_scope(db) as s: assert TripService(TripRepository(s)).set_status(i,"completed").status=="completed"
def test_trip_requires_real_route():
    e=create_engine("sqlite:///:memory:");Base.metadata.create_all(e);db=create_session_factory(e)
    with session_scope(db) as s:
        with pytest.raises(TripValidationError):TripService(TripRepository(s)).create_trip("T",99,date.today())
def test_trip_rejects_timestamp_instead_of_silently_truncating_it():
    e=create_engine("sqlite:///:memory:");Base.metadata.create_all(e);db=create_session_factory(e)
    with session_scope(db) as s:
        r=Route(route_code="R",origin="A",destination="B");s.add(r);s.flush()
        with pytest.raises(TripValidationError):TripService(TripRepository(s)).create_trip("T",r.id,datetime(2026,8,27,23,30))
