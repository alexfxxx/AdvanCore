from datetime import date, datetime
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from advancore.models import Base, Customer, FinancialEntry, Route, Trip
from advancore.repositories import FinancialEntryRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.financial_entry_service import FinancialEntryService, FinancialEntryValidationError

def setup():
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); db=create_session_factory(engine)
    with session_scope(db) as s:
        customer=Customer(name="Customer"); route=Route(route_code="R",origin="A",destination="B"); s.add_all([customer,route]); s.flush(); trip=Trip(trip_reference="T",route_id=route.id,service_date=date(2026,8,27)); s.add(trip); s.flush(); ids=(trip.id,customer.id)
    return db,ids

def test_records_exact_denomination_and_real_links():
    db,(trip_id,customer_id)=setup()
    with session_scope(db) as s:
        item=FinancialEntryService(FinancialEntryRepository(s)).record(date(2026,8,27),"income","125.50","sgd"," Real job ",trip_id,customer_id)
        assert (item.amount,item.currency_code,item.description)==(Decimal("125.50"),"SGD","Real job")

@pytest.mark.parametrize("amount",[0,-1,"1.001","NaN"])
def test_rejects_invalid_amount(amount):
    db,_=setup()
    with session_scope(db) as s:
        with pytest.raises(FinancialEntryValidationError): FinancialEntryService(FinancialEntryRepository(s)).record(date.today(),"expense",amount,"SGD")

def test_rejects_timestamp_currency_and_unknown_links():
    db,_=setup()
    with session_scope(db) as s:
        service=FinancialEntryService(FinancialEntryRepository(s))
        with pytest.raises(FinancialEntryValidationError): service.record(datetime.now(),"income",1,"SGD")
        with pytest.raises(FinancialEntryValidationError): service.record(date.today(),"income",1,"S$")
        with pytest.raises(FinancialEntryValidationError): service.record(date.today(),"income",1,"ſgd")
        with pytest.raises(FinancialEntryValidationError): service.record(date.today(),"income",1,"ﬃ")
        with pytest.raises(FinancialEntryValidationError): service.record(date.today(),"income",1,"SGD",trip_id=999)

def test_database_constraint_rejects_non_letter_currency_code():
    db,_=setup()
    with pytest.raises(IntegrityError):
        with session_scope(db) as s:
            s.add(FinancialEntry(entry_date=date.today(),entry_type="income",amount=Decimal("1.00"),currency_code="S$1"))
