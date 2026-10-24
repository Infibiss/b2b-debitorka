import os
from pathlib import Path

import pytest

from scripts.postgres_backup import backup, client_command, restore_empty


def test_docker_command_never_contains_database_credentials(monkeypatch):
    monkeypatch.setattr('scripts.postgres_backup.shutil.which',lambda tool:'/usr/bin/'+tool)
    monkeypatch.setenv('PGPASSWORD','unrelated-shell-secret')
    command,env=client_command('pg_dump','postgresql://test_user:test-only-secret@127.0.0.1:55432/test_db',docker=True)
    assert 'test-only-secret' not in ' '.join(command)
    assert 'unrelated-shell-secret' not in ' '.join(command)
    assert env['PGPASSWORD']=='test-only-secret'
    assert env['PGHOST']=='host.docker.internal'
    assert env['PGDATABASE']=='test_db'


def test_backup_does_not_overwrite_existing_archive(tmp_path):
    path=tmp_path/'important.dump';path.write_bytes(b'keep')
    with pytest.raises(FileExistsError):backup('postgresql://invalid',path)
    assert path.read_bytes()==b'keep'


def test_invalid_restore_source_does_not_connect(tmp_path):
    with pytest.raises(ValueError,match='Archive does not exist'):
        restore_empty('postgresql://invalid',tmp_path/'missing.dump')
