"""Real bank/accounting file ingestion and human-approved reconciliation."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.banking import parse_import
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path/'bank.db',seed_demo=False,auth_mode='off'))


def invoice(number='INV-BANK'):
    today=date.today()
    return {'invoice_number':number,'customer':'Blue Sky Labs','amount':'100.00',
            'issued_on':(today-timedelta(days=40)).isoformat(),
            'due_on':(today-timedelta(days=10)).isoformat()}


def bank_csv(reference='INV-BANK', amount='100.00'):
    return f'Date,Description,Amount,Reference,Currency\n{date.today().isoformat()},Payment for {reference},{amount},TX-123,USD\n'


def test_bank_import_is_staged_idempotent_and_can_reconcile(client):
    row=client.post('/api/invoices',json=invoice()).json()
    body=bank_csv()
    imported=client.post('/api/v3/import/bank_csv',content=body,headers={'Content-Type':'text/csv'})
    assert imported.status_code==200,imported.text
    assert imported.json()['imported']==1
    again=client.post('/api/v3/import/bank_csv',content=body,headers={'Content-Type':'text/csv'}).json()
    assert again['imported']==0 and again['duplicates']==1
    # Staging never changes the invoice or cash balance.
    assert client.get('/api/dashboard').json()['summary']['outstanding_cents']==10000
    txn=client.get('/api/v3/bank-transactions').json()['items'][0]
    suggestion=client.get(f"/api/v3/bank-transactions/{txn['id']}/suggestions").json()['matches'][0]
    assert suggestion['invoice_id']==row['id']
    assert suggestion['confidence_pct']>=90
    reconciled=client.post(f"/api/v3/bank-transactions/{txn['id']}/review",
                           json={'action':'reconcile','invoice_id':row['id']})
    assert reconciled.status_code==200,reconciled.text
    assert reconciled.json()['status']=='matched'
    assert client.get('/api/dashboard').json()['summary']['outstanding_cents']==0
    assert client.get('/api/dashboard').json()['summary']['paid_cents']==10000
    assert client.get('/api/v2/cash').json()['items'][0]['amount_cents']==10000
    assert client.post(f"/api/v3/bank-transactions/{txn['id']}/review",json={'action':'ignore'}).status_code==422


def test_partial_payment_lifecycle(client):
    row=client.post('/api/invoices',json=invoice('INV-PART')).json()
    first=client.post(f"/api/v3/invoices/{row['id']}/payments",json={'amount':'40.01','paid_on':date.today().isoformat(),'reference':'manual'})
    assert first.status_code==201,first.text
    assert first.json()['remaining_cents']==5999
    assert client.get('/api/dashboard').json()['summary']['outstanding_cents']==5999
    assert client.get('/api/dashboard').json()['summary']['paid_cents']==4001
    assert client.post(f"/api/v3/invoices/{row['id']}/payments",json={'amount':'60.00','paid_on':date.today().isoformat()}).status_code==422
    last=client.post(f"/api/v3/invoices/{row['id']}/payments",json={'amount':'59.99','paid_on':date.today().isoformat()})
    assert last.status_code==201
    assert client.get('/api/dashboard').json()['summary']['outstanding_cents']==0
    assert len(client.get(f"/api/v3/invoices/{row['id']}/payments").json()['payments'])==2
    assert client.delete(f"/api/v3/payments/{first.json()['id']}").status_code==204
    assert client.get('/api/dashboard').json()['summary']['outstanding_cents']==4001


def test_quickbooks_xero_qif_ofx_and_camt_formats():
    qbo='Date,Description,Amount,Type,Reference\n2026-11-01,Office rent,250,Expense,RENT-1\n'
    assert parse_import('quickbooks_csv',qbo.encode())[0]['signed_amount_cents']==-25000
    xero='Date,Description,Amount,Reference\n2026-11-01,Subscription,-19.99,XERO-1\n'
    assert parse_import('xero_csv',xero.encode())[0]['signed_amount_cents']==-1999
    qif='!Type:Bank\nD11/01/2026\nT-54.20\nPCoffee Store\nNABC\n^\n'
    assert parse_import('qif',qif.encode())[0]['signed_amount_cents']==-5420
    ofx='<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20261101000000<TRNAMT>82.50<FITID>AB1<NAME>Example customer</STMTTRN>'
    assert parse_import('ofx',ofx.encode())[0]['signed_amount_cents']==8250
    camt='''<Document><BkToCstmrStmt><Stmt><Ntry><Amt Ccy="USD">12.34</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-11-01</Dt></BookgDt><NtryRef>REF1</NtryRef><AddtlNtryInf>Invoice</AddtlNtryInf></Ntry></Stmt></BkToCstmrStmt></Document>'''
    assert parse_import('camt053',camt.encode())[0]['signed_amount_cents']==-1234
    with pytest.raises(ValueError,match='DTD'):
        parse_import('camt053',b'<!DOCTYPE foo [<!ENTITY x "y">]><Document/>')


def test_expense_post_and_ignored_transaction(client):
    body=bank_csv('OFFICE','-35.50')
    client.post('/api/v3/import/bank_csv',content=body)
    txn=client.get('/api/v3/bank-transactions').json()['items'][0]
    posted=client.post(f"/api/v3/bank-transactions/{txn['id']}/review",json={'action':'post'})
    assert posted.status_code==200
    assert client.get('/api/v2/cash').json()['items'][0]['kind']=='expense'
    second=bank_csv('OTHER','50.00').replace('TX-123','TX-456')
    client.post('/api/v3/import/bank_csv',content=second)
    pending=[t for t in client.get('/api/v3/bank-transactions').json()['items'] if t['status']=='unreviewed'][0]
    assert client.post(f"/api/v3/bank-transactions/{pending['id']}/review",json={'action':'ignore'}).json()['status']=='ignored'
    assert client.get('/api/v3/bank-transactions?status=unreviewed').json()['items']==[]

