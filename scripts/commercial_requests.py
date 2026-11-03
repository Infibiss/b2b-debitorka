"""Private SSH/operator queue for commercial and deletion requests. Sends no mail."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import uuid

from psycopg import Error as PostgreSQLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.database import Config, database
from server.models import single_line

KINDS = ('demo', 'custom', 'deletion')
STATES = ('pending', 'handled', 'all')
CONTACT_FIELDS = ('name', 'email', 'company', 'note', 'tenant_id')
QUEUE_SQL = '''
SELECT q.*,COALESCE(h.status,'pending') AS status,h.owner,h.reference,h.handled_at
FROM (
 SELECT id,kind,created_at,name,email,company,note,NULL AS tenant_id FROM commercial_requests
 UNION ALL
 SELECT r.id,'deletion' AS kind,r.created_at,u.name,u.email,t.company,'' AS note,r.tenant_id
 FROM commercial_deletion_requests r
 JOIN users u ON u.id=r.created_by AND u.tenant_id=r.tenant_id
 JOIN tenants t ON t.id=r.tenant_id
) q LEFT JOIN commercial_request_handling h ON h.request_id=q.id AND h.kind=q.kind
'''


def check_database(config):
    # Never initialize schemas or accidentally create a database at a typo path.
    if not config.database_url and not Path(config.database_path).expanduser().is_file():
        raise ValueError('Configured database does not exist; run against the existing application database')


def list_requests(config, *, kind='all', state='pending', limit=50, include_contact=False):
    check_database(config)
    if kind not in (*KINDS, 'all') or state not in STATES or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('Invalid queue filter or limit; limit must be 1–500')
    clauses, values = [], []
    if kind != 'all':
        clauses.append('q.kind=?')
        values.append(kind)
    if state != 'all':
        clauses.append("COALESCE(h.status,'pending')=?")
        values.append(state)
    query = QUEUE_SQL + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY q.created_at,q.id LIMIT ?'
    with database(config) as c:
        rows = c.execute(query, (*values, limit + 1)).fetchall()
    fields = ('id', 'kind', 'created_at', 'status', 'owner', 'reference', 'handled_at')
    if include_contact:
        fields += CONTACT_FIELDS
    return {'items': [{key: row[key] for key in fields} for row in rows[:limit]], 'has_more': len(rows) > limit}


def mark_handled(config, *, kind, request_id, owner, reference):
    check_database(config)
    if kind not in KINDS:
        raise ValueError('Select an exact request kind')
    try:
        if str(uuid.UUID(request_id)) != request_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Supply the full canonical request UUID') from None
    owner, reference = single_line(owner), single_line(reference)
    if not 1 <= len(owner) <= 200 or not 1 <= len(reference) <= 1000:
        raise ValueError('Owner and reference are required (maximum 200 and 1000 characters)')
    with database(config, write=True) as c:
        if kind == 'deletion':
            found = c.execute('SELECT id FROM commercial_deletion_requests WHERE id=?', (request_id,)).fetchone()
        else:
            found = c.execute('SELECT id FROM commercial_requests WHERE id=? AND kind=?', (request_id, kind)).fetchone()
        if not found:
            raise ValueError('Request not found for this kind')
        existing = c.execute('SELECT * FROM commercial_request_handling WHERE request_id=? AND kind=?', (request_id, kind)).fetchone()
        if existing and (existing['owner'] != owner or existing['reference'] != reference):
            raise ValueError('Handling already recorded; existing owner/reference cannot be overwritten')
        if not existing:
            stamp = datetime.now(timezone.utc).isoformat(timespec='microseconds')
            c.execute("INSERT INTO commercial_request_handling VALUES(?,?,'handled',?,?,?)", (request_id, kind, owner, reference, stamp))
        row = c.execute('SELECT request_id AS id,kind,status,owner,reference,handled_at FROM commercial_request_handling WHERE request_id=? AND kind=?', (request_id, kind)).fetchone()
        return dict(row)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    queue = commands.add_parser('list', help='List the private queue; contact information is opt-in')
    queue.add_argument('--kind', choices=(*KINDS, 'all'), default='all')
    queue.add_argument('--state', choices=STATES, default='pending')
    queue.add_argument('--limit', type=int, default=50)
    queue.add_argument('--include-contact', action='store_true', help='Print private contact details to stdout; use only in an authorized SSH session')
    handled = commands.add_parser('mark-handled', help='Record a manual disposition/ticket reference; does not contact or delete')
    handled.add_argument('--kind', choices=KINDS, required=True)
    handled.add_argument('--request', required=True, help='Full request UUID')
    handled.add_argument('--owner', required=True, help='Responsible operator identifier; no secrets')
    handled.add_argument('--reference', required=True, help='Existing internal ticket/disposition reference; no secrets or message content')
    args = parser.parse_args(argv)
    try:
        config = Config.from_environment()
        if args.command == 'list':
            result = list_requests(config, kind=args.kind, state=args.state, limit=args.limit, include_contact=args.include_contact)
        else:
            result = mark_handled(config, kind=args.kind, request_id=args.request, owner=args.owner, reference=args.reference)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, RuntimeError, PostgreSQLError):
        # Database errors may contain credentials or customer values. Do not
        # dump SQL, DSNs, source rows or traceback into shared terminal logs.
        print('Queue unavailable. Check the existing application database, schema and private environment configuration.', file=sys.stderr)
        return 1
    # ASCII JSON escapes user-provided terminal controls and bidi characters.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
