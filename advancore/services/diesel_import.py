"""Local, deterministic diesel import with owner preview and atomic confirmation."""
import base64
import hashlib
import json
import re
from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from sqlalchemy import Table, Column, String, Date, Numeric, JSON, select
from advancore.models import Base, Vehicle, FuelEntry, FinancialEntry

rates_table = Table('diesel_rates', Base.metadata, Column('effective_on', Date, primary_key=True), Column('price', Numeric(8, 3), nullable=False))
imports_table = Table('diesel_transactions', Base.metadata, Column('transaction_id', String(80), primary_key=True), Column('record', JSON, nullable=False))
settings_table = Table('diesel_settings', Base.metadata, Column('key', String(80), primary_key=True), Column('value', JSON, nullable=False))

def product_key(label):
    return {'a diesel':'diesel','diesel':'diesel','adblue':'adblue'}.get(label.lower().strip())

def adblue_rates(session):
    return session.execute(select(settings_table.c.value).where(settings_table.c.key=='adblue_rates')).scalar_one_or_none() or {}

def effective_rate(rates,day):
    return next((Decimal(str(rates[d])) for d in sorted(rates,reverse=True) if str(d)<=day),None)

class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=[]; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag=='tr': self.row=[]
        if tag in ('td','th'): self.cell=''
    def handle_data(self, value):
        if self.cell is not None: self.cell+=value
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(self.cell.split())); self.cell=None
        if tag=='tr': self.rows.append(self.row)

def parse_report(encoded):
    raw=base64.b64decode(encoded,validate=True)
    if len(raw)>8_000_000: raise ValueError('Report exceeds 8 MB.')
    text=raw.decode('utf-8-sig')
    if '<table' not in text.lower(): raise ValueError('Use the supplier Transaction by Company - Vehicle HTML/Excel (.xls) export. Other workbook layouts are not supported yet.')
    parser=ReportParser(); parser.feed(text)
    if not any('Tran No.' in r and 'Vol (LTR)' in r for r in parser.rows): raise ValueError('Unrecognised supplier report headers.')
    plate=''; rows=[]; seen=set(); grand=None
    for r in parser.rows:
        if r and r[0]=='Grand Total': grand=(int(r[1].replace(',','')),Decimal(r[2].replace(',','')))
        if len(r)!=9 or not re.fullmatch(r'\d{2}/\d{2}/\d{4}',r[2]): continue
        if r[1]: plate=r[1].split(' (')[0].replace(' ','').upper()
        d,m,y=map(int,r[2].split('/')); day=date(y,m,d).isoformat()
        if not re.fullmatch(r'\d{2}:\d{2}:\d{2}',r[3]): raise ValueError('Invalid transaction time.')
        time.fromisoformat(r[3])
        litres=Decimal(r[8].replace(',',''))
        if not litres.is_finite() or litres<0 or litres!=litres.quantize(Decimal('.01')): raise ValueError('Invalid litres.')
        if not re.fullmatch(r'[A-Za-z0-9-]{1,60}',r[4]): raise ValueError('Invalid transaction number.')
        if r[4] in seen: raise ValueError('Repeated transaction number in this report: '+r[4])
        seen.add(r[4]);rows.append(dict(transaction=r[4],plate=plate,date=day,time=r[3],station=r[5],litres=str(litres),product=r[7]))
    if not rows or grand is None: raise ValueError('No transactions or supplier grand total found.')
    if grand!=(len(rows),sum(Decimal(r['litres']) for r in rows)): raise ValueError('Report transaction count or litres do not reconcile to its grand total.')
    return rows

def parse_rates(text):
    # Strip WhatsApp sending timestamps; only effective dates beside px are rates.
    clean=re.sub(r'\[[^\]\n]+\]', '', text)
    found={}
    for match in re.finditer(r'(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s+px\s*([0-9]+(?:\.[0-9]+)?)\s+(?:SFSD|FSD)\b',clean,re.I):
        d,m,y,p=match.groups(); year=int(y)+(2000 if len(y)==2 else 0)
        day=date(year,int(m),int(d)); price=Decimal(p)
        if price<=0 or price>=100 or price!=price.quantize(Decimal('.001')): raise ValueError('Invalid diesel price.')
        if day in found and found[day]!=price: raise ValueError('Conflicting rates for '+str(day))
        found[day]=price
    if len(re.findall(r'\bpx\s*',clean,re.I))!=len(list(re.finditer(r'\d{1,2}/\d{1,2}/(?:\d{2}|\d{4})\s+px\s*[0-9]+(?:\.[0-9]+)?\s+(?:SFSD|FSD)\b',clean,re.I))):
        raise ValueError('A rate line has an unreadable date or price. Correct typos (for example /6 to /2026) before previewing.')
    if text.strip() and not found: raise ValueError('No dated px rates found. Paste effective date, px price and SFSD.')
    return found

def preview(session, rows, proposed):
    blue=adblue_rates(session)
    stored=dict(session.execute(select(rates_table.c.effective_on,rates_table.c.price)).all())
    rates={**stored,**proposed}; policy=session.execute(select(settings_table.c.value).where(settings_table.c.key=='policy')).scalar_one_or_none()
    if not policy or not isinstance(policy.get('excluded_vehicles'),list):
        raise ValueError('An owner-approved local fuel policy must be configured before importing.')
    excluded=set(policy['excluded_vehicles']); fleet={v.registration_number:v.id for v in session.scalars(select(Vehicle)).all()}
    old=dict(session.execute(select(imports_table.c.transaction_id,imports_table.c.record)).all())
    result=dict(new=[],duplicates=[],excluded=[],zero=[],corrections=[],issues=[],rate_changes=[],other_products=[])
    for d,p in proposed.items():
        if stored.get(d)!=p: result['rate_changes'].append(dict(date=str(d),previous=str(stored[d]) if d in stored else None,proposed=str(p)))
    def price_on(day,product='A Diesel'):
        kind=product_key(product)
        return effective_rate(blue,day) if kind=='adblue' else effective_rate(rates,day) if kind=='diesel' else None
    for transaction,record in old.items():
        if record.get('excluded') or Decimal(record['litres'])==0:continue
        if product_key(record.get('product','A Diesel')) is None:
            result['corrections'].append(dict(transaction=transaction,plate=record['plate'],date=record['date'],previous=record['cost'],proposed='Needs '+record['product']+' rate; previously priced as diesel'))
            continue
        rate=price_on(record['date'],record.get('product','A Diesel'))
        if rate is not None and rate!=Decimal(record['rate']):
            cost=(Decimal(record['litres'])*rate).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            result['corrections'].append(dict(transaction=transaction,plate=record['plate'],date=record['date'],previous=record['cost'],proposed=str(cost)))
    for r in rows:
        if product_key(r.get('product','A Diesel')) is None:
            result['other_products'].append(r)
            if r['transaction'] in old: result['duplicates'].append(r)
            else: result['issues'].append('Non-diesel product needs separate pricing: '+r['product'])
            continue
        rate=price_on(r['date'],r.get('product','A Diesel')); row=dict(r)
        if rate is None:
            result['issues'].append('Missing '+r.get('product','diesel')+' rate on '+r['date']);result['other_products'].append(r);continue
        row.update(rate=str(rate),cost=str((Decimal(r['litres'])*rate).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)))
        if r['transaction'] in old:
            if any(str(old[r['transaction']].get(k))!=str(r[k]) for k in ('plate','date','time','litres','station')): result['issues'].append('Previously imported transaction changed: '+r['transaction'])
            if product_key(old[r['transaction']].get('product','A Diesel'))!=product_key(r.get('product','A Diesel')):result['issues'].append('Previously imported product changed: '+r['transaction'])
            result['duplicates'].append(row);continue
        if r['plate'] in excluded:row['excluded']=True;result['excluded'].append(row);continue
        if r['plate'] not in fleet:result['issues'].append('Unknown vehicle '+r['plate']);continue
        row['vehicle_id']=fleet[r['plate']]
        if Decimal(r['litres'])==0:result['zero'].append(row)
        else:result['new'].append(row)
    totals={}
    for r in result['new']:
        month=r['date'][:7];totals[month]=totals.get(month,Decimal(0))+Decimal(r['cost'])
    result['monthly_costs']={m:str(v) for m,v in sorted(totals.items())}; result['issues']=sorted(set(result['issues']))
    result['can_confirm']=not result['issues'] and not result['corrections']
    result['fingerprint']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return result

def commit(session, result, proposed):
    if not result['can_confirm']:raise ValueError('Resolve questions or rate corrections before importing.')
    for d,p in proposed.items():
        exists=session.execute(select(rates_table.c.effective_on).where(rates_table.c.effective_on==d)).first()
        if exists:session.execute(rates_table.update().where(rates_table.c.effective_on==d).values(price=p))
        else:session.execute(rates_table.insert().values(effective_on=d,price=p))
    for r in result['new']:
        day=date.fromisoformat(r['date']);key='SFSD:'+r['transaction']
        product=product_key(r.get('product','A Diesel'))
        fuel=FuelEntry(vehicle_id=r['vehicle_id'],recorded_on=day,litres=Decimal(r['litres']),total_cost=Decimal(r['cost']),product=product)
        finance=FinancialEntry(vehicle_id=r['vehicle_id'],entry_date=day,accounting_month=day.replace(day=1),entry_type='expense',category='adblue' if product=='adblue' else 'fuel',amount=Decimal(r['cost']),currency_code='SGD',payment_status='unpaid',description=f'{key}; {r["plate"]}; {product} excl GST; payment unconfirmed')
        session.add_all([fuel,finance]);session.flush()
        session.execute(imports_table.insert().values(transaction_id=r['transaction'],record=dict(r,fuel_id=fuel.id,financial_id=finance.id)))
    for r in result['excluded']+result['zero']:
        session.execute(imports_table.insert().values(transaction_id=r['transaction'],record=r))
