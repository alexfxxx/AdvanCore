"""Local owner credential entry; no secret read API or external login side effects."""
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import JSONResponse
from advancore.api.routes.orchestration import require_local_action
from advancore.services.supplier_keychain import SupplierKeychain, VaultUnavailable

router=APIRouter(prefix='/api/supplier-credentials/santa',dependencies=[Depends(require_local_action)])

def reply(data):
    return JSONResponse(data,headers={'Cache-Control':'no-store','Pragma':'no-cache'})

def vault():
    try:return SupplierKeychain()
    except Exception:raise HTTPException(503,'macOS Keychain is unavailable.') from None

async def payload(request):
    # Avoid Pydantic validation errors echoing submitted secret input.
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>16384:raise HTTPException(413,'Credential request too large.')
    try:
        import json
        value=json.loads(body)
    except Exception:raise HTTPException(400,'Invalid credential request.') from None
    finally:body[:]=b'\0'*len(body)
    if not isinstance(value,dict) or value.get('confirmed') is not True:
        raise HTTPException(400,'Explicit confirmation is required.')
    return value

@router.post('/status')
def status():
    try:return reply({'saved':vault().exists(),'storage':'macOS Keychain','login_verified':False,'scheduled':False})
    except VaultUnavailable:raise HTTPException(503,'Keychain access unavailable; unlock your login Keychain.') from None

@router.post('/save')
async def save(request:Request):
    data=await payload(request)
    username=data.get('username');password=data.get('password')
    if set(data)!={'username','password','confirmed'} or not isinstance(username,str) or not isinstance(password,str) or not username.strip() or not password or len(username)>256 or len(password)>4096 or '\0' in username or '\0' in password:
        raise HTTPException(400,'Enter a valid Login ID and password.')
    try:vault().save(username.strip(),password)
    except VaultUnavailable:raise HTTPException(503,'Credentials were not saved. Check macOS Keychain access.') from None
    return reply({'saved':True,'login_verified':False,'scheduled':False})

@router.post('/remove')
async def remove(request:Request):
    data=await payload(request)
    if set(data)!={'confirmed'}:raise HTTPException(400,'Invalid removal request.')
    try:vault().remove()
    except VaultUnavailable:raise HTTPException(503,'Could not remove credentials. Check Keychain access.') from None
    return reply({'saved':False})
