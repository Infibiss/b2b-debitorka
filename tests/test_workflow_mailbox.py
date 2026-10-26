"""Private mailbox polling verifies reply correlation before any agent work."""
from email.message import EmailMessage
from datetime import datetime, timezone

from tests.test_api import client
from tests.test_workflow import configure, provider, workflow_environment
from server.database import database


class Mailbox:
    def __init__(self, messages, *, validity=b'77'):
        self.messages, self.validity, self.seen = messages, validity, []
        self.received_at = datetime.now(timezone.utc).replace(microsecond=0)
    def login(self, user, password): return 'OK', [b'authenticated']
    def select(self, folder, readonly=False): return 'OK', [str(len(self.messages)).encode()]
    def response(self, kind): return 'UIDVALIDITY', [self.validity]
    def uid(self, command, *args):
        if command == 'search': return 'OK', [b' '.join(self.messages)]
        if command == 'fetch':
            key, fields = args
            raw = self.messages[key]
            if 'RFC822.SIZE' in fields: return 'OK', [b'1 (UID ' + key + b' RFC822.SIZE ' + str(len(raw)).encode() + b' INTERNALDATE "' + self.received_at.strftime('%d-%b-%Y %H:%M:%S %z').encode() + b'")']
            if fields.startswith('(BODY.PEEK[HEADER.FIELDS'):
                return 'OK', [(b'headers', raw.split(b'\n\n', 1)[0][:8192])]
            assert fields == '(BODY.PEEK[])'
            return 'OK', [(b'1 (UID ' + key + b' BODY[] {' + str(len(raw)).encode() + b'}', raw), b')']
        if command == 'store':
            self.seen.append(args[0])
            return 'OK', [b'done']
        raise AssertionError(command)
    def logout(self): pass


def mail(sender, message_id, text='Пришлите акт сверки', *, authentication=True):
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'], msg['In-Reply-To'] = sender, 'finance@example.ru', 'Re: reminder', message_id
    if authentication:
        msg['Authentication-Results'] = 'trusted.mx; dmarc=pass header.from=' + sender.rsplit('@', 1)[-1]
    msg.set_content(text)
    return msg.as_bytes()


def configured(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    monkeypatch.setattr(workflow, 'send_email', lambda *args: None)
    workflow.run_once(client.app.state.config)
    with database(client.app.state.config) as c:
        job = c.execute('SELECT id FROM workflow_jobs').fetchone()
    for key, value in dict(IMAP_HOST='imap.example.ru', IMAP_USER='finance@example.ru', IMAP_PASSWORD='test-never-sent', IMAP_TENANT_ID=tenant, IMAP_AUTH_SERV_ID='trusted.mx').items():
        monkeypatch.setenv(key, value)
    return inv, case, tenant, '<' + job['id'] + '@example.ru>'


def test_correlated_authenticated_reply_is_ingested_once_and_marked_seen_after_persistence(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    box = Mailbox({b'1': mail(inv['email'], message_id)})
    calls = []
    original_store = box.uid
    def uid(command, *args):
        if command == 'store':
            with database(client.app.state.config) as c:
                assert c.execute('SELECT id FROM workflow_inbound').fetchone()
        return original_store(command, *args)
    box.uid = uid
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    assert workflow_mailbox.poll_once(client.app.state.config)['processed'] == 1
    assert workflow_mailbox.poll_once(client.app.state.config)['processed'] == 0
    assert box.seen == [b'1']
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['messages'][0]['status'] == 'received'
    assert detail['balance'] == inv['balance']


def test_sender_mismatch_or_missing_domain_authentication_never_reaches_agent(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    box = Mailbox({b'1': mail('attacker@example.ru', message_id), b'2': mail(inv['email'], message_id, authentication=False)})
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    result = workflow_mailbox.poll_once(client.app.state.config)
    assert result['processed'] == 0 and result['issues'] == 2
    assert box.seen == []
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) AS n FROM workflow_inbound').fetchone()['n'] == 0
        assert c.execute('SELECT COUNT(*) AS n FROM workflow_mailbox_receipts').fetchone()['n'] == 2


def test_unknown_reply_and_oversized_mail_are_persisted_as_mailbox_issues(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    box = Mailbox({b'1': mail(inv['email'], '<unknown@example.ru>'), b'2': b'x' * 70000})
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    assert workflow_mailbox.poll_once(client.app.state.config)['issues'] == 2
    status = client.get('/api/workflow/mailbox').json()
    assert status['configured'] and status['issues_count'] == 2
    assert 'password' not in str(status).lower()


def test_private_polling_uses_existing_graph_for_unambiguous_dispute(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    text = 'Не согласны с долгом, спор по поставке'
    provider(monkeypatch, tenant, 'dispute', text)
    box = Mailbox({b'1': mail(inv['email'], message_id, text)})
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    assert workflow_mailbox.poll_once(client.app.state.config)['processed'] == 1
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['stage'] == 'disputed'
    assert detail['balance'] == inv['balance']


def test_mailbox_failure_pauses_bound_tenant_reminders_and_keeps_error_private(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    def fail(): raise TimeoutError('secret-password-must-not-leak')
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', fail)
    assert workflow_mailbox.poll_once(client.app.state.config)['status'] == 'error'
    status = client.get('/api/workflow/mailbox').json()
    assert status['reason'] == 'mailbox_sync_failed'
    assert 'secret-password' not in str(status)
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['queue'] == 'needs_decision'


def test_uid_validity_reset_does_not_repeat_same_original_mail(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    box = Mailbox({b'1': mail(inv['email'], message_id)})
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    assert workflow_mailbox.poll_once(client.app.state.config)['processed'] == 1
    box.validity = b'78'
    assert workflow_mailbox.poll_once(client.app.state.config)['processed'] == 1
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) AS n FROM workflow_inbound').fetchone()['n'] == 1


def test_interrupted_mail_processing_stays_paused_until_audited_operator_resolution(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    box = Mailbox({b'1': mail(inv['email'], message_id)})
    ordinary = box.uid
    def fail_fetch(command, *args):
        if command == 'fetch': raise TimeoutError('transient private error')
        return ordinary(command, *args)
    box.uid = fail_fetch
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    assert workflow_mailbox.poll_once(client.app.state.config)['status'] == 'error'
    box.uid = ordinary
    assert workflow_mailbox.poll_once(client.app.state.config)['status'] == 'ok'
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['queue'] == 'needs_decision'
    issue = client.get('/api/workflow/mailbox').json()['issues'][0]
    response = client.post('/api/workflow/mailbox/issues/' + issue['id'] + '/resolve', json={'resolution': 'Проверили письмо вручную, ответ передан бухгалтеру'})
    assert response.status_code == 200, response.text
    assert client.get('/api/workflow/cases/' + case['id']).json()['queue'] == 'in_progress'


def test_polling_uses_durable_uid_range_not_unseen_and_pauses_for_backlog(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    box = Mailbox({str(i).encode(): mail(inv['email'], '<unrelated-' + str(i) + '@example.ru>') for i in range(1, 23)})
    ordinary = box.uid
    def uid(command, *args):
        if command == 'search': assert args == (None, 'UID', '1:*') or args == (None, 'UID', '21:*')
        return ordinary(command, *args)
    box.uid = uid
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    first = workflow_mailbox.poll_once(client.app.state.config)
    assert first['status'] == 'backlog' and first['issues'] == 20
    assert client.get('/api/workflow/cases/' + case['id']).json()['queue'] == 'needs_decision'
    second = workflow_mailbox.poll_once(client.app.state.config)
    assert second['status'] == 'ok' and second['issues'] == 2


def test_imap_internaldate_is_persisted_and_passed_to_graph_not_untrusted_date_header(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    text = 'Обещаем оплатить 100 рублей завтра'
    received = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)
    from server.business_time import business_timezone
    expected_due = str((received.astimezone(business_timezone()) + timedelta(days=1)).date())
    provider(monkeypatch, tenant, 'promise', text, amount=10000, due_date=expected_due)
    box = Mailbox({b'1': mail(inv['email'], message_id, text)})
    ordinary = box.uid
    def uid(command, *args):
        if command == 'fetch' and 'RFC822.SIZE' in args[1]:
            return 'OK', [b'1 (UID 1 RFC822.SIZE ' + str(len(box.messages[b'1'])).encode() + b' INTERNALDATE "' + received.strftime('%d-%b-%Y %H:%M:%S %z').encode() + b'")']
        return ordinary(command, *args)
    box.uid = uid
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    assert workflow_mailbox.poll_once(client.app.state.config)['processed'] == 1
    with database(client.app.state.config) as c:
        proposal = c.execute('SELECT received_at FROM agent_proposals WHERE tenant_id=?', (tenant,)).fetchone()
        assert datetime.fromisoformat(proposal['received_at']) == received
        stored = c.execute('SELECT received_at FROM workflow_inbound_receipts').fetchone()
        assert datetime.fromisoformat(stored['received_at']) == received


def test_unreadable_authenticated_correlated_reply_stops_case_until_review(client, monkeypatch):
    from server import workflow_mailbox
    inv, case, tenant, message_id = configured(client, monkeypatch)
    msg = EmailMessage()
    msg['From'], msg['To'], msg['In-Reply-To'] = inv['email'], 'finance@example.ru', message_id
    msg['Authentication-Results'] = 'trusted.mx; dmarc=pass header.from=example.ru'
    msg.set_content('<p>Не согласны с долгом</p>', subtype='html')
    box = Mailbox({b'1': msg.as_bytes()})
    monkeypatch.setattr(workflow_mailbox, 'open_mailbox', lambda: box)
    assert workflow_mailbox.poll_once(client.app.state.config)['issues'] == 1
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['queue'] == 'needs_decision'
    assert detail['exceptions'][0]['kind'] == 'incoming_unreadable'
    assert detail['balance'] == inv['balance']
