from datetime import date, datetime
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from advancore.models import Base, Vehicle
from advancore.repositories import FuelEntryRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.fuel_entry_service import FuelEntryService, FuelEntryValidationError

def setup():
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); db=create_session_factory(engine)
    with session_scope(db) as s: vehicle=Vehicle(registration_number="BUS"); s.add(vehicle); s.flush(); identifier=vehicle.id
    return db,identifier

def test_records_exact_real_values_and_lists_newest_first():
    db,vehicle_id=setup()
    with session_scope(db) as s:
        item=FuelEntryService(FuelEntryRepository(s)).record(vehicle_id,date(2026,8,27),"42.34","100.00","1234.5")
        assert (item.litres,item.total_cost,item.odometer_km)==(Decimal("42.34"),Decimal("100.00"),Decimal("1234.5"))

@pytest.mark.parametrize("field,value",[("litres",0),("litres","NaN"),("litres","42.345"),("total_cost",-1),("total_cost","100.005"),("odometer_km",-1),("odometer_km","1.23")])
def test_rejects_invalid_values(field,value):
    db,vehicle_id=setup(); kwargs={"litres":"1","total_cost":None,"odometer_km":None}; kwargs[field]=value
    with session_scope(db) as s:
        with pytest.raises(FuelEntryValidationError): FuelEntryService(FuelEntryRepository(s)).record(vehicle_id,date.today(),**kwargs)

def test_rejects_timestamp_and_unknown_vehicle():
    db,vehicle_id=setup()
    with session_scope(db) as s:
        service=FuelEntryService(FuelEntryRepository(s))
        with pytest.raises(FuelEntryValidationError): service.record(vehicle_id,datetime.now(),1)
        with pytest.raises(FuelEntryValidationError): service.record(999,date.today(),1)
