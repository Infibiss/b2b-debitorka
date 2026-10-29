"""Service mail recovery and operator-assisted tenant mail setup."""
import hashlib
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import Field, field_validator

from .models import Input, Login, valid_email

SCHEMA = '''
CREATE TABLE IF NOT EXISTS password_resets (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS password_resets_user ON password_resets(user_id,created_at);
CREATE TABLE IF NOT EXISTS mail_setup_requests (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), id TEXT NOT NULL UNIQUE,
 email TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mail_setup_assignments (
 request_id TEXT PRIMARY KEY REFERENCES mail_setup_requests(id),
 owner TEXT NOT NULL DEFAULT '', verified_at TEXT, verification_reference TEXT NOT NULL DEFAULT ''
);
'''


def initialize_schema(connection):
    for statement in SCHEMA.split(';'):
        if statement.strip():
            connection.execute(statement)


class RecoveryRequest(Input):
    email: str = Field(max_length=254)

    @field_validator('email')
    @classmethod
    def mailbox(cls, value):
        return valid_email(value)


class ResetPassword(Input):
    model_config = Login.model_config
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=12, max_length=128)


def recovery_configured():
    return bool(os.getenv('AUTH_SMTP_HOST') and os.getenv('AUTH_SMTP_FROM'))


def send_recovery(email, link):
    mail = EmailMessage()
    mail['Subject'] = 'Восстановление доступа к Mandato'
    mail['From'] = os.environ['AUTH_SMTP_FROM']
    mail['To'] = email
    mail.set_content(f'Для смены пароля откройте ссылку в течение 30 минут:\n{link}\n\nЕсли вы не запрашивали смену пароля, проигнорируйте письмо.')
    use_ssl = os.getenv('AUTH_SMTP_USE_SSL', 'false').lower() == 'true'
    cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    kwargs = {'timeout': 15}
    if use_ssl:
        kwargs['context'] = ssl.create_default_context()
    with cls(os.environ['AUTH_SMTP_HOST'], int(os.getenv('AUTH_SMTP_PORT', '465' if use_ssl else '587')), **kwargs) as smtp:
        if not use_ssl:
            smtp.starttls(context=ssl.create_default_context())
        if os.getenv('AUTH_SMTP_USER'):
            smtp.login(os.environ['AUTH_SMTP_USER'], os.getenv('AUTH_SMTP_PASSWORD', ''))
        if smtp.send_message(mail):
            raise smtplib.SMTPException('Recipient rejected')


def create_router(ctx):
    router = APIRouter(prefix='/api')

    @router.get('/auth/help')
    def help_settings():
        address = os.getenv('SUPPORT_EMAIL', '')
        try:
            address = valid_email(address) if address else ''
        except ValueError:
            address = ''
        return {'recovery_available': recovery_configured() and bool(ctx.config.app_url), 'support_email': address}

    def deliver_recovery(email):
        # Background work keeps the public response identical for known/unknown addresses.
        with ctx.database(ctx.config, write=True) as c:
            user = c.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if not user:
                return
            recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            if c.execute('SELECT token_hash FROM password_resets WHERE user_id=? AND created_at>?', (user['id'], recent)).fetchone():
                return
            token = secrets.token_urlsafe(48)
            hashed = hashlib.sha256(token.encode()).hexdigest()
            c.execute('DELETE FROM password_resets WHERE expires_at<=?', (ctx.now(),))
            c.execute('INSERT INTO password_resets VALUES(?,?,?,?)', (hashed, user['id'], (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(), ctx.now()))
        try:
            send_recovery(email, ctx.config.app_url.rstrip('/') + '/app#reset=' + token)
        except (OSError, smtplib.SMTPException, ValueError):
            # Never log tokens or addresses. Failed tokens cannot be used.
            with ctx.database(ctx.config, write=True) as c:
                c.execute('DELETE FROM password_resets WHERE token_hash=?', (hashed,))

    @router.post('/auth/recovery', status_code=202)
    def recover(data: RecoveryRequest, tasks: BackgroundTasks):
        if not recovery_configured() or not ctx.config.app_url:
            ctx.problem(503, 'Сервис восстановления пока не подключён. Обратитесь к администратору вашей организации через раздел помощи.')
        tasks.add_task(deliver_recovery, data.email)
        return {'detail': 'Если аккаунт существует, письмо со ссылкой придёт на указанный адрес. Проверьте также папку «Спам». Ссылка действует 30 минут.'}

    @router.post('/auth/reset-password')
    def reset_password(data: ResetPassword):
        from .main import PASSWORDS, COOKIE_NAME
        hashed = hashlib.sha256(data.token.encode()).hexdigest()
        # Hash before acquiring the write lock. Consumption and revocation are atomic.
        password_hash = PASSWORDS.hash(data.password)
        with ctx.database(ctx.config, write=True) as c:
            row = c.execute('DELETE FROM password_resets WHERE token_hash=? AND expires_at>? RETURNING user_id', (hashed, ctx.now())).fetchone()
            if not row:
                ctx.problem(400, 'Ссылка недействительна или истекла. Запросите новую.')
            c.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash, row['user_id']))
            c.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))
            c.execute('DELETE FROM password_resets WHERE user_id=?', (row['user_id'],))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE_NAME, path='/', secure=ctx.config.secure_cookies, httponly=True, samesite='lax')
        return response

    @router.get('/mail/setup')
    def mail_setup(user=Depends(ctx.get_user)):
        from .main import smtp_configuration
        with ctx.database(ctx.config) as c:
            row = c.execute('SELECT r.id,r.email,r.status,r.note,r.created_at,r.updated_at,a.owner,a.verified_at,a.verification_reference FROM mail_setup_requests r LEFT JOIN mail_setup_assignments a ON a.request_id=r.id WHERE r.tenant_id=?', (user['tenant_id'],)).fetchone()
        return {'connected': smtp_configuration(user['tenant_id']), 'request': dict(row) if row else None, 'can_request': user['role'] == 'manager'}

    @router.post('/mail/setup', status_code=201)
    def request_setup(data: RecoveryRequest, user=Depends(ctx.get_user)):
        if user['role'] != 'manager':
            ctx.problem(403, 'Подключение почты запрашивает руководитель')
        with ctx.database(ctx.config, write=True) as c:
            stamp = ctx.now()
            c.execute("INSERT INTO mail_setup_requests VALUES(?,?,?,'pending','',?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET email=excluded.email,status='pending',note='',updated_at=excluded.updated_at", (user['tenant_id'], ctx.identifier(), data.email, user['id'], stamp, stamp))
            row = c.execute('SELECT id FROM mail_setup_requests WHERE tenant_id=?', (user['tenant_id'],)).fetchone()
            c.execute("UPDATE mail_setup_assignments SET verified_at=NULL,verification_reference='' WHERE request_id=?", (row['id'],))
        return mail_setup(user)

    return router
