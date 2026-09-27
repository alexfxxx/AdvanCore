"""Preview-first deterministic local assistant. No cloud or arbitrary execution."""
import secrets
import time
from decimal import InvalidOperation
from threading import Lock
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import text,select
from advancore.api.routes.orchestration import require_local_action,require_confirmation
from advancore.services.database import session_scope
from advancore.services.diesel_import import parse_report,parse_rates,preview,commit,settings_table
from advancore.services.consumption_review import review
from advancore.services.diesel_import import adblue_rates, imports_table, effective_rate, product_key
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

router=APIRouter(prefix='/api/diesel-import',dependencies=[Depends(require_local_action)])
drafts={}
lock=Lock()
class ConsumptionRequest(BaseModel):
    month:str=Field(pattern=r'^\d{4}-\d{2}$')
@router.post('/consumption')
def consumption(payload:ConsumptionRequest):
    try:
        with session_scope() as session:return review(session,payload.month)
    except ValueError:raise HTTPException(400,'Choose a valid month.')

class AdblueRate(BaseModel):
    effective_on:date
    price:Decimal=Field(gt=0,lt=100,max_digits=5,decimal_places=3)
    confirmed:bool=False
    expected_rates:dict[str,str]=Field(default_factory=dict)
@router.post('/adblue-rate')
def adblue_rate(payload:AdblueRate):
    with lock, session_scope() as session:
        if session.bind.dialect.name=='postgresql':session.execute(text('SELECT pg_advisory_xact_lock(216923)'))
        old=adblue_rates(session);new={**old,payload.effective_on.isoformat():str(payload.price)}
        corrections=[]
        for r in session.execute(select(imports_table.c.record)).scalars():
            if r.get('excluded') or product_key(r.get('product','A Diesel'))!='adblue' or Decimal(r['litres'])==0:continue
            rate=effective_rate(new,r['date'])
            if rate is not None and rate!=Decimal(r['rate']):
                corrections.append(dict(transaction=r['transaction'],vehicle=r['plate'],date=r['date'],previous=r['cost'],proposed=str((Decimal(r['litres'])*rate).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))))
        if payload.confirmed:
            if old!=payload.expected_rates:raise HTTPException(409,'Rates changed. Preview again.')
            if corrections:raise HTTPException(409,'Historical corrections require separate reconciliation; no changes saved. Choose a date after approved purchases for future prices.')
            if old:session.execute(settings_table.update().where(settings_table.c.key=='adblue_rates').values(value=new))
            else:session.execute(settings_table.insert().values(key='adblue_rates',value=new))
        return dict(previous_rates=old,rates=new,corrections=corrections,saved=payload.confirmed,can_confirm=not corrections)
@router.post('/status')
def import_status():
    with session_scope() as session:
        return session.execute(select(settings_table.c.value).where(settings_table.c.key=='review_issue')).scalar_one_or_none() or {}
class Upload(BaseModel):
    model_config=ConfigDict(extra='forbid')
    report_base64:str=Field(max_length=11_000_000)
    rates_text:str=Field(default='',max_length=100_000)
class Confirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(max_length=100)
    confirmed:bool
@router.post('/preview')
def make_preview(payload:Upload):
    try:
        rows=parse_report(payload.report_base64);rates=parse_rates(payload.rates_text)
        with session_scope() as session:result=preview(session,rows,rates)
    except (ValueError,UnicodeError,InvalidOperation) as e:raise HTTPException(400,'Report validation failed: '+str(e))
    with lock:
        for key in list(drafts):
            if drafts[key][0]<time.time()-1800:del drafts[key]
        if len(drafts)>=20:raise HTTPException(429,'Too many previews. Retry after older previews expire.')
        token=secrets.token_urlsafe(24);drafts[token]=(time.time(),rows,rates,result['fingerprint'])
    return dict(result,token=token)
@router.post('/confirm')
def confirm_import(payload:Confirm):
    require_confirmation(payload.confirmed)
    with lock:
        draft=drafts.get(payload.token)
        if not draft or draft[0]<time.time()-1800:raise HTTPException(409,'Preview expired. Preview again.')
        with session_scope() as session:
            if session.bind.dialect.name=='postgresql':session.execute(text('SELECT pg_advisory_xact_lock(216923)'))
            result=preview(session,draft[1],draft[2])
            if result['fingerprint']!=draft[3]:raise HTTPException(409,'Records changed. Preview again before confirming.')
            if not result['can_confirm']:raise HTTPException(409,'Questions or corrections need review; nothing saved.')
            commit(session,result,draft[2])
        del drafts[payload.token]
    return dict(imported=len(result['new']),excluded=len(result['excluded']),zero=len(result['zero']),monthly_costs=result['monthly_costs'])
