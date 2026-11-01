import os
from pathlib import Path

import pytest

from scripts.postgres_backup import backup, client_command, restore_empty
from test_storage_pg import postgres_config


def test_docker_command_never_contains_database_credentials(monkeypatch):
    monkeypatch.setattr('scripts.postgres_backup.shutil.which',lambda tool:'/usr/bin/'+tool)
    monkeypatch.setenv('PGPASSWORD','unrelated-shell-secret')
    command,env=client_command('pg_dump','postgresql://test_user:test-only-secret@127.0.0.1:55432/test_db',docker=True)
    assert 'test-only-secret' not in ' '.join(command)
    assert 'unrelated-shell-secret' not in ' '.join(command)
    assert env['PGPASSWORD']=='test-only-secret'
    assert env['PGHOST']=='host.docker.internal'
    assert env['PGDATABASE']=='test_db'


def test_backup_does_not_overwrite_existing_archive(tmp_path,monkeypatch):
    monkeypatch.setattr('scripts.postgres_backup.shutil.which',lambda tool:None)
    path=tmp_path/'important.dump';path.write_bytes(b'keep')
    with pytest.raises(FileExistsError):backup('postgresql://invalid',path)
    assert path.read_bytes()==b'keep'


def test_missing_client_tools_remove_only_the_new_reservation(tmp_path,monkeypatch):
    monkeypatch.setattr('scripts.postgres_backup.shutil.which',lambda tool:None)
    path=tmp_path/'new.dump'
    with pytest.raises(ValueError,match='client tools or Docker'):
        backup('postgresql://invalid',path)
    assert not path.exists()


def test_invalid_restore_source_does_not_connect(tmp_path):
    with pytest.raises(ValueError,match='Archive does not exist'):
        restore_empty('postgresql://invalid',tmp_path/'missing.dump')


def test_real_postgres_backup_restores_money_and_refuses_nonempty_target(postgres_config,tmp_path):
    import uuid
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from scripts.private_files import is_private
    target_name='mandato_restore_'+uuid.uuid4().hex
    admin_url=make_conninfo(postgres_config.database_url,dbname='postgres',options='')
    target_url=make_conninfo(postgres_config.database_url,dbname=target_name,options='')
    with psycopg.connect(postgres_config.database_url) as c:
        schema=c.execute('SELECT current_schema()').fetchone()[0]
        c.execute('CREATE TABLE backup_money(amount BIGINT)')
        c.execute('INSERT INTO backup_money VALUES(%s)',(1_000_000_000_000_000,))
    with psycopg.connect(admin_url,autocommit=True) as c:
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target_name)))
    try:
        archive=backup(postgres_config.database_url,tmp_path/'private.dump')
        assert is_private(archive)
        restore_empty(target_url,archive)
        with psycopg.connect(target_url) as c:
            assert c.execute(sql.SQL('SELECT amount FROM {}.backup_money').format(sql.Identifier(schema))).fetchone()[0]==1_000_000_000_000_000
        with pytest.raises(ValueError,match='empty database'):
            restore_empty(target_url,archive)
    finally:
        with psycopg.connect(admin_url,autocommit=True) as c:
            c.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(target_name)))
