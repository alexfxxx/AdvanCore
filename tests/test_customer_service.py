import pytest
from sqlalchemy import create_engine
from advancore.models import Base
from advancore.repositories import CustomerRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.customer_service import CustomerService, CustomerValidationError, DuplicateCustomerReferenceError
def factory():
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); return create_session_factory(engine)
def test_customer_create_list_and_status():
    db=factory()
    with session_scope(db) as session:
        service=CustomerService(CustomerRepository(session)); item=service.create_customer("  Acme  Transport ", " c-1 "); identifier=item.id; assert (item.name,item.customer_reference)==("Acme Transport","C-1")
    with session_scope(db) as session:
        service=CustomerService(CustomerRepository(session)); assert service.set_status(identifier,"inactive").status=="inactive"; assert len(service.list_customers())==1
def test_customer_rejects_blank_duplicate_and_unknown_status():
    db=factory()
    with session_scope(db) as session:
        service=CustomerService(CustomerRepository(session))
        with pytest.raises(CustomerValidationError): service.create_customer(" ")
        service.create_customer("One","REF")
        with pytest.raises(DuplicateCustomerReferenceError): service.create_customer("Two","ref")
        with pytest.raises(CustomerValidationError): service.set_status(1,"unknown")
