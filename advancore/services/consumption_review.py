"""Read-only consumption checks; flags are questions, not findings of misuse."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from advancore.models import Vehicle, FuelEntry
from advancore.services.diesel_import import imports_table, settings_table, adblue_rates

def review(session, month):
    first=date.fromisoformat(month+'-01')
    fleet={v.id:v for v in session.scalars(select(Vehicle))}
    facts=list(session.scalars(select(FuelEntry)))
    selected=[r for r in facts if r.recorded_on.strftime('%Y-%m')==month]
    last=max((r.recorded_on.day for r in selected),default=0)
    previous=(first.replace(year=first.year-1,month=12) if first.month==1 else first.replace(month=first.month-1)).strftime('%Y-%m')
    cutoff=min(last,monthrange(int(previous[:4]),int(previous[5:]))[1])
    totals=defaultdict(lambda: {'litres':Decimal(0),'cost':Decimal(0),'count':0,'unknown':False})
    for r in selected:
        t=totals[(r.vehicle_id,r.product)];t['litres']+=r.litres;t['count']+=1
        if r.total_cost is None:t['unknown']=True
        else:t['cost']+=r.total_cost
    rows=[]
    for (vid,product),t in sorted(totals.items()):
        rows.append(dict(vehicle=fleet[vid].registration_number,product=product,litres=str(t['litres']),cost=None if t['unknown'] else str(t['cost']),rate=None if t['unknown'] or not t['litres'] else str(round(t['cost']/t['litres'],3)),count=t['count']))
    policy=session.execute(select(settings_table.c.value).where(settings_table.c.key=='policy')).scalar_one_or_none() or {}
    excluded=set(policy.get('excluded_vehicles',[]));alerts=[]
    if selected:
        for vid,v in fleet.items():
            if v.status!='active' or v.vehicle_type in ('car','lorry') or v.registration_number in excluded:continue
            current=[r for r in selected if r.vehicle_id==vid and r.product=='diesel' and r.litres>0]
            if not current:alerts.append(dict(vehicle=v.registration_number,type='No diesel record',detail='No supplier diesel record this month. Check standby, another supplier, or fleet start date.'))
            baseline=[r for r in facts if r.vehicle_id==vid and r.product=='diesel' and r.recorded_on.strftime('%Y-%m')==previous and r.recorded_on.day<=cutoff and r.litres>0]
            now=sum((r.litres for r in current if r.recorded_on.day<=cutoff),Decimal(0));old=sum((r.litres for r in baseline),Decimal(0))
            if len(baseline)>=3 and old and current:
                change=(now-old)/old*100
                if abs(change)>=50:alerts.append(dict(vehicle=v.registration_number,type='Usage spike' if change>0 else 'Usage drop',detail=f'{change:+.0f}% litres: {now} vs {old}; days 1–{cutoff} compared with {previous}. Screening threshold 50%, not proof of a problem.'))
    extra=[];plates={v.registration_number for v in fleet.values()}
    for r in session.execute(select(imports_table.c.record)).scalars():
        if r['date'].startswith(month) and (r['plate'] not in plates or r['plate'] in excluded):
            extra.append(dict(vehicle=r['plate'],date=r['date'],time=r['time'],litres=r['litres'],cost=r.get('cost'),status='Approved exclusion' if r['plate'] in excluded else 'Not in Fleet'))
    return dict(month=month,through_day=last,rows=rows,alerts=alerts,extra=extra,adblue_rates=adblue_rates(session),months=sorted({r.recorded_on.strftime('%Y-%m') for r in facts},reverse=True))
