"""V2 contract tests for all 100 indicators and operational workflows."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.feature_lab import FEATURE_GROUPS
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / 'v2.db', seed_demo=False, auth_mode='off'))


def metrics(client):
    response = client.get('/api/v2/features')
    assert response.status_code == 200, response.text
    return {item['id']:item for item in response.json()['features']}


def cash_payload(kind='income', amount='80.25'):
    return {'title':f'{kind.title()} event', 'kind':kind, 'amount':amount,
            'occurs_on':date.today().isoformat(), 'category':'Operations','notes':'Demo'}


def test_exactly_100_unique_executable_features(client):
    assert len(FEATURE_GROUPS) == 10
    assert all(len(items)==10 for items in FEATURE_GROUPS.values())
    result = client.get('/api/v2/features').json()
    assert result['total'] == 100
    assert len(result['features']) == 100
    ids = [item['id'] for item in result['features']]
    assert len(ids) == len(set(ids))
    assert all(item['description'] and item['kind'] and item['value'] is not None for item in result['features'])
    assert metrics(client)['cash.net']['value'] == 0


def test_cash_events_drive_metrics_and_can_be_edited(client):
    income=client.post('/api/v2/cash',json=cash_payload()).json()
    expense=client.post('/api/v2/cash',json=cash_payload('expense','30.10')).json()
    assert income['amount_cents'] == 8025
    assert expense['amount_cents'] == 3010
    v=metrics(client)
    assert v['cash.in_total']['value']==8025
    assert v['cash.out_total']['value']==3010
    assert v['cash.net']['value']==5015
    update=client.put(f"/api/v2/cash/{expense['id']}",json=cash_payload('expense','20.00'))
    assert update.status_code==200
    assert metrics(client)['cash.net']['value']==6025
    assert client.delete(f"/api/v2/cash/{income['id']}").status_code==204
    assert metrics(client)['cash.in_count']['value']==0


def test_budgets_compute_overspend_and_variance(client):
    record=client.post('/api/v2/budgets',json={'category':'Operations','monthly_limit':'100.00'})
    assert record.status_code==201
    assert client.post('/api/v2/budgets',json={'category':'Operations','monthly_limit':'100.00'}).status_code==409
    assert client.post('/api/v2/budgets',json={'category':'operations','monthly_limit':'100.00'}).status_code==409
    client.post('/api/v2/cash',json=cash_payload('expense','145.00'))
    m=metrics(client)
    assert m['budgets.overspent_count']['value']==1
    assert m['budgets.largest_overage']['value']==4500
    assert m['budgets.utilization']['value']==145.0


def test_tasks_customers_and_saved_views(client):
    due=(date.today()+timedelta(days=2)).isoformat()
    task={'title':'Call about overdue invoice','category':'collection','customer':'Acme','due_on':due,
          'priority':'high','status':'open','assignee':'Samer','notes':'Discuss terms'}
    created=client.post('/api/v2/tasks',json=task)
    assert created.status_code==201, created.text
    assert metrics(client)['ops.high_tasks']['value']==1
    done=client.put(f"/api/v2/tasks/{created.json()['id']}",json={**task,'status':'done'})
    assert done.status_code==200
    assert metrics(client)['health.task_completion']['value']==100.0
    customer=client.post('/api/v2/customers',json={'name':'Acme','email':'finance@acme.test',
        'segment':'Strategic','payment_terms_days':45,'notes':'Relationship account'})
    assert customer.status_code==201
    assert metrics(client)['customers.profiles']['value']==1
    view=client.post('/api/v2/views',json={'title':'Late customers','resource':'invoices','search_text':'Acme'})
    assert view.status_code==201
    assert metrics(client)['ops.saved_views']['value']==1
    assert client.put('/api/v2/tasks/no-such-id',json=task).status_code==404
    assert client.delete('/api/v2/views/no-such-id').status_code==404


def test_validation_reports_and_backup(client):
    invalid=client.post('/api/v2/cash',json=cash_payload('expense','-1'))
    assert invalid.status_code==422
    assert client.post('/api/v2/customers',json={'name':'Acme','email':'not-email'}).status_code==422
    assert client.get('/api/v2/forecast?days=366').status_code==422
    assert len(client.get('/api/v2/forecast?days=14').json()['scenarios']['base']['points'])==15
    client.post('/api/v2/cash',json=cash_payload())
    report=client.get('/api/v2/reports/cash?format=csv')
    assert report.status_code==200 and 'amount_cents' in report.text and '8025' in report.text
    assert len(client.get('/api/v2/reports/features?format=json').json())==100
    assert client.get('/api/v2/reports/unknown').status_code==404
    backup=client.get('/api/v2/backup').json()
    assert backup['format']=='floatwise-v2'
    assert len(backup['resources']['cash'])==1
    assert len(client.get('/api/v2/activity').json()['items'])>=1


def test_reminder_drafts_are_not_sent(client):
    today=date.today()
    invoice={'invoice_number':'INV-FOLLOW','customer':'Acme Studio','amount':'120.50',
             'issued_on':(today-timedelta(days=60)).isoformat(),
             'due_on':(today-timedelta(days=30)).isoformat(), 'notes':''}
    assert client.post('/api/invoices',json=invoice).status_code==201
    response=client.get('/api/v2/reminders')
    assert response.status_code==200
    draft=response.json()['drafts'][0]
    assert 'Acme Studio' in draft['body']
    assert 'INV-FOLLOW' in draft['subject']
    assert 'not sent' in response.json()['disclaimer']


def test_lab_ui_assets_are_served(client):
    page = client.get('/')
    assert page.status_code == 200
    assert 'Intelligence lab' in page.text
    assert 'Operations hub' in page.text
    assert '/static/lab.js' in page.text
    assert client.get('/static/lab.js').status_code == 200
    assert client.get('/static/lab.css').status_code == 200

