"""Optional Plaid Link / Transactions Sync connector.

Credentials never reach the browser. Access tokens are encrypted in per-user
SQLite workspaces; synced entries are staged, not automatically reconciled.
Plaid is not available in every country and requires its own approved account.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app import banking, operations


SCHEMA = """
CREATE TABLE IF NOT EXISTS plaid_links (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE,
    access_token_ciphertext TEXT NOT NULL,
    cursor TEXT,
    created_at TEXT NOT NULL,
    last_synced_at TEXT
);
"""
URLS = {
    'sandbox': 'https://sandbox.plaid.com',
    'development': 'https://development.plaid.com',
    'production': 'https://production.plaid.com',
}


class PlaidUnavailable(ValueError):
    """Raised when the optional bank connector lacks valid configuration."""


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def configured() -> bool:
    return all(os.getenv(key) for key in ('PLAID_CLIENT_ID', 'PLAID_SECRET', 'PLAID_TOKEN_ENCRYPTION_KEY'))


def encryption() -> Fernet:
    key = os.getenv('PLAID_TOKEN_ENCRYPTION_KEY', '')
    if not key:
        raise PlaidUnavailable('Configure PLAID_TOKEN_ENCRYPTION_KEY before connecting banks')
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as error:
        raise PlaidUnavailable('PLAID_TOKEN_ENCRYPTION_KEY must be a valid Fernet key') from error


def _post(path: str, payload: dict) -> dict:
    environment = os.getenv('PLAID_ENV', 'sandbox').lower()
    if environment not in URLS:
        raise PlaidUnavailable('PLAID_ENV must be sandbox, development or production')
    client_id, secret = os.getenv('PLAID_CLIENT_ID'), os.getenv('PLAID_SECRET')
    if not client_id or not secret:
        raise PlaidUnavailable('Configure PLAID_CLIENT_ID and PLAID_SECRET to enable Plaid')
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        try:
            response = client.post(URLS[environment] + path,
                                   json={**payload, 'client_id': client_id, 'secret': secret})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            # Never log the payload or access tokens: even provider errors may be sensitive.
            raise ValueError('Bank provider request failed. Check Plaid configuration and try again.') from error


def link_token(user_id: str) -> str:
    encryption()  # refuse enrollment unless tokens can be stored safely
    country_codes = [part.strip().upper() for part in os.getenv('PLAID_COUNTRIES', 'US').split(',')]
    if not country_codes or any(len(code) != 2 or not code.isalpha() for code in country_codes):
        raise PlaidUnavailable('PLAID_COUNTRIES should contain two-letter country codes')
    payload = {
        'client_name': 'Floatwise',
        'user': {'client_user_id': user_id},
        'products': ['transactions'],
        'country_codes': country_codes,
        'language': 'en',
        'transactions': {'days_requested': 90},
    }
    redirect = os.getenv('PLAID_REDIRECT_URI')
    if redirect:
        payload['redirect_uri'] = redirect
    token = _post('/link/token/create', payload).get('link_token')
    if not token:
        raise ValueError('Bank provider did not return a Link token')
    return token


def exchange(connection: sqlite3.Connection, public_token: str) -> dict:
    if not public_token or len(public_token) > 2048:
        raise ValueError('Invalid public token')
    crypto = encryption()
    result = _post('/item/public_token/exchange', {'public_token': public_token})
    token, item_id = result.get('access_token'), result.get('item_id')
    if not token or not item_id:
        raise ValueError('Bank provider did not return an Item access token')
    link_id = uuid4().hex
    try:
        connection.execute('''INSERT INTO plaid_links
            (id,item_id,access_token_ciphertext,created_at)
            VALUES (?,?,?,?)''',
            (link_id,item_id,crypto.encrypt(token.encode()).decode(),datetime.now(timezone.utc).isoformat()))
    except sqlite3.IntegrityError as error:
        raise ValueError('This bank connection is already linked') from error
    operations.activity(connection,'linked','plaid',link_id)
    return {'id':link_id,'last_synced_at':None,'note':'Bank linked; sync to stage transactions for review.'}


def links(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        'SELECT id,created_at,last_synced_at FROM plaid_links ORDER BY created_at DESC')]


def _transaction(item: dict) -> dict | None:
    if item.get('pending'):
        return None
    amount = banking.cents(str(item.get('amount', '')))
    signed = -amount  # Plaid positive amounts are debits/expenses.
    currency = item.get('iso_currency_code') or item.get('unofficial_currency_code') or 'USD'
    record = banking.parsed_row(
        str(item.get('date','')), str(item.get('merchant_name') or item.get('name') or 'Bank transaction'),
        signed, str(item.get('transaction_id','')), str(currency))
    if not record['reference']:
        raise ValueError('Plaid transaction did not include a transaction_id')
    return record


def sync(connection: sqlite3.Connection, link_id: str) -> dict:
    row = connection.execute('SELECT * FROM plaid_links WHERE id = ?', (link_id,)).fetchone()
    if not row:
        raise ValueError('Bank connection not found')
    try:
        token = encryption().decrypt(row['access_token_ciphertext'].encode()).decode()
    except InvalidToken as error:
        raise PlaidUnavailable('Bank token cannot be decrypted; check your configured encryption key') from error

    cursor = row['cursor'] or ''
    start_cursor = cursor
    added, modified, removed = [], [], []
    for _ in range(30):  # Bounded pagination, 500/page; caller may sync again.
        result = _post('/transactions/sync', {'access_token':token,'cursor':cursor,'count':500})
        added.extend(result.get('added', []))
        modified.extend(result.get('modified', []))
        removed.extend(result.get('removed', []))
        cursor = result.get('next_cursor',cursor)
        if not result.get('has_more',False):
            break
    else:
        raise ValueError('Provider has more than 15,000 updates; sync with a shorter interval')

    # Keep the cursor + all mutations in one SQLite transaction. On provider
    # failure, no cursor advances and no partial page is committed.
    current = connection.execute('SELECT cursor FROM plaid_links WHERE id = ?', (link_id,)).fetchone()
    if (current['cursor'] or '') != start_cursor:
        raise ValueError('Another sync updated this connection. Please refresh and retry.')
    source = f"plaid:{row['item_id']}"
    created=updated=deleted=reviewed=0
    for data in [*added,*modified]:
        record=_transaction(data)
        if record is None:
            continue
        existing=connection.execute(
            'SELECT id,status FROM bank_transactions WHERE source = ? AND external_id = ?',
            (source,record['reference'])).fetchone()
        if existing:
            if existing['status']=='unreviewed':
                connection.execute('''UPDATE bank_transactions SET booking_date=?,description=?,
                    signed_amount_cents=?,currency=? WHERE id=?''',
                    (record['booking_date'],record['description'],record['signed_amount_cents'],record['currency'],existing['id']))
                updated+=1
            else:
                reviewed+=1  # Never rewrite user-approved finance records.
            continue
        connection.execute('''INSERT INTO bank_transactions
            (id,source,external_id,booking_date,description,signed_amount_cents,currency,created_at)
            VALUES (?,?,?,?,?,?,?,?)''',
            (str(uuid4()),source,record['reference'],record['booking_date'],record['description'],
             record['signed_amount_cents'],record['currency'],datetime.now(timezone.utc).isoformat()))
        created+=1
    for item in removed:
        transaction_id = item.get('transaction_id')
        existing=connection.execute(
            'SELECT id,status FROM bank_transactions WHERE source=? AND external_id=?',
            (source,transaction_id)).fetchone()
        if existing and existing['status']=='unreviewed':
            connection.execute('DELETE FROM bank_transactions WHERE id = ?', (existing['id'],))
            deleted+=1
        elif existing:
            reviewed+=1
    connection.execute('UPDATE plaid_links SET cursor=?,last_synced_at=? WHERE id=?',
                       (cursor,datetime.now(timezone.utc).isoformat(),link_id))
    operations.activity(connection,'synced','plaid',link_id)
    return {'new':created,'updated':updated,'removed_unreviewed':deleted,
            'previously_reviewed_unchanged':reviewed,
            'note':'Transactions are staged; manually review before posting or matching.'}
