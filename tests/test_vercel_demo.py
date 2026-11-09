"""Vercel's serverless deployment must not depend on persistent SQLite state."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def vercel_client(monkeypatch, tmp_path):
    monkeypatch.setenv('VERCEL', '1')
    # Even a misconfigured deployment cannot enable unrestricted API access.
    monkeypatch.setenv('FLOATWISE_AUTH_MODE', 'off')
    monkeypatch.setenv('FLOATWISE_ALLOW_SIGNUP', '1')
    app = create_app(tmp_path/'ephemeral.sqlite3', seed_demo=True, auth_mode='off')
    assert app.state.auth_mode == 'demo'
    assert app.state.auth_service is None
    return TestClient(app)


def test_public_demo_is_read_only_and_usable(vercel_client):
    client = vercel_client
    dashboard = client.get('/api/dashboard')
    assert dashboard.status_code == 200
    assert dashboard.json()['summary']['total_invoices'] > 0
    assert len(client.get('/api/v2/features').json()['features']) == 100
    assert client.get('/api/v3/bank-transactions').status_code == 200
    identity = client.get('/api/auth/me').json()
    assert identity['read_only'] is True
    assert identity['login_enabled'] is False
    assert identity['signup_enabled'] is False
    assert client.post('/api/auth/register', json={
        'email':'demo@example.com', 'password':'strong-enough-password'}).status_code == 403
    assert client.post('/api/auth/login', json={
        'email':'demo@example.com', 'password':'strong-enough-password'}).status_code == 403
    assert client.post('/api/v3/plaid/link-token').status_code == 401
    assert client.post('/api/import', content='').status_code == 401
    assert client.post('/api/invoices', json={}).status_code == 401


def test_vercel_static_assets_and_attribution(vercel_client):
    client = vercel_client
    html = client.get('/')
    assert html.status_code == 200
    assert 'Designed &amp; developed by' in html.text
    assert 'https://github.com/samertall/floatwise' in html.text
    assert '/static/demo.css' in html.text
    css = client.get('/static/demo.css')
    assert css.status_code == 200
    assert 'body.public-demo' in css.text
