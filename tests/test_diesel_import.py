import base64
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from advancore.services.diesel_import import parse_rates,parse_report,preview,commit,rates_table,imports_table,settings_table
from advancore.models import Base,Vehicle,LegalEntity

def test_rates_and_ambiguity():
    assert parse_rates('[23/9/26, 19:00] Sender: 24/09/26 px 2.040 SFSD')=={date(2026,9,24):Decimal('2.040')}
    with pytest.raises(ValueError):parse_rates('14/09/6 px 2.16 SFSD')
    with pytest.raises(ValueError):parse_rates('24/09/26 px 2.04 SFSD\n24/09/26 px 2.05 SFSD')

def test_fresh_database_requires_approved_policy():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(ValueError,match='owner-approved'):
            preview(session,[],{})

def test_report_reconciliation():
    text='<table><tr><td>Tran No.</td><td>Vol (LTR)</td></tr><tr>'+''.join('<td>'+x+'</td>' for x in ['Company','BUS1 (12)','24/09/2026','12:00:00','123','Station','1','A Diesel','10.00'])+'</tr><tr><td>Grand Total</td><td>1</td><td>10.00</td></tr></table>'
    assert parse_report(base64.b64encode(text.encode()).decode())[0]['litres']=='10.00'
    with pytest.raises(ValueError):parse_report(base64.b64encode(text.replace('<td>1</td><td>10.00</td></tr></table>','<td>2</td><td>10.00</td></tr></table>').encode()).decode())

def test_preview_exclusion_duplicate_correction_and_commit():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as s:
        owner=LegalEntity(name='Test owner');s.add(owner);s.flush()
        vehicle=Vehicle(registration_number='BUS1',registered_owner_id=owner.id,status='active');s.add(vehicle);s.flush()
        s.execute(settings_table.insert().values(key='policy',value={'excluded_vehicles':['OTHER']}))
        s.execute(rates_table.insert().values(effective_on=date(2026,9,1),price=Decimal('2')))
        row=dict(transaction='123',plate='BUS1',date='2026-09-24',time='12:00:00',station='A',litres='10.00')
        result=preview(s,[row,dict(row,transaction='124',plate='OTHER')],{})
        assert result['monthly_costs']=={'2026-09':'20.00'} and len(result['excluded'])==1
        commit(s,result,{})
        repeat=preview(s,[row],{});assert len(repeat['duplicates'])==1 and not repeat['new']
        correction=preview(s,[row],{date(2026,9,1):Decimal('3')})
        assert not correction['can_confirm'] and correction['corrections'][0]['proposed']=='30.00'
        with pytest.raises(ValueError):commit(s,correction,{})
        assert preview(s,[dict(row,transaction='125',plate='UNKNOWN')],{})['issues']
        other=preview(s,[dict(row,transaction='126',product='Adblue')],{})
        assert not other['new'] and other['issues'] and len(other['other_products'])==1
        changed=preview(s,[dict(row,litres='11.00')],{})
        assert not changed['can_confirm'] and changed['issues']
        before=preview(s,[dict(row,transaction='127')],{})
        commit(s,before,{})
        after=preview(s,[dict(row,transaction='127')],{})
        assert before['fingerprint']!=after['fingerprint']
