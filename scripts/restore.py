"""Restore SQLite offline; replacing an existing DB requires explicit consent."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
import uuid

try:
    from .backup import backup_database, default_database
except ImportError:
    from backup import backup_database, default_database


def restore_database(backup: Path, database: Path, *, replace_existing: bool = False) -> Path | None:
    backup = backup.expanduser().resolve()
    database = database.expanduser().absolute()
    if database.is_symlink():
        raise ValueError("Restore destination must not be a symbolic link")
    if backup == database.resolve():
        raise ValueError("Backup and destination must be different files")
    exists_at_start = database.exists()
    if exists_at_start and not database.is_file():
        raise ValueError("Restore destination must be a regular file")
    if exists_at_start and not replace_existing:
        raise ValueError("Database already exists; stop the app and use --replace-existing explicitly")
    sidecars = [Path(str(database) + suffix) for suffix in ("-wal", "-shm", "-journal")]
    if not exists_at_start and any(path.exists() for path in sidecars):
        raise ValueError("Orphan SQLite sidecar files found; inspect them before restoring")

    database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = database.with_name(f".{database.name}.restore-{uuid.uuid4().hex}.db")
    rollback = None
    try:
        # Validate the input and build a standalone restored file before touching live data.
        backup_database(backup, temporary)
        with closing(sqlite3.connect(temporary, timeout=5)) as restored:
            required = {"tenants", "users", "sessions", "settings", "invoices", "payments", "messages", "events", "schema_version"}
            present = {row[0] for row in restored.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = restored.execute("PRAGMA user_version").fetchone()[0]
            if version not in (1, 2, 3) or not required.issubset(present):
                raise ValueError("Backup is not a supported AgentPay schema version 1, 2 or 3 database")
            if version >= 2 and "invalidation_reason" not in {row[1] for row in restored.execute("PRAGMA table_info(messages)")}:
                raise ValueError("Backup is missing the AgentPay schema version 2 message provenance")
            if version == 3:
                required_v3 = {"finance_counterparties", "finance_bank_payments", "finance_actions", "finance_adjustments", "finance_reversals", "finance_promises", "finance_installments", "finance_imports", "finance_identity_conflicts"}
                invoice_columns = {row[1] for row in restored.execute("PRAGMA table_info(invoices)")}
                payment_columns = {row[1] for row in restored.execute("PRAGMA table_info(payments)")}
                if not required_v3.issubset(present) or not {"counterparty_id", "number_key", "opening_paid_amount", "adjustment_amount", "promised_amount", "revision"}.issubset(invoice_columns) or not {"bank_payment_id", "reversed_amount"}.issubset(payment_columns):
                    raise ValueError("Backup is missing the AgentPay schema version 3 financial ledger")
            if restored.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Backup contains invalid foreign-key references")
        if exists_at_start:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            rollback = database.with_name(f"{database.name}.pre-restore-{stamp}-{uuid.uuid4().hex[:8]}.db")
            backup_database(database, rollback)
            # All application instances must be stopped. A busy checkpoint is a hard refusal.
            with closing(sqlite3.connect(database, timeout=5)) as old:
                checkpoint = old.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if checkpoint and checkpoint[0] != 0:
                    raise ValueError("Database is busy; stop every application process before restoring")
            for sidecar in sidecars:
                sidecar.unlink(missing_ok=True)
        if exists_at_start:
            os.replace(temporary, database)
        else:
            # link is atomic and refuses a destination created since the initial check.
            os.link(temporary, database)
            temporary.unlink()
        return rollback
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=default_database())
    parser.add_argument("--replace-existing", action="store_true", help="Preserve current DB as a verified pre-restore backup, then replace it")
    parser.add_argument("--app-stopped", action="store_true", required=True, help="Confirm all app processes using this database have been stopped")
    args = parser.parse_args()
    try:
        rollback = restore_database(args.backup, args.database, replace_existing=args.replace_existing)
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Restore failed: {error}", file=sys.stderr)
        return 1
    print(f"Restore verified: {args.database.absolute()}")
    if rollback:
        print(f"Previous database preserved: {rollback}")
    print("Restart one application instance and verify health and balances before reopening access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
