"""SQLite connection lifecycle and additive, versioned schema migration."""
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .business_time import business_timezone

SCHEMA_VERSION = 3


@dataclass
class Config:
    database_path: str
    app_url: str = ""
    secure_cookies: bool = False
    production: bool = False
    max_body_bytes: int = 2_000_000
    database_url: str = ""

    @classmethod
    def from_environment(cls):
        business_timezone()  # Fail startup early for invalid/missing IANA data.
        production = os.getenv("APP_ENV", "development").lower() == "production"
        secure = os.getenv("SECURE_COOKIES", str(production)).lower() == "true"
        app_url = (os.getenv("APP_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
        if production and (not secure or not app_url.startswith("https://")):
            raise RuntimeError("Production requires SECURE_COOKIES=true and an https APP_URL")
        default = str(Path(__file__).parent / "data" / "mandato.sqlite3")
        return cls(os.getenv("DATABASE_PATH", default), app_url, secure, production, database_url=os.getenv("DATABASE_URL", ""))


@contextmanager
def database(config, *, write=False):
    if config.database_url:
        from .storage_pg import database as pg_database
        with pg_database(config, write=write) as connection:
            yield connection
        return
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
    if config.database_url:
        from .storage_pg import initialize as pg_initialize
        return pg_initialize(config)
    if config.database_path == ":memory:":
        raise RuntimeError("DATABASE_PATH must be a persistent file")
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.database_path, timeout=15, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        # The version read and every migration share one write lock. Otherwise
        # two version-zero startups can replay v1 after the first reached v2.
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 3:
            raise RuntimeError("Database schema is newer than this application")
        if version == 0:
            schema_sql = LEGACY_SCHEMA_SQL
            # This is static DDL without semicolons inside literals. execute()
            # preserves our transaction; executescript() would implicitly commit.
            for statement in schema_sql.split(";"):
                if statement.strip():
                    connection.execute(statement)
            version = 1
        if version == 1:
            connection.execute("ALTER TABLE messages ADD COLUMN invalidation_reason TEXT")
            # V1 drafts contain no provenance for the then-current sender
            # settings. Preserve their text/history but require a fresh draft.
            connection.execute("UPDATE messages SET status='draft',invalidation_reason='legacy_sender_settings' WHERE status!='sent'")
            connection.execute("INSERT INTO schema_version(version,applied_at) VALUES(2,strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
            connection.execute("PRAGMA user_version=2")
        if version < 3:
            from .finance_migration import migrate_v3
            migrate_v3(connection, LEGACY_SCHEMA_SQL)
        from .finance import initialize_schema as initialize_finance
        initialize_finance(connection)
        for module_name in ('legal', 'agent', 'accounting_import', 'portfolio', 'integrations', 'forecasting', 'negotiation', 'partner', 'workflow', 'yandex_services', 'account_help', 'commercial', 'recovery', 'financing', 'organizations'):
            try:
                module = __import__('server.'+module_name, fromlist=['initialize_schema'])
            except ModuleNotFoundError as error:
                if error.name != 'server.'+module_name: raise
                continue
            if hasattr(module, 'initialize_schema'): module.initialize_schema(connection)
        connection.commit()
        # Journal mode cannot change inside a transaction. Negotiate only after
        # the schema is current, and tolerate a short competing startup lock.
        deadline = time.monotonic() + 15
        while True:
            try:
                mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                if mode.lower() != "wal":
                    raise RuntimeError("Database filesystem must support SQLite WAL")
                break
            except sqlite3.OperationalError as error:
                code = getattr(error, "sqlite_errorcode", 0) & 0xFF
                if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.025)
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


LEGACY_SCHEMA_SQL = "\n                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);\n                CREATE TABLE IF NOT EXISTS tenants (id TEXT PRIMARY KEY, company TEXT NOT NULL, created_at TEXT NOT NULL);\n                CREATE TABLE IF NOT EXISTS users (\n                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),\n                    name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,\n                    created_at TEXT NOT NULL\n                );\n                CREATE TABLE IF NOT EXISTS sessions (\n                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,\n                    csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL\n                );\n                CREATE TABLE IF NOT EXISTS settings (\n                    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), sender_name TEXT NOT NULL DEFAULT '',\n                    reply_to TEXT NOT NULL DEFAULT '', bank_details TEXT NOT NULL DEFAULT '',\n                    annual_rate REAL NOT NULL DEFAULT 22, cooldown_days INTEGER NOT NULL DEFAULT 3\n                );\n                CREATE TABLE IF NOT EXISTS invoices (\n                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), company TEXT NOT NULL,\n                    inn TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', number TEXT NOT NULL,\n                    issued_on TEXT NOT NULL, due_on TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount > 0),\n                    paid_amount INTEGER NOT NULL DEFAULT 0 CHECK(paid_amount >= 0 AND paid_amount <= amount),\n                    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','disputed','paused')),\n                    promise_date TEXT, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,\n                    UNIQUE(tenant_id, company, number), UNIQUE(id, tenant_id)\n                );\n                CREATE TABLE IF NOT EXISTS events (\n                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), invoice_id TEXT NOT NULL,\n                    type TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,\n                    FOREIGN KEY(invoice_id, tenant_id) REFERENCES invoices(id, tenant_id) ON DELETE CASCADE\n                );\n                CREATE TABLE IF NOT EXISTS messages (\n                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), invoice_id TEXT NOT NULL,\n                    subject TEXT NOT NULL, body TEXT NOT NULL, recipient TEXT NOT NULL,\n                    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','sent','failed')),\n                    source TEXT NOT NULL DEFAULT 'template', balance_snapshot INTEGER NOT NULL,\n                    created_at TEXT NOT NULL, sent_at TEXT,\n                    FOREIGN KEY(invoice_id, tenant_id) REFERENCES invoices(id, tenant_id) ON DELETE CASCADE\n                );\n                CREATE TABLE IF NOT EXISTS payments (\n                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), invoice_id TEXT NOT NULL,\n                    amount INTEGER NOT NULL CHECK(amount > 0), paid_on TEXT NOT NULL, reference TEXT NOT NULL,\n                    created_at TEXT NOT NULL, UNIQUE(tenant_id, invoice_id, reference),\n                    FOREIGN KEY(invoice_id, tenant_id) REFERENCES invoices(id, tenant_id) ON DELETE CASCADE\n                );\n                CREATE INDEX IF NOT EXISTS invoices_tenant ON invoices(tenant_id, due_on);\n                CREATE INDEX IF NOT EXISTS events_invoice ON events(tenant_id, invoice_id, created_at);\n                CREATE INDEX IF NOT EXISTS messages_invoice ON messages(tenant_id, invoice_id, created_at);\n                CREATE INDEX IF NOT EXISTS payments_tenant ON payments(tenant_id, paid_on);\n                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);\n                INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));\n                PRAGMA user_version = 1;\n            "
from .finance_migration import final_schema
BASE_SCHEMA_SQL = final_schema(LEGACY_SCHEMA_SQL)
