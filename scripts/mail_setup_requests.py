"""Operator queue for SMTP setup. Never accepts or prints mailbox passwords."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.database import Config, database, initialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', help='Full request ID to update')
    parser.add_argument('--status', choices=['pending', 'in_progress', 'completed'])
    parser.add_argument('--note', default='', help='Client-visible next step; no passwords')
    parser.add_argument('--owner', default='', help='Responsible operator name, visible to client')
    parser.add_argument('--verified-send-reference', default='', help='Evidence of a successful test delivery already performed by operator')
    args = parser.parse_args()
    if bool(args.request) != bool(args.status):
        parser.error('--request and --status must be supplied together')
    config = Config.from_environment()
    initialize(config)
    with database(config, write=bool(args.request)) as c:
        if args.request:
            if not args.note or len(args.note) > 2000:
                parser.error('Provide a client-visible --note of 1–2000 characters')
            row = c.execute('SELECT tenant_id FROM mail_setup_requests WHERE id=?', (args.request,)).fetchone()
            if not row:
                parser.error('Request not found')
            if args.status in ('in_progress', 'completed') and not args.owner.strip():
                parser.error('Assign a responsible operator with --owner')
            if len(args.owner) > 200 or len(args.verified_send_reference) > 2000:
                parser.error('Owner/reference is too long')
            if args.status == 'completed':
                if not args.verified_send_reference.strip():
                    parser.error('Provide --verified-send-reference for an already verified test delivery')
                from server.main import smtp_configuration
                if not smtp_configuration(row['tenant_id']):
                    parser.error('Configure SMTP and bind SMTP_TENANT_ID before completing the request')
            c.execute('UPDATE mail_setup_requests SET status=?,note=?,updated_at=? WHERE id=?', (args.status, args.note, datetime.now(timezone.utc).isoformat(), args.request))
            c.execute("INSERT INTO mail_setup_assignments(request_id,owner,verified_at,verification_reference) VALUES(?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET owner=excluded.owner,verified_at=excluded.verified_at,verification_reference=excluded.verification_reference", (args.request, args.owner.strip(), datetime.now(timezone.utc).isoformat() if args.status == 'completed' else None, args.verified_send_reference.strip() if args.status == 'completed' else ''))
        rows = c.execute('SELECT r.id,r.tenant_id,t.company,r.email,r.status,r.note,r.updated_at FROM mail_setup_requests r JOIN tenants t ON t.id=r.tenant_id ORDER BY r.created_at').fetchall()
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
