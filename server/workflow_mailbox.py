"""Bounded private IMAP SSL reply collector with durable UID receipts.

Only exact In-Reply-To matches and registered, DMARC-verified senders reach the
agent. The configured MTA must remove forged Authentication-Results claiming
its trusted authserv-id before inserting its own authentication result.
"""
import hashlib
import imaplib
import os
import re
import ssl
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from types import SimpleNamespace

from . import finance as f
from .database import database
from .models import valid_email

MAX_BYTES = 65536
SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS workflow_message_ids (
 message_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,job_id TEXT NOT NULL UNIQUE,
 FOREIGN KEY(job_id,tenant_id) REFERENCES workflow_jobs(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS workflow_mailbox_receipts (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),account_key TEXT NOT NULL,
 uid_validity TEXT NOT NULL,mail_uid TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,
 incoming_id TEXT,created_at TEXT NOT NULL,UNIQUE(account_key,uid_validity,mail_uid)
);
CREATE TABLE IF NOT EXISTS workflow_mailbox_state (
 account_key TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),status TEXT NOT NULL,
 checked_at TEXT NOT NULL,reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_mailbox_reviews (
 receipt_id TEXT PRIMARY KEY REFERENCES workflow_mailbox_receipts(id),tenant_id TEXT NOT NULL REFERENCES tenants(id),
 reason TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL
);
'''


def initialize_schema(c):
    for statement in SCHEMA_SQL.split(';'):
        if statement.strip(): c.execute(statement)


def account_key():
    # No password or public mailbox address is stored in API-visible status.
    value = '|'.join(os.getenv(key, '') for key in ('IMAP_TENANT_ID', 'IMAP_HOST', 'IMAP_USER', 'IMAP_FOLDER'))
    return hashlib.sha256(value.encode()).hexdigest()


def configured(tenant=None):
    bound = os.getenv('IMAP_TENANT_ID', '')
    return bool(bound and (tenant is None or tenant == bound) and all(os.getenv(key) for key in ('IMAP_HOST', 'IMAP_USER', 'IMAP_PASSWORD', 'IMAP_AUTH_SERV_ID')))


def mailbox_status(c, tenant):
    key = account_key()
    row = c.execute('SELECT status,checked_at,reason FROM workflow_mailbox_state WHERE tenant_id=? AND account_key=?', (tenant, key)).fetchone()
    issues = c.execute("SELECT COUNT(*) AS n FROM workflow_mailbox_receipts WHERE tenant_id=? AND account_key=? AND status IN('issue','processing')", (tenant, key)).fetchone()['n']
    issue_items = [dict(row) for row in c.execute("SELECT id,status,reason,created_at FROM workflow_mailbox_receipts WHERE tenant_id=? AND account_key=? AND status IN('issue','processing') ORDER BY created_at DESC LIMIT 50", (tenant, key))]
    return dict(configured=configured(tenant), status=row['status'] if row else 'not_checked', checked_at=row['checked_at'] if row else None,
                reason=row['reason'] if row else None, issues_count=issues, issues=issue_items)


def mailbox_blocked(c, tenant):
    if not configured(tenant): return False
    row = c.execute('SELECT * FROM workflow_mailbox_state WHERE tenant_id=? AND account_key=?', (tenant, account_key())).fetchone()
    interrupted = c.execute("SELECT id FROM workflow_mailbox_receipts WHERE tenant_id=? AND account_key=? AND status='processing' LIMIT 1", (tenant, account_key())).fetchone()
    # A configured but unavailable mailbox must not silently miss a dispute
    # while reminders continue. An operator can disable the mailbox connector
    # explicitly if another authenticated ingestion channel is in service.
    return bool(interrupted) or not row or row['status'] != 'ok' or row['checked_at'] < (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()


def open_mailbox():
    return imaplib.IMAP4_SSL(os.environ['IMAP_HOST'], int(os.getenv('IMAP_PORT', '993')),
                            ssl_context=ssl.create_default_context(), timeout=10)


def _state(config, tenant, key, status, reason=''):
    with database(config, write=True) as c:
        c.execute('''INSERT INTO workflow_mailbox_state VALUES(?,?,?,?,?) ON CONFLICT(account_key)
            DO UPDATE SET status=excluded.status,checked_at=excluded.checked_at,reason=excluded.reason''',
            (key, tenant, status, f.timestamp(), reason))


def _receipt(config, tenant, key, validity, uid, status, reason, incoming=None):
    with database(config, write=True) as c:
        c.execute('''INSERT INTO workflow_mailbox_receipts VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(account_key,uid_validity,mail_uid) DO UPDATE SET status=excluded.status,reason=excluded.reason,incoming_id=excluded.incoming_id''',
            (f.uid(), tenant, key, validity, uid, status, reason, incoming, f.timestamp()))


def _author(msg):
    parsed = getaddresses(msg.get_all('From', []))
    if len(parsed) != 1: raise ValueError('ambiguous_sender')
    try: sender = valid_email(parsed[0][1])
    except ValueError: raise ValueError('invalid_sender') from None
    trusted = os.environ['IMAP_AUTH_SERV_ID'].lower()
    auth = [str(value) for value in msg.get_all('Authentication-Results', []) if str(value).split(';', 1)[0].strip().lower() == trusted]
    if len(auth) != 1: raise ValueError('sender_authentication_required')
    text = auth[0].lower()
    domain = sender.rsplit('@', 1)[-1]
    if not re.search(r'(?:^|;)\s*dmarc\s*=\s*pass\b', text) or not re.search(r'\bheader\.from\s*=\s*' + re.escape(domain) + r'(?=\s|;|$)', text):
        raise ValueError('sender_authentication_required')
    return sender


def _envelope(config, tenant, msg):
    sender = _author(msg)
    reply = str(msg.get('In-Reply-To', '')).strip()
    if not re.fullmatch(r'<[^<>\s]{1,250}>', reply): raise ValueError('reply_not_correlated')
    with database(config) as c:
        row = c.execute('''SELECT j.* FROM workflow_message_ids m JOIN workflow_jobs j ON j.id=m.job_id AND j.tenant_id=m.tenant_id
            WHERE m.message_id=? AND m.tenant_id=? AND j.status IN('sent','unknown','claimed')''', (reply, tenant)).fetchone()
        if not row: raise ValueError('reply_not_correlated')
        inv = f.load_invoice(c, tenant, row['invoice_id'])
        if sender != row['recipient'] or sender != inv['email']:
            raise ValueError('sender_mismatch')
        invoice_id = row['invoice_id']
    return invoice_id, sender


def _parse(config, tenant, raw):
    if len(raw) > MAX_BYTES: raise ValueError('message_too_large')
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    invoice_id, sender = _envelope(config, tenant, msg)
    body = msg.get_body(preferencelist=('plain',))
    if body is None: raise ValueError('plain_text_required')
    text = body.get_content()
    if not isinstance(text, str) or not 3 <= len(text.strip()) <= 12000:
        raise ValueError('text_size_invalid')
    return invoice_id, sender, text.strip()


def _hold_unreadable(config, tenant, raw, source_key):
    from .workflow import case_items, _exception
    try:
        if len(raw) > MAX_BYTES: return
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        invoice_id, _ = _envelope(config, tenant, msg)
    except (ValueError, TypeError, RecursionError):
        return
    with database(config, write=True) as c:
        item = next(value for value in case_items(c, tenant) if invoice_id in value['invoice_ids'])
        _exception(c, tenant, item['id'], invoice_id, 'incoming_unreadable', 'Получен подтверждённый ответ, который не удалось прочитать. Проверьте письмо вручную перед новым контактом.', source_key)


def _received_at(metadata):
    match = re.search(rb'INTERNALDATE\s+"([^"]{1,60})"', metadata, re.I)
    if not match: return None
    # IMAP uses fixed English month names independently of the server locale.
    parts = re.fullmatch(rb' ?([0-9]{1,2})-([A-Za-z]{3})-([0-9]{4}) ([0-9]{2}):([0-9]{2}):([0-9]{2}) ([+-])([0-9]{2})([0-9]{2})', match[1])
    if not parts: raise ValueError('invalid_received_time')
    day, month, year, hour, minute, second, sign, offset_h, offset_m = parts.groups()
    months = {name: index + 1 for index, name in enumerate((b'jan', b'feb', b'mar', b'apr', b'may', b'jun', b'jul', b'aug', b'sep', b'oct', b'nov', b'dec'))}
    offset = (int(offset_h) * 60 + int(offset_m)) * (-1 if sign == b'-' else 1)
    return datetime(int(year), months[month.lower()], int(day), int(hour), int(minute), int(second), tzinfo=timezone(timedelta(minutes=offset)))


def poll_once(config):
    from .workflow import InboundInput, ingest_verified
    tenant = os.getenv('IMAP_TENANT_ID', '')
    if not configured(): return dict(status='unconfigured', processed=0, issues=0)
    key, box, processed, issues = account_key(), None, 0, 0
    with database(config) as c:
        if not c.execute('SELECT id FROM tenants WHERE id=?', (tenant,)).fetchone():
            return dict(status='tenant_unavailable', processed=0, issues=0)
    try:
        box = open_mailbox()
        if box.login(os.environ['IMAP_USER'], os.environ['IMAP_PASSWORD'])[0] != 'OK': raise ValueError('mailbox_authentication')
        if box.select(os.getenv('IMAP_FOLDER', 'INBOX'), readonly=False)[0] != 'OK': raise ValueError('mailbox_folder')
        _, values = box.response('UIDVALIDITY')
        validity = values[0].decode('ascii')
        if not re.fullmatch(r'[0-9]{1,20}', validity): raise ValueError('mailbox_uid_validity')
        with database(config) as c:
            last_uid = c.execute('SELECT MAX(CAST(mail_uid AS BIGINT)) AS last_uid FROM workflow_mailbox_receipts WHERE account_key=? AND uid_validity=?', (key, validity)).fetchone()['last_uid'] or 0
        status, rows = box.uid('search', None, 'UID', str(last_uid + 1) + ':*')
        if status != 'OK' or not rows or not isinstance(rows[0], bytes) or len(rows[0]) > 100000: raise ValueError('mailbox_search')
        uids = rows[0].split()
        if any(not re.fullmatch(rb'[0-9]{1,20}', uid) for uid in uids): raise ValueError('mailbox_uid')
        pending = sorted({uid for uid in uids if int(uid) > last_uid}, key=int)
        backlog = len(pending) > 20
        pending = pending[:20]
        ctx = SimpleNamespace(config=config, database=database, identifier=f.uid, now=f.timestamp, event=f.emit)
        for uid in pending:
            # Reserve before provider work. A crash cannot repeat a paid call.
            _receipt(config, tenant, key, validity, uid.decode(), 'processing', 'processing_interrupted')
            raw = None
            try:
                status, metadata = box.uid('fetch', uid, '(RFC822.SIZE INTERNALDATE)')
                metadata = b' '.join(value for value in metadata if isinstance(value, bytes))
                match = re.search(rb'RFC822.SIZE\s+([0-9]+)', metadata)
                if status != 'OK' or not match: raise ValueError('message_size_unavailable')
                if int(match[1]) > MAX_BYTES:
                    status, header_data = box.uid('fetch', uid, '(BODY.PEEK[HEADER.FIELDS (FROM IN-REPLY-TO AUTHENTICATION-RESULTS)]<0.8192>)')
                    headers = [value[1] for value in header_data if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], bytes)]
                    if status == 'OK' and len(headers) == 1 and len(headers[0]) <= 8192:
                        raw = headers[0]
                    raise ValueError('message_too_large')
                status, payload = box.uid('fetch', uid, '(BODY.PEEK[])')
                bodies = [value[1] for value in payload if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], bytes)]
                if status != 'OK' or len(bodies) != 1: raise ValueError('message_body_unavailable')
                raw = bodies[0]
                invoice_id, sender, text = _parse(config, tenant, raw)
                # IMAP UIDVALIDITY may change after a mailbox rebuild. Exact
                # original bytes remain the same durable incoming identity.
                source_id = 'mail:' + hashlib.sha256(key.encode() + bodies[0]).hexdigest()
                data = InboundInput(invoice_id=invoice_id, source='imap', source_id=source_id, sender=sender, text=text, received_at=_received_at(metadata))
                result = ingest_verified(ctx, data, tenant, 'imap')
                _receipt(config, tenant, key, validity, uid.decode(), 'processed', '', result['id'])
                processed += 1
                # Never mark read before source and outcome are durably stored.
                box.uid('store', uid, '+FLAGS.SILENT', '(\\Seen)')
            except ValueError as error:
                allowed = {'ambiguous_sender', 'invalid_sender', 'sender_authentication_required', 'reply_not_correlated', 'sender_mismatch', 'plain_text_required', 'text_size_invalid', 'message_size_unavailable', 'message_too_large', 'message_body_unavailable'}
                reason = str(error) if str(error) in allowed else 'invalid_message'
                if raw is not None:
                    _hold_unreadable(config, tenant, raw, 'imap-unreadable:' + key + ':' + validity + ':' + uid.decode())
                _receipt(config, tenant, key, validity, uid.decode(), 'issue', reason)
                issues += 1
        final_status = 'backlog' if backlog else 'ok'
        _state(config, tenant, key, final_status)
        return dict(status=final_status, processed=processed, issues=issues)
    except Exception:
        _state(config, tenant, key, 'error', 'mailbox_sync_failed')
        return dict(status='error', processed=processed, issues=issues)
    finally:
        if box:
            try: box.logout()
            except Exception: pass
