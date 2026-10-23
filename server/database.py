"""SQLite connection lifecycle and additive, versioned schema migration."""
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .business_time import business_timezone


@dataclass
class Config:
    database_path: str
    app_url: str = ""
    secure_cookies: bool = False
    production: bool = False
    max_body_bytes: int = 2_000_000

    @classmethod
    def from_environment(cls):
        business_timezone()  # Fail startup early for invalid/missing IANA data.
        production = os.getenv("APP_ENV", "development").lower() == "production"
        secure = os.getenv("SECURE_COOKIES", str(production)).lower() == "true"
        app_url = (os.getenv("APP_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
        if production and (not secure or not app_url.startswith("https://")):
            raise RuntimeError("Production requires SECURE_COOKIES=true and an https APP_URL")
        default = str(Path(__file__).parent / "data" / "agentpay.sqlite3")
        return cls(os.getenv("DATABASE_PATH", default), app_url, secure, production)


@contextmanager
def database(config, *, write=False):
    connection = sqlite3.connect(config.database_path, timeout=15, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(config):
    if config.database_path == ":memory:":
        raise RuntimeError("DATABASE_PATH must be a persistent file")
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.database_path, timeout=15)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            raise RuntimeError("Database schema is newer than this application")
        if version == 0:
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tenants (id TEXT PRIMARY KEY, company TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), sender_name TEXT NOT NULL DEFAULT '',
                    reply_to TEXT NOT NULL DEFAULT '', bank_details TEXT NOT NULL DEFAULT '',
                    annual_rate REAL NOT NULL DEFAULT 22, cooldown_days INTEGER NOT NULL DEFAULT 3
                );
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), company TEXT NOT NULL,
                    inn TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', number TEXT NOT NULL,
                    issued_on TEXT NOT NULL, due_on TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount > 0),
                    paid_amount INTEGER NOT NULL DEFAULT 0 CHECK(paid_amount >= 0 AND paid_amount <= amount),
                    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','disputed','paused')),
                    promise_date TEXT, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    UNIQUE(tenant_id, company, number), UNIQUE(id, tenant_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), invoice_id TEXT NOT NULL,
                    type TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    FOREIGN KEY(invoice_id, tenant_id) REFERENCES invoices(id, tenant_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), invoice_id TEXT NOT NULL,
                    subject TEXT NOT NULL, body TEXT NOT NULL, recipient TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','sent','failed')),
                    source TEXT NOT NULL DEFAULT 'template', balance_snapshot INTEGER NOT NULL,
                    created_at TEXT NOT NULL, sent_at TEXT,
                    FOREIGN KEY(invoice_id, tenant_id) REFERENCES invoices(id, tenant_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS payments (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), invoice_id TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount > 0), paid_on TEXT NOT NULL, reference TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(tenant_id, invoice_id, reference),
                    FOREIGN KEY(invoice_id, tenant_id) REFERENCES invoices(id, tenant_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS invoices_tenant ON invoices(tenant_id, due_on);
                CREATE INDEX IF NOT EXISTS events_invoice ON events(tenant_id, invoice_id, created_at);
                CREATE INDEX IF NOT EXISTS messages_invoice ON messages(tenant_id, invoice_id, created_at);
                CREATE INDEX IF NOT EXISTS payments_tenant ON payments(tenant_id, paid_on);
                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
                INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
                PRAGMA user_version = 1;
                COMMIT;
            """)
        connection.commit()
    finally:
        connection.close()
