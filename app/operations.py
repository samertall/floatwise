"""Finance operations: customers, cash movements, budgets, tasks, saved views.

Each resource uses explicit validated fields and a parameterized SQL whitelist.
The application remains a single-workspace localhost demo, not a multi-tenant SaaS.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


SCHEMA = """
CREATE TABLE IF NOT EXISTS cash_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income','expense')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    occurs_on TEXT NOT NULL,
    category TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cash_events_date ON cash_events(occurs_on);
CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL UNIQUE COLLATE NOCASE,
    monthly_limit_cents INTEGER NOT NULL CHECK (monthly_limit_cents >= 0),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('collection','expense','general')),
    customer TEXT NOT NULL DEFAULT '',
    due_on TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('low','medium','high')),
    status TEXT NOT NULL CHECK (status IN ('open','done','snoozed')),
    assignee TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_tasks_due ON work_tasks(due_on);
CREATE TABLE IF NOT EXISTS customer_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL DEFAULT '',
    segment TEXT NOT NULL DEFAULT 'Standard',
    payment_terms_days INTEGER NOT NULL DEFAULT 30,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_views (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL UNIQUE COLLATE NOCASE,
    resource TEXT NOT NULL CHECK (resource IN ('invoices','tasks','cash')),
    search_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_log (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
"""


def money_cents(value: Decimal) -> int:
    return int((value * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


class CashInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    kind: str = Field(pattern=r'^(income|expense)$')
    amount: Decimal = Field(gt=0, le=Decimal('1000000000'))
    occurs_on: date
    category: str = Field(min_length=2, max_length=60)
    notes: str = Field(default='', max_length=500)


class BudgetInput(BaseModel):
    category: str = Field(min_length=2, max_length=60)
    monthly_limit: Decimal = Field(ge=0, le=Decimal('1000000000'))


class TaskInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    category: str = Field(default='general', pattern=r'^(collection|expense|general)$')
    customer: str = Field(default='', max_length=100)
    due_on: date
    priority: str = Field(default='medium', pattern=r'^(low|medium|high)$')
    status: str = Field(default='open', pattern=r'^(open|done|snoozed)$')
    assignee: str = Field(default='', max_length=100)
    notes: str = Field(default='', max_length=500)


class CustomerInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(default='', max_length=160)
    segment: str = Field(default='Standard', max_length=40)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    notes: str = Field(default='', max_length=500)

    @model_validator(mode='after')
    def check_email(self):
        if self.email and (self.email.count('@') != 1 or '.' not in self.email.split('@')[-1]):
            raise ValueError('Use a valid email address or leave the field blank')
        return self


class ViewInput(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    resource: str = Field(pattern=r'^(invoices|tasks|cash)$')
    search_text: str = Field(default='', max_length=120)


MODELS = {
    'cash': CashInput,
    'budgets': BudgetInput,
    'tasks': TaskInput,
    'customers': CustomerInput,
    'views': ViewInput,
}
TABLES = {
    'cash': 'cash_events',
    'budgets': 'budgets',
    'tasks': 'work_tasks',
    'customers': 'customer_profiles',
    'views': 'saved_views',
}
ORDERING = {
    'cash': 'occurs_on DESC, created_at DESC',
    'budgets': 'category COLLATE NOCASE',
    'tasks': "CASE status WHEN 'open' THEN 0 WHEN 'snoozed' THEN 1 ELSE 2 END, due_on ASC",
    'customers': 'name COLLATE NOCASE',
    'views': 'title COLLATE NOCASE',
}


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def get_rows(connection: sqlite3.Connection, resource: str) -> list[dict]:
    table = TABLES[resource]
    return [dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY {ORDERING[resource]}')]


def get_all(connection: sqlite3.Connection) -> dict[str, list[dict]]:
    return {resource: get_rows(connection, resource) for resource in TABLES}


def activity(connection: sqlite3.Connection, action: str, resource: str, resource_id: str) -> None:
    connection.execute(
        'INSERT INTO activity_log(id,action,resource,resource_id,occurred_at) VALUES (?,?,?,?,?)',
        (str(uuid4()), action, resource, resource_id, datetime.now(timezone.utc).isoformat()),
    )


def get_activity(connection: sqlite3.Connection, limit: int = 50) -> list[dict]:
    return [dict(row) for row in connection.execute(
        'SELECT * FROM activity_log ORDER BY occurred_at DESC LIMIT ?', (min(limit, 100),)
    )]


def serialize(resource: str, payload: BaseModel) -> dict:
    row = payload.model_dump(mode='json')
    if resource == 'cash':
        row['amount_cents'] = money_cents(payload.amount)
        del row['amount']
    if resource == 'budgets':
        row['monthly_limit_cents'] = money_cents(payload.monthly_limit)
        del row['monthly_limit']
    for name in ('title','name','category'):
        if name in row:
            row[name] = row[name].strip()
    return row


def create(connection: sqlite3.Connection, resource: str, payload: BaseModel) -> dict:
    row = {**serialize(resource, payload), 'id':str(uuid4()), 'created_at':datetime.now(timezone.utc).isoformat()}
    keys = list(row)
    placeholders = ','.join('?' for _ in keys)
    columns = ','.join(keys)  # Keys originate from whitelisted Pydantic models.
    connection.execute(f'INSERT INTO {TABLES[resource]} ({columns}) VALUES ({placeholders})', tuple(row[k] for k in keys))
    activity(connection, 'created', resource, row['id'])
    return row


def update(connection: sqlite3.Connection, resource: str, item_id: str, payload: BaseModel) -> dict | None:
    row = serialize(resource, payload)
    keys = list(row)
    table = TABLES[resource]
    cursor = connection.execute(
        f"UPDATE {table} SET {','.join(f'{key} = ?' for key in keys)} WHERE id = ?",
        (*[row[k] for k in keys], item_id),
    )
    if not cursor.rowcount:
        return None
    activity(connection, 'updated', resource, item_id)
    return dict(connection.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,)).fetchone())


def remove(connection: sqlite3.Connection, resource: str, item_id: str) -> bool:
    result = connection.execute(f'DELETE FROM {TABLES[resource]} WHERE id = ?', (item_id,))
    if result.rowcount:
        activity(connection, 'deleted', resource, item_id)
        return True
    return False


def backup_data(connection: sqlite3.Connection) -> dict:
    """Export portable JSON; deliberately excludes any access tokens or secrets."""
    from app.database import fetch_invoices, fetch_settings
    return {
        'format': 'floatwise-v2',
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'invoices': fetch_invoices(connection),
        'settings': fetch_settings(connection),
        'resources': get_all(connection),
        'activity': get_activity(connection, 100),
    }


def report_csv(rows: list[dict]) -> str:
    import csv
    import io
    if not rows:
        return ''
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        sanitized = {}
        for key, value in row.items():
            if isinstance(value, (int, float)):
                sanitized[key] = value
            else:
                text = json.dumps(value) if isinstance(value, (dict, list)) else str(value if value is not None else '')
                sanitized[key] = f"'{text}" if text.lstrip().startswith(('=', '+', '-', '@')) else text
        writer.writerow(sanitized)
    return output.getvalue()
