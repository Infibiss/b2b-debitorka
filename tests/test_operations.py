"""Offline CLI tests; every database and subprocess is isolated from real data."""
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from server.database import Config, initialize


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def live_database(tmp_path):
    path = tmp_path / "live.db"
    initialize(Config(str(path)))
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE ledger (amount INTEGER)")
    connection.execute("INSERT INTO ledger VALUES (12345)")
    connection.commit()
    yield path, connection
    connection.close()


def command(script, *arguments):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)],
        text=True, capture_output=True, timeout=20,
    )


def make_backup(database, snapshot):
    result = command("backup.py", "--database", database, "--output", snapshot)
    assert result.returncode == 0, result.stderr


def total(database):
    with sqlite3.connect(database) as connection:
        return connection.execute("SELECT sum(amount) FROM ledger").fetchone()[0]


def test_backup_includes_committed_wal_in_a_single_private_file(live_database, tmp_path):
    database, _ = live_database
    assert Path(str(database) + "-wal").exists()
    snapshot = tmp_path / "backup.db"
    make_backup(database, snapshot)
    assert total(snapshot) == 12345
    assert not Path(str(snapshot) + "-wal").exists()
    assert snapshot.stat().st_mode & 0o777 == 0o600


def test_backup_refuses_overwrite_and_does_not_create_missing_source(live_database, tmp_path):
    database, _ = live_database
    snapshot = tmp_path / "existing.db"
    snapshot.write_bytes(b"preserve")
    result = command("backup.py", "--database", database, "--output", snapshot)
    assert result.returncode != 0
    assert snapshot.read_bytes() == b"preserve"
    missing = tmp_path / "missing.db"
    result = command("backup.py", "--database", missing, "--output", tmp_path / "new.db")
    assert result.returncode != 0
    assert not missing.exists()


def test_restore_requires_explicit_offline_confirmation(live_database, tmp_path):
    database, _ = live_database
    snapshot, target = tmp_path / "backup.db", tmp_path / "restored.db"
    make_backup(database, snapshot)
    result = command("restore.py", "--backup", snapshot, "--database", target)
    assert result.returncode != 0
    assert not target.exists()


def test_restore_roundtrip_and_default_existing_file_refusal(live_database, tmp_path):
    database, _ = live_database
    snapshot, target = tmp_path / "backup.db", tmp_path / "restored.db"
    make_backup(database, snapshot)
    result = command("restore.py", "--backup", snapshot, "--database", target, "--app-stopped")
    assert result.returncode == 0, result.stderr
    assert total(target) == 12345
    result = command("restore.py", "--backup", snapshot, "--database", target, "--app-stopped")
    assert result.returncode != 0
    assert total(target) == 12345


def test_explicit_replacement_preserves_a_verified_previous_database(live_database, tmp_path):
    database, connection = live_database
    snapshot = tmp_path / "backup.db"
    make_backup(database, snapshot)
    connection.execute("INSERT INTO ledger VALUES (7)")
    connection.commit()
    connection.close()
    result = command("restore.py", "--backup", snapshot, "--database", database, "--app-stopped", "--replace-existing")
    assert result.returncode == 0, result.stderr
    assert total(database) == 12345
    originals = list(tmp_path.glob("live.db.pre-restore-*.db"))
    assert len(originals) == 1
    assert total(originals[0]) == 12352


def test_corrupt_backup_never_replaces_existing_data(live_database, tmp_path):
    database, connection = live_database
    connection.close()
    snapshot = tmp_path / "corrupt.db"
    snapshot.write_bytes(b"not a SQLite database")
    result = command("restore.py", "--backup", snapshot, "--database", database, "--app-stopped", "--replace-existing")
    assert result.returncode != 0
    assert total(database) == 12345


def test_restore_refuses_orphan_sqlite_sidecars(live_database, tmp_path):
    database, _ = live_database
    snapshot, target = tmp_path / "backup.db", tmp_path / "missing.db"
    make_backup(database, snapshot)
    sidecar = Path(str(target) + "-wal")
    sidecar.write_bytes(b"unknown")
    result = command("restore.py", "--backup", snapshot, "--database", target, "--app-stopped")
    assert result.returncode != 0
    assert not target.exists()
    assert sidecar.read_bytes() == b"unknown"


def test_restore_refuses_an_unrelated_valid_sqlite_database(live_database, tmp_path):
    database, connection = live_database
    connection.close()
    snapshot = tmp_path / "unrelated.db"
    with sqlite3.connect(snapshot) as unrelated:
        unrelated.execute("CREATE TABLE unrelated (value TEXT)")
    result = command("restore.py", "--backup", snapshot, "--database", database, "--app-stopped", "--replace-existing")
    assert result.returncode != 0
    assert total(database) == 12345
