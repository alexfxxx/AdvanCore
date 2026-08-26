import pytest
from sqlalchemy import create_engine
from advancore.models import Base
from advancore.repositories import DriverRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.driver_service import DriverService, DriverValidationError, DuplicateDriverReferenceError

def factory():
    engine = create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); return create_session_factory(engine)

def test_driver_create_list_status_and_minimal_fields():
    db = factory()
    with session_scope(db) as session:
        service = DriverService(DriverRepository(session)); driver = service.create_driver("  Alex  Tan ", " drv-1 "); identifier = driver.id
        assert (driver.name, driver.employee_reference, driver.status) == ("Alex Tan", "DRV-1", "active")
    with session_scope(db) as session:
        service = DriverService(DriverRepository(session)); assert service.set_status(identifier, "unavailable").status == "unavailable"; assert len(service.list_drivers()) == 1

def test_driver_rejects_invalid_duplicate_and_unknown_status():
    db = factory()
    with session_scope(db) as session:
        service = DriverService(DriverRepository(session))
        with pytest.raises(DriverValidationError): service.create_driver(" ")
        service.create_driver("Driver One", "REF-1")
        with pytest.raises(DuplicateDriverReferenceError): service.create_driver("Driver Two", "ref-1")
        with pytest.raises(DriverValidationError): service.set_status(1, "invented")
