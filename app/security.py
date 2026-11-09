"""Local multi-user authentication, isolated workspaces and CSRF-aware sessions.

This module does not claim production identity assurance: email verification,
password recovery, MFA, abuse monitoring and external secret storage remain
deployment responsibilities.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app import database, operations, banking, plaid


workspace_context: ContextVar[Path | None] = ContextVar('floatwise_workspace', default=None)


class ScopedPath:
    """Resolve the request-bound workspace without changing legacy service APIs.

    FastAPI/AnyIO preserves context variables across sync route thread pools.
    This avoids accidental use of a shared file path inside any V1/V2 handler.
    """

    def __init__(self, fallback: Path):
        self.fallback = fallback

    def __str__(self) -> str:
        return str(workspace_context.get() or self.fallback)

    def __fspath__(self) -> str:
        return str(self)


AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    csrf_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
"""
SESSION_DURATION = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str
    csrf_token: str


@contextmanager
def auth_connection(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 10000')
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def encode_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        method, iterations, salt_text, digest_text = encoded.split('$')
        if method != 'scrypt' or iterations != '16384':
            return False
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(digest_text, validate=True)
        actual = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class AuthService:
    def __init__(self, database_path: Path, workspace_root: Path):
        self.database_path = Path(database_path)
        self.workspace_root = Path(workspace_root)
        self._attempt_lock = threading.Lock()
        self._attempts: dict[str, list[float]] = {}
        with auth_connection(self.database_path) as con:
            con.executescript(AUTH_SCHEMA)

    def rate_limit(self, source: str) -> bool:
        now = time.monotonic()
        with self._attempt_lock:
            recent = [x for x in self._attempts.get(source, []) if now - x < 900]
            if len(recent) >= 15:
                self._attempts[source] = recent
                return False
            recent.append(now)
            self._attempts[source] = recent
            return True

    def workspace_path(self, user_id: str) -> Path:
        # User IDs are server-generated UUID hex strings, never a client path.
        if len(user_id) != 32 or any(c not in '0123456789abcdef' for c in user_id):
            raise ValueError('Invalid internal user identifier')
        return self.workspace_root / f'{user_id}.sqlite3'

    def register(self, email: str, password: str) -> str:
        email = email.strip().casefold()
        if not 5 <= len(email) <= 254 or email.count('@') != 1 or '.' not in email.split('@')[-1]:
            raise ValueError('Enter a valid email address')
        if len(password) < 12 or len(password) > 1024:
            raise ValueError('Password must contain 12 to 1024 characters')
        if password.casefold() in (email, email.split('@')[0]):
            raise ValueError('Choose a stronger password')
        user_id = uuid4().hex
        encoded = encode_password(password)
        with auth_connection(self.database_path) as con:
            con.execute('INSERT INTO users(id,email,password_hash,created_at) VALUES (?,?,?,?)',
                        (user_id,email,encoded,int(time.time())))
        location = self.workspace_path(user_id)
        database.initialize(location)
        with database.connect(location) as con:
            operations.initialize(con)
            banking.initialize(con)
            plaid.initialize(con)
        return user_id

    def login(self, email: str, password: str) -> str | None:
        with auth_connection(self.database_path) as con:
            row = con.execute('SELECT id,password_hash FROM users WHERE email = ? COLLATE NOCASE',(email.strip(),)).fetchone()
        # Constant-work rejection for unknown emails minimizes account enumeration.
        hash_to_check = row['password_hash'] if row else encode_password('unavailable-account-dummy-password')
        correct = check_password(password, hash_to_check)
        return row['id'] if row and correct else None

    def new_session(self, user_id: str) -> tuple[str, Identity]:
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        csrf = secrets.token_urlsafe(32)
        expires = int(time.time()) + SESSION_DURATION
        with auth_connection(self.database_path) as con:
            con.execute('DELETE FROM sessions WHERE expires_at <= ?', (int(time.time()),))
            user = con.execute('SELECT email FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user:
                raise ValueError('Unknown account')
            con.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES (?,?,?,?)',
                        (token_hash,user_id,csrf,expires))
        return token, Identity(user_id,user['email'],csrf)

    def identify(self, token: str | None) -> Identity | None:
        if not token or len(token) > 256:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with auth_connection(self.database_path) as con:
            row = con.execute('''SELECT s.user_id, s.csrf_token, u.email
                FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?''', (digest,int(time.time()))).fetchone()
        return Identity(row['user_id'],row['email'],row['csrf_token']) if row else None

    def revoke(self, token: str | None) -> None:
        if token:
            with auth_connection(self.database_path) as con:
                con.execute('DELETE FROM sessions WHERE token_hash = ?',
                            (hashlib.sha256(token.encode()).hexdigest(),))
