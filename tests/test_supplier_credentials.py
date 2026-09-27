from fastapi import FastAPI
from fastapi.testclient import TestClient
from advancore.api.routes import supplier_credentials as routes
from advancore.services.supplier_keychain import VaultUnavailable

class FakeVault:
    value=None
    def exists(self):return self.value is not None
    def save(self,u,p):self.value=(u,p)
    def remove(self):self.value=None

def test_local_credential_lifecycle_and_redaction(monkeypatch):
    fake=FakeVault();monkeypatch.setattr(routes,'SupplierKeychain',lambda:fake)
    app=FastAPI();app.state.action_token='test-token';app.state.allowed_origins={'http://127.0.0.1:8000'};app.include_router(routes.router)
    client=TestClient(app,client=('127.0.0.1',12345))
    headers={'Origin':'http://127.0.0.1:8000','X-AdvanCore-Action-Token':'test-token'}
    url='/api/supplier-credentials/santa/'
    secret='synthetic-only-secret'
    data={'username':'test-user','password':secret,'confirmed':True}
    assert client.post(url+'save',json=data).status_code==403
    assert client.post(url+'save',json=data,headers={**headers,'Origin':'https://evil.invalid'}).status_code==403
    for bad in ({**data,'confirmed':False},{**data,'username':[]},{**data,'extra':secret}):
        response=client.post(url+'save',json=bad,headers=headers)
        assert response.status_code==400 and secret not in response.text
    response=client.post(url+'save',json=data,headers=headers)
    assert response.status_code==200 and secret not in response.text and response.headers['cache-control']=='no-store'
    assert fake.value==('test-user',secret)
    assert client.post(url+'status',json={},headers=headers).json()['saved']
    assert client.get(url+'save',headers=headers).status_code==405
    assert client.post(url+'save',content='x'*17000,headers=headers).status_code==413
    assert client.post(url+'remove',json={'confirmed':True},headers=headers).json()=={'saved':False}
    assert fake.value is None

def test_keychain_failure_does_not_echo_secret(monkeypatch):
    class Broken(FakeVault):
        def save(self,u,p):raise VaultUnavailable(p)
    monkeypatch.setattr(routes,'SupplierKeychain',Broken)
    app=FastAPI();app.state.action_token='token';app.state.allowed_origins={'http://127.0.0.1:8000'};app.include_router(routes.router)
    c=TestClient(app,client=('127.0.0.1',12345))
    r=c.post('/api/supplier-credentials/santa/save',headers={'Origin':'http://127.0.0.1:8000','X-AdvanCore-Action-Token':'token'},json={'username':'dummy','password':'secret-test','confirmed':True})
    assert r.status_code==503 and 'secret-test' not in r.text
