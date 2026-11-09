"""Plaid contract tests are fully mocked: CI never needs bank credentials."""

from datetime import date, timedelta

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import database, plaid
from app.main import create_app


def test_plaid_requires_credentials(tmp_path,monkeypatch):
    monkeypatch.delenv('PLAID_CLIENT_ID',raising=False)
    monkeypatch.delenv('PLAID_SECRET',raising=False)
    monkeypatch.delenv('PLAID_TOKEN_ENCRYPTION_KEY',raising=False)
    with TestClient(create_app(tmp_path/'db.sqlite3',auth_mode='off',seed_demo=False)) as client:
        assert client.get('/api/v3/plaid/status').json()['configured'] is False
        assert client.post('/api/v3/plaid/link-token').status_code==503


def test_plaid_link_encrypt_sync_review_and_repeat(tmp_path,monkeypatch):
    monkeypatch.setenv('PLAID_CLIENT_ID','id-for-test')
    monkeypatch.setenv('PLAID_SECRET','secret-for-test')
    monkeypatch.setenv('PLAID_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('PLAID_ENV','sandbox')
    calls=[]
    today=date.today().isoformat()

    def provider(path,payload):
        calls.append(path)
        if path=='/link/token/create':
            assert payload['products']==['transactions']
            return {'link_token':'link-sandbox-test'}
        if path=='/item/public_token/exchange':
            return {'access_token':'access-sandbox-secret','item_id':'item-uuid'}
        if path=='/transactions/sync':
            assert payload['access_token']=='access-sandbox-secret'
            if payload['cursor']=='cursor-first':
                return {'added':[],'modified':[],'removed':[],'next_cursor':'cursor-next','has_more':False}
            return {'added':[
                {'transaction_id':'txn-deposit','date':today,'name':'Client payment INV-1','amount':-125,
                 'iso_currency_code':'USD','pending':False},
                {'transaction_id':'txn-expense','date':today,'name':'Office supplies','amount':33.17,
                 'iso_currency_code':'USD','pending':False},
                {'transaction_id':'txn-pending','date':today,'name':'Pending','amount':15,
                 'iso_currency_code':'USD','pending':True}],
                'modified':[],'removed':[],'next_cursor':'cursor-first','has_more':False}
        raise AssertionError(path)

    monkeypatch.setattr(plaid,'_post',provider)
    path=tmp_path/'db.sqlite3'
    with TestClient(create_app(path,auth_mode='off',seed_demo=False)) as client:
        issue=client.post('/api/invoices',json={
            'invoice_number':'INV-1','customer':'Client','amount':'125.00',
            'issued_on':(date.today()-timedelta(days=40)).isoformat(),
            'due_on':(date.today()-timedelta(days=10)).isoformat()})
        assert issue.status_code==201
        token=client.post('/api/v3/plaid/link-token').json()['link_token']
        assert token=='link-sandbox-test'
        linked=client.post('/api/v3/plaid/exchange',json={'public_token':'public-sandbox'}).json()
        assert linked['id']
        assert 'access_token' not in str(linked)
        with database.connect(path) as con:
            ciphertext=con.execute('SELECT access_token_ciphertext FROM plaid_links').fetchone()[0]
            assert 'access-sandbox-secret' not in ciphertext
        synced=client.post(f"/api/v3/plaid/{linked['id']}/sync")
        assert synced.status_code==200,synced.text
        assert synced.json()['new']==2
        transactions=client.get('/api/v3/bank-transactions').json()['items']
        assert len(transactions)==2
        assert sorted(r['signed_amount_cents'] for r in transactions)==[-3317,12500]
        repeated=client.post(f"/api/v3/plaid/{linked['id']}/sync").json()
        assert repeated['new']==0
        deposit=next(r for r in transactions if r['signed_amount_cents']==12500)
        matched=client.post(f"/api/v3/bank-transactions/{deposit['id']}/review",json={
            'action':'reconcile','invoice_id':issue.json()['id']})
        assert matched.status_code==200,matched.text
        assert client.get('/api/dashboard').json()['summary']['outstanding_cents']==0
        assert calls.count('/transactions/sync')==2


def test_anonymous_demo_cannot_link_banks(tmp_path,monkeypatch):
    monkeypatch.setenv('PLAID_CLIENT_ID','id')
    monkeypatch.setenv('PLAID_SECRET','secret')
    monkeypatch.setenv('PLAID_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    app=create_app(tmp_path/'demo.sqlite3',seed_demo=False,auth_mode='demo',
                   auth_db_path=tmp_path/'accounts.sqlite3',workspace_root=tmp_path/'workspaces')
    with TestClient(app) as client:
        assert client.post('/api/v3/plaid/link-token').status_code==401
