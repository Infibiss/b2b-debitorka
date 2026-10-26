"""Fixed environment SMTP connector; never accepts client-supplied hosts."""
import hmac
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


def smtp_configured(tenant_id):
    bound = os.getenv('SMTP_TENANT_ID', '')
    return bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM') and bound and hmac.compare_digest(tenant_id, bound))


def message_id(job):
    return '<' + job['id'] + '@' + os.environ['SMTP_FROM'].rsplit('@', 1)[-1] + '>'


def send_email(job, settings):
    if not smtp_configured(job['tenant_id']):
        raise ValueError('SMTP tenant binding unavailable')
    sender = os.environ['SMTP_FROM']
    mail = EmailMessage()
    mail['Subject'], mail['To'] = job['subject'], job['recipient']
    mail['From'] = formataddr((settings['sender_name'], sender))
    if settings['reply_to']: mail['Reply-To'] = settings['reply_to']
    mail['Message-ID'] = message_id(job)
    mail.set_content(job['body'])
    secure = ssl.create_default_context()
    use_ssl = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
    options = dict(timeout=10)
    if use_ssl: options['context'] = secure
    cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with cls(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT', '587')), **options) as smtp:
        if not use_ssl and os.getenv('SMTP_USE_TLS', 'true').lower() == 'true':
            smtp.starttls(context=secure)
        if os.getenv('SMTP_USER'):
            smtp.login(os.environ['SMTP_USER'], os.getenv('SMTP_PASSWORD', ''))
        if smtp.send_message(mail):
            raise smtplib.SMTPException('Recipient rejected')
