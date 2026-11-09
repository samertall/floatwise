"""Security boundaries: authentication, CSRF and per-account database isolation."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.security import check_password, encode_password


def create_clients(tmp_path, mode='demo'):
    app=create_app(tmp_path/'synthetic-demo.sqlite3',seed_demo=False,auth_mode=mode,
                   auth_db_path=tmp_path/'accounts.sqlite3',workspace_root=tmp_path/'workspaces')
    return TestClient(app),TestClient(app)


def new_invoice(number):
    today=date.today()
    return {'invoice_number':number,'customer':'Private Acme','amount':'120.00',
            'issued_on':today.isoformat(),'due_on':(today+timedelta(days=15)).isoformat()}


def test_scrypt_hashing_and_bad_password():
    encoded=encode_password('A-very-long-secret-2026')
    assert 'A-very-long-secret-2026' not in encoded
    assert check_password('A-very-long-secret-2026',encoded)
    assert not check_password('wrong-long-secret',encoded)


def test_demo_is_read_only_until_sign_in(tmp_path):
    client,_=create_clients(tmp_path)
    assert client.get('/api/auth/me').json()['read_only']
    assert client.get('/api/dashboard').status_code==200
    assert client.post('/api/invoices',json=new_invoice('DEMO-1')).status_code==401
    assert client.post('/api/v2/cash',json={}).status_code==401
    assert client.get('/api/health').json()['mode']=='demo'


def test_register_csrf_private_workspace_logout(tmp_path):
    client,_=create_clients(tmp_path)
    result=client.post('/api/auth/register',json={'email':'owner@example.com','password':'A-super-safe-2026-passphrase'})
    assert result.status_code==200,result.text
    identity=result.json()
    assert identity['authenticated'] and identity['email']=='owner@example.com'
    assert 'httponly' in result.headers['set-cookie'].lower()
    assert 'samesite=strict' in result.headers['set-cookie'].lower()
    assert 'password' not in str(identity).lower()
    assert client.get('/api/dashboard').json()['summary']['total_invoices']==0
    assert client.post('/api/invoices',json=new_invoice('ONE')).status_code==403
    assert client.post('/api/invoices',json=new_invoice('TWO'),headers={'X-CSRF-Token':'wrong'}).status_code==403
    saved=client.post('/api/invoices',json=new_invoice('THREE'),headers={'X-CSRF-Token':identity['csrf_token']})
    assert saved.status_code==201,saved.text
    assert client.get('/api/dashboard').json()['summary']['total_invoices']==1
    assert client.post('/api/auth/logout',headers={'X-CSRF-Token':identity['csrf_token']}).status_code==200
    assert client.get('/api/auth/me').json()['authenticated'] is False
    assert client.get('/api/dashboard').json()['summary']['total_invoices']==0


def test_private_accounts_never_see_each_others_invoices(tmp_path):
    first,second=create_clients(tmp_path)
    a=first.post('/api/auth/register',json={'email':'first@example.com','password':'Really-long-first-passphrase'}).json()
    b=second.post('/api/auth/register',json={'email':'second@example.com','password':'Really-long-second-passphrase'}).json()
    assert first.post('/api/invoices',json=new_invoice('FIRST'),headers={'X-CSRF-Token':a['csrf_token']}).status_code==201
    assert second.post('/api/invoices',json=new_invoice('SECOND'),headers={'X-CSRF-Token':b['csrf_token']}).status_code==201
    assert [r['invoice_number'] for r in first.get('/api/invoices').json()['items']]==['FIRST']
    assert [r['invoice_number'] for r in second.get('/api/invoices').json()['items']]==['SECOND']
    assert len(list((tmp_path/'workspaces').glob('*.sqlite3')))==2
    assert first.get('/api/v2/backup').json()['invoices'][0]['invoice_number']=='FIRST'
    assert second.get('/api/v2/backup').json()['invoices'][0]['invoice_number']=='SECOND'


def test_login_validation_and_required_mode(tmp_path):
    client,_=create_clients(tmp_path,mode='required')
    assert client.get('/api/dashboard').status_code==401
    assert client.get('/api/auth/me').status_code==200
    assert client.post('/api/auth/register',json={'email':'a@example.com','password':'short'}).status_code==422
    assert client.post('/api/auth/register',json={'email':'a@example.com','password':'a-valid-long-secret'}).status_code==200
    assert client.post('/api/auth/register',json={'email':'a@example.com','password':'another-long-secret'}).status_code==409
    assert client.post('/api/auth/login',json={'email':'a@example.com','password':'wrong-long-secret'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'a@example.com','password':'a-valid-long-secret'}).status_code==200

