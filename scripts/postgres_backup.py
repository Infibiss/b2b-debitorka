"""Private PostgreSQL archive and restore into an explicitly empty database.

Connection secrets are read from an environment variable, never command-line
arguments or output. Use pg_dump/pg_restore 17 or the official Docker image.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict

try:
    from .private_files import create_private
except ImportError:
    from private_files import create_private


def client_command(tool, url, *, docker=False):
    values = conninfo_to_dict(url)
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    mapping = {'host':'PGHOST','port':'PGPORT','dbname':'PGDATABASE','user':'PGUSER','password':'PGPASSWORD',
               'sslmode':'PGSSLMODE','sslrootcert':'PGSSLROOTCERT','connect_timeout':'PGCONNECT_TIMEOUT','options':'PGOPTIONS'}
    for key, target in mapping.items():
        if key in values: env[target] = values[key]
    env.setdefault('PGCONNECT_TIMEOUT','10')
    if shutil.which(tool) and not docker:
        return [tool], env
    if not shutil.which('docker'):
        raise ValueError('Install PostgreSQL 17 client tools or Docker')
    if env.get('PGHOST') in ('localhost','127.0.0.1'):
        env['PGHOST'] = 'host.docker.internal'
    command = ['docker','run','--rm','-i','--add-host=host.docker.internal:host-gateway']
    for key in mapping.values():
        if key in env: command += ['-e', key]
    return command + ['postgres:17-alpine', tool], env


def run_private(command, env, **kwargs):
    result = subprocess.run(command, env=env, stderr=subprocess.PIPE, timeout=300, **kwargs)
    if result.returncode:
        # Database errors can contain connection strings or customer values.
        raise ValueError('PostgreSQL client failed; check connectivity, client version and database permissions')


def backup(url, output, *, docker=False):
    output = Path(output).expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = create_private(output)
    try:
        with os.fdopen(descriptor,'wb') as handle:
            command, env = client_command('pg_dump', url, docker=docker)
            run_private(command+['--format=custom','--no-owner','--no-acl'], env, stdout=handle)
            handle.flush(); os.fsync(handle.fileno())
        command, env = client_command('pg_restore', url, docker=docker)
        with output.open('rb') as handle:
            run_private(command+['--list'],env,stdin=handle,stdout=subprocess.DEVNULL)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output


def restore_empty(url, archive, *, docker=False):
    archive = Path(archive).expanduser().resolve()
    if not archive.is_file(): raise ValueError('Archive does not exist')
    with psycopg.connect(url,connect_timeout=10) as connection:
        ensure_empty_target(connection)
    command, env = client_command('pg_restore',url,docker=docker)
    with archive.open('rb') as handle:
        run_private(command+['--dbname='+env['PGDATABASE'],'--no-owner','--no-acl','--exit-on-error','--single-transaction'],env,stdin=handle,stdout=subprocess.DEVNULL)


def ensure_empty_target(connection):
    # A view/function/enum can be overwritten or collide with an archive even
    # when pg_tables is empty. Reject all non-system objects before restore.
    count = connection.execute("""SELECT
      (SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE left(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema') +
      (SELECT COUNT(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
       WHERE left(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema') +
      (SELECT COUNT(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
       WHERE left(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema')
      AS object_count""").fetchone()[0]
    if count: raise ValueError('Restore target must be an empty database; existing objects are never replaced')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('backup','restore-empty'))
    parser.add_argument('--file',type=Path,required=True)
    parser.add_argument('--url-env',default='DATABASE_URL',help='Name of the variable containing the connection URL')
    parser.add_argument('--docker',action='store_true',help='Use official postgres:17-alpine client')
    args = parser.parse_args()
    if not os.getenv(args.url_env): parser.error('Database URL environment variable is empty')
    try:
        if args.action=='backup': backup(os.environ[args.url_env],args.file,docker=args.docker)
        else: restore_empty(os.environ[args.url_env],args.file,docker=args.docker)
    except (ValueError,OSError,subprocess.SubprocessError,psycopg.Error):
        print('Database operation failed. Existing backups and destination data are preserved. Check the URL, archive, client and connectivity.',file=sys.stderr)
        return 1
    print('Private archive verified.' if args.action=='backup' else 'Archive restored into empty database.')
    return 0


if __name__=='__main__': raise SystemExit(main())
