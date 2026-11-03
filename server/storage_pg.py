"""PostgreSQL storage with the same row/transaction contract as local SQLite.

Only static application SQL is translated. User values remain bound parameters.
The global transaction advisory lock preserves the current serial financial
write invariant on a small temporary instance, including multiple processes.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import re
import sqlite3

import psycopg
from psycopg.rows import dict_row

WRITE_LOCK = 437102611


class Record:
    def __init__(self, values):
        # PostgreSQL SUM(bigint) returns numeric. Preserve the integer money
        # contract through hashing, JSON snapshots and idempotency records.
        self.values = {key: int(value) if isinstance(value, Decimal) and value == value.to_integral_value() else value
                       for key, value in values.items()}

    def __getitem__(self, key):
        return tuple(self.values.values())[key] if isinstance(key, int) else self.values[key]

    def __iter__(self):
        return iter(self.values.values())

    def __len__(self):
        return len(self.values)

    def keys(self):
        return self.values.keys()

    def get(self, key, default=None):
        return self.values.get(key, default)


def translate_sql(statement, parameters=False):
    if re.match(r"\s*CREATE\s+TABLE\b", statement, re.I):
        statement = re.sub(r"\bINTEGER\b", "BIGINT", statement, flags=re.I)
        statement = re.sub(r"\bREAL\b", "DOUBLE PRECISION", statement, flags=re.I)
    if parameters:
        statement = statement.replace("%", "%%")
    ignore = bool(re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\b", statement, re.I))
    if ignore:
        statement = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", statement, count=1, flags=re.I).rstrip().rstrip(";")
    result, quote, index = [], None, 0
    while index < len(statement):
        char = statement[index]
        if quote:
            result.append(char)
            if char == quote:
                if index + 1 < len(statement) and statement[index + 1] == quote:
                    result.append(statement[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            result.append(char)
        elif char == "?":
            result.append("%s")
        else:
            result.append(char)
        index += 1
    if ignore:
        result.append(" ON CONFLICT DO NOTHING")
    return "".join(result)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return None if row is None else Record(row)

    def fetchall(self):
        return [Record(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return (Record(row) for row in self.cursor)


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        try:
            sql = translate_sql(statement, bool(parameters))
            cursor = self.connection.execute(sql, parameters if parameters else None)
            return Cursor(cursor)
        except psycopg.IntegrityError:
            # Preserve the established API's conflict handling without exposing
            # PostgreSQL error details containing financial/customer values.
            raise sqlite3.IntegrityError("Database constraint rejected the change") from None

    def executemany(self, statement, rows):
        for row in rows:
            self.execute(statement, row)


@contextmanager
def database(config, *, write=False):
    try:
        connection = psycopg.connect(config.database_url, connect_timeout=8, row_factory=dict_row)
    except psycopg.Error:
        raise RuntimeError("PostgreSQL connection unavailable") from None
    try:
        connection.execute("SET LOCAL statement_timeout = '20000ms'")
        connection.execute("SET LOCAL lock_timeout = '15000ms'")
        if write:
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (WRITE_LOCK,))
        else:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield Connection(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(config):
    from .database import BASE_SCHEMA_SQL, SCHEMA_VERSION
    with database(config, write=True) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS schema_version(version BIGINT PRIMARY KEY, applied_at TEXT NOT NULL)")
        row = connection.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
        version = row["version"] or 0
        if version and version != SCHEMA_VERSION:
            raise RuntimeError("PostgreSQL schema needs an explicit compatible migration")
        for statement in BASE_SCHEMA_SQL.split(";"):
            statement = statement.strip()
            if not statement or statement.upper().startswith("PRAGMA"):
                continue
            statement = re.sub(r"\bINTEGER\b", "BIGINT", statement, flags=re.I)
            statement = re.sub(r"\bREAL\b", "DOUBLE PRECISION", statement, flags=re.I)
            connection.execute(statement)
        connection.execute("INSERT OR IGNORE INTO schema_version(version,applied_at) VALUES(?,?)", (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()))
        for name in ("finance", "legal", "agent", "accounting_import", "portfolio", "integrations", "forecasting", "negotiation", "partner", "workflow", "yandex_services", "account_help", "commercial"):
            import importlib
            try:
                module = importlib.import_module("server." + name)
            except ModuleNotFoundError as error:
                if error.name == "server." + name:
                    continue
                raise
            module.initialize_schema(connection)
