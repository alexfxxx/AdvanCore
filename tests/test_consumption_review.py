from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from advancore.models import Base,Vehicle,FuelEntry
from advancore.services.diesel_import import settings_table,preview,commit
from advancore.services.consumption_review import review

def test_separate_adblue_and_missing_bus_not_car():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as s:
        bus=Vehicle(registration_number='BUS',status='active',vehicle_type='Bus')
        s.add_all([bus,Vehicle(registration_number='MISSING',status='active',vehicle_type='Bus'),Vehicle(registration_number='CAR',status='active',vehicle_type='car')]);s.flush()
        s.execute(settings_table.insert().values(key='policy',value={'excluded_vehicles':[]}))
        s.execute(settings_table.insert().values(key='adblue_rates',value={'2026-08-01':'1.250'}))
        row=dict(transaction='BLUE1',plate='BUS',date='2026-09-20',time='12:00:00',station='A',litres='10.00',product='Adblue')
        p=preview(s,[row],{});assert p['new'][0]['cost']=='12.50';commit(s,p,{})
        for day in (1,5,10):s.add(FuelEntry(vehicle_id=bus.id,recorded_on=date(2026,8,day),litres=100,total_cost=200,product='diesel'))
        s.add(FuelEntry(vehicle_id=bus.id,recorded_on=date(2026,9,20),litres=600,total_cost=1200,product='diesel'));s.flush()
        result=review(s,'2026-09')
        assert {r['product'] for r in result['rows']}=={'diesel','adblue'}
        assert any(r['vehicle']=='MISSING' for r in result['alerts'])
        assert not any(r['vehicle']=='CAR' for r in result['alerts'])
        assert any(r['type']=='Usage spike' and '+100%' in r['detail'] for r in result['alerts'])
        assert not review(s,'2026-10')['alerts']
