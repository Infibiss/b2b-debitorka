"""Create a consistent, private SQLite backup, including committed WAL data."""
from __future__ import annotations

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys


def backup_database(database: Path, output: Path) -> None:
    """Never create a missing source or overwrite an existing destination."""
    database = database.expanduser().resolve()
    output = output.expanduser().absolute()
    if not database.is_file():
        raise ValueError(f"Database does not exist: {database}")
    if database == output.resolve():
        raise ValueError("Source and destination must be different files")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Exclusive reservation prevents accidentally replacing a previous backup.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=15)) as source:
            with closing(sqlite3.connect(output, timeout=15)) as target:
                source.backup(target, pages=256, sleep=0.05)
                target.execute("PRAGMA journal_mode=DELETE")
                if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Backup failed SQLite integrity_check")
        with output.open("rb") as saved:
            os.fsync(saved.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(output) + suffix).unlink(missing_ok=True)
        raise


def default_database() -> str:
    return os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parents[1] / "server/data/agentpay.sqlite3"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=default_database())
    parser.add_argument("--output", type=Path, required=True, help="New backup filename; existing files are refused")
    args = parser.parse_args()
    try:
        backup_database(args.database, args.output)
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Backup failed: {error}", file=sys.stderr)
        return 1
    print(f"Backup verified: {args.output.absolute()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
