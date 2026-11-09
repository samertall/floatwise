"""Small, explicit SQLite persistence layer with parameterized queries."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    invoice_number TEXT NOT NULL UNIQUE,
    customer TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    issued_on TEXT NOT NULL,
    due_on TEXT NOT NULL,
    paid_on TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoices_due ON invoices(due_on);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
INSERT OR IGNORE INTO settings(key, value) VALUES ('opening_balance_cents', 6800000);
INSERT OR IGNORE INTO settings(key, value) VALUES ('monthly_expenses_cents', 1850000);
"""


def initialize(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.executescript(SCHEMA)


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def fetch_invoices(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        "SELECT * FROM invoices ORDER BY due_on ASC, invoice_number ASC"
    )]


def fetch_settings(connection: sqlite3.Connection) -> dict[str, int]:
    return {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM settings")}

