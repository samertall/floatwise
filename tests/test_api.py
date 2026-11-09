from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "test.db", seed_demo=False))


def payload(number="INV-001"):
    today = date.today()
    return {
        "invoice_number": number,
        "customer": "Aster Design",
        "amount": "1234.56",
        "issued_on": today.isoformat(),
        "due_on": (today + timedelta(days=20)).isoformat(),
        "notes": "First project",
    }


def test_health_and_empty_workspace(client):
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/api/dashboard').json()['summary']['total_invoices'] == 0
    assert client.get('/').status_code == 200
    assert 'floatwise' in client.get('/').text.lower()


def test_invoice_lifecycle_and_money_precision(client):
    response = client.post('/api/invoices', json=payload())
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['amount_cents'] == 123456
    assert len(client.get('/api/invoices').json()['items']) == 1
    assert client.post('/api/invoices', json=payload()).status_code == 409
    assert client.get('/api/dashboard').json()['summary']['outstanding_cents'] == 123456

    today = date.today().isoformat()
    paid = client.patch(f"/api/invoices/{row['id']}/payment", json={'paid_on': today})
    assert paid.status_code == 200
    assert client.get('/api/dashboard').json()['summary']['paid_count'] == 1
    assert client.patch(f"/api/invoices/{row['id']}/payment", json={'paid_on': None}).status_code == 200
    assert client.delete(f"/api/invoices/{row['id']}").status_code == 204
    assert client.delete(f"/api/invoices/{row['id']}").status_code == 404


def test_invalid_date_and_amount_are_rejected(client):
    invalid = payload()
    invalid['due_on'] = (date.today() - timedelta(days=1)).isoformat()
    assert client.post('/api/invoices', json=invalid).status_code == 422
    invalid = payload()
    invalid['amount'] = '-10'
    assert client.post('/api/invoices', json=invalid).status_code == 422


def test_csv_import_export_and_atomicity(client):
    header = 'invoice_number,customer,amount,issued_on,due_on,paid_on,notes\n'
    row = f'INV-A,Acme,42.15,{date.today().isoformat()},{date.today().isoformat()},,A note\n'
    response = client.post('/api/import', content=header+row, headers={'Content-Type':'text/csv'})
    assert response.status_code == 200, response.text
    assert response.json()['imported'] == 1
    assert '42.15' in client.get('/api/export').text
    # The second batch has a unique row first and a duplicate second: nothing commits.
    bad = f'INV-B,Acme,5,{date.today().isoformat()},{date.today().isoformat()},,\n' + row
    assert client.post('/api/import', content=header+bad, headers={'Content-Type':'text/csv'}).status_code == 409
    assert len(client.get('/api/invoices').json()['items']) == 1


def test_settings_change_forecast(client):
    response = client.patch('/api/settings', json={'opening_balance':'800.05','monthly_expenses':'300.00'})
    assert response.status_code == 200
    assert response.json()['opening_balance_cents'] == 80005
    forecast = client.get('/api/dashboard').json()['forecast']['scenarios']['base']
    assert forecast['points'][0]['balance_cents'] == 80005

