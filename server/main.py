"""AgentPay HTTP API. Run with: python -m uvicorn server.main:app."""
import csv
import hashlib
import hmac
import io
import os
import secrets
import smtplib
import ssl
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .csv_import import parse_csv
from .business_time import business_today
from .database import Config, database, initialize
from . import llm
from .models import (ContactInput, CSVInput, DraftInput, InvoiceInput, Login, MessageInput,
                     PaymentInput, PromiseInput, Register, SettingsInput, StatusInput)

COOKIE_NAME = "agentpay_session"
PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = PASSWORDS.hash("dummy-verification-password-never-a-user")
PUBLIC_MESSAGE = ("id", "invoice_id", "subject", "body", "status", "recipient", "source", "created_at")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def identifier():
    return str(uuid.uuid4())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def problem(code, detail):
    raise HTTPException(code, detail)


class GuardMiddleware:
    """Bounded body and process-local limits. Proxy must enforce distributed limits."""

    def __init__(self, app, config):
        self.app, self.config = app, config
        self.buckets = defaultdict(deque)
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope["headers"]}
        method, path = scope["method"], scope["path"]
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            if self.config.app_url:
                expected = urlsplit(self.config.app_url)
                supplied = urlsplit(headers.get("origin", ""))
                if (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc):
                    return await JSONResponse({"detail": "Источник запроса не разрешён"}, 403)(scope, receive, send)
            try:
                declared = int(headers.get("content-length", "0"))
            except ValueError:
                return await JSONResponse({"detail": "Некорректный Content-Length"}, 400)(scope, receive, send)
            if declared > self.config.max_body_bytes:
                return await JSONResponse({"detail": "Размер запроса превышает 2 МБ"}, 413)(scope, receive, send)
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > self.config.max_body_bytes:
                    return await JSONResponse({"detail": "Размер запроса превышает 2 МБ"}, 413)(scope, receive, send)
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            original_receive = replay
        else:
            original_receive = receive
        if path.startswith("/api/"):
            ip = (scope.get("client") or ("unknown",))[0]
            group = "auth" if path in ("/api/auth/login", "/api/auth/register") else "api"
            limit = 15 if group == "auth" else 300
            key, clock = (ip, group), time.monotonic()
            with self.lock:
                # Remove stale keys as well as individual timestamps to bound memory.
                if len(self.buckets) > 10000:
                    self.buckets = defaultdict(deque, {k: v for k, v in self.buckets.items() if v and v[-1] > clock - 60})
                bucket = self.buckets[key]
                while bucket and bucket[0] <= clock - 60:
                    bucket.popleft()
                limited = len(bucket) >= limit
                if not limited:
                    bucket.append(clock)
            if limited:
                return await JSONResponse({"detail": "Слишком много запросов. Повторите через минуту."}, 429, headers={"Retry-After": "60"})(scope, receive, send)

        async def secured_send(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ])
                if path.startswith("/api/"):
                    response_headers.append((b"cache-control", b"no-store"))
                if self.config.production:
                    response_headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, original_receive, secured_send)


def event(connection, tenant_id, invoice_id, kind, title, detail=""):
    connection.execute(
        "INSERT INTO events(id,tenant_id,invoice_id,type,title,detail,created_at) VALUES(?,?,?,?,?,?,?)",
        (identifier(), tenant_id, invoice_id, kind, title, detail, now()),
    )


def invoice_row(connection, tenant_id, invoice_id):
    row = connection.execute("SELECT * FROM invoices WHERE id=? AND tenant_id=?", (invoice_id, tenant_id)).fetchone()
    if row is None:
        problem(404, "Счёт не найден")
    return row


def invoice_view(row):
    today = business_today()
    result = {key: row[key] for key in ("id", "company", "inn", "email", "number", "issued_on", "due_on", "amount", "paid_amount", "promise_date", "notes")}
    balance = row["amount"] - row["paid_amount"]
    days = max(0, (today - date.fromisoformat(row["due_on"])).days) if balance else 0
    status = "paid" if not balance else row["status"]
    if balance and status == "open" and row["promise_date"]:
        status = "promised"
    reasons = []
    broken = balance and row["promise_date"] and date.fromisoformat(row["promise_date"]) < today
    if days:
        reasons.append(f"Просрочка {days} дн.")
    if broken:
        reasons.append("Нарушено обещание оплаты")
    if balance >= 10_000_000 and days:
        reasons.append("Остаток от 100 000 ₽")
    priority = "high" if broken or days >= 30 or (balance >= 10_000_000 and days) else "medium" if days else "low"
    if status in ("paid", "disputed", "paused"):
        priority = "low"
        if status == "disputed":
            reasons.append("Спор: требуется решение сотрудника")
        elif status == "paused":
            reasons.append("Контакт приостановлен")
    result.update(balance=balance, days_overdue=days, status=status, priority=priority, priority_reasons=reasons)
    return result


def contactable(row):
    if row["paid_amount"] >= row["amount"]:
        problem(409, "Счёт оплачен: напоминание не требуется")
    if row["status"] in ("disputed", "paused"):
        problem(409, "Контакт приостановлен: сначала разрешите спор или снимите паузу")
    if not row["email"]:
        problem(409, "Для письма необходим email контрагента")


def message_row(connection, tenant_id, message_id):
    row = connection.execute("SELECT * FROM messages WHERE id=? AND tenant_id=?", (message_id, tenant_id)).fetchone()
    if row is None:
        problem(404, "Письмо не найдено")
    return row


def message_view(row):
    return {key: row[key] for key in PUBLIC_MESSAGE}


def money_text(amount):
    return f"{amount // 100:,}".replace(",", " ") + f",{amount % 100:02d}"


def smtp_configuration(tenant_id):
    host, sender = os.getenv("SMTP_HOST", ""), os.getenv("SMTP_FROM", "")
    bound_tenant = os.getenv("SMTP_TENANT_ID", "")
    return bool(host and sender and bound_tenant and hmac.compare_digest(tenant_id, bound_tenant))


def settings_view(connection, tenant_id):
    row = connection.execute("SELECT s.*,t.company FROM settings s JOIN tenants t ON t.id=s.tenant_id WHERE s.tenant_id=?", (tenant_id,)).fetchone()
    return {**{key: row[key] for key in ("company", "sender_name", "reply_to", "bank_details", "annual_rate", "cooldown_days")},
            "smtp_configured": smtp_configuration(tenant_id), "llm_configured": llm.configured()}


def create_session(connection, user, config, status=200):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    timestamp = datetime.now(timezone.utc)
    connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (timestamp.isoformat(),))
    connection.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (digest(token), user["id"], csrf, (timestamp + timedelta(days=7)).isoformat(), timestamp.isoformat()))
    response = JSONResponse({"user": {key: user[key] for key in ("id", "name", "company", "email")}, "csrf_token": csrf}, status)
    response.set_cookie(COOKIE_NAME, token, max_age=7 * 86400, httponly=True, secure=config.secure_cookies, samesite="lax", path="/")
    return response


def get_user(request: Request):
    raw_token = request.cookies.get(COOKIE_NAME, "")
    if not raw_token:
        problem(401, "Войдите в аккаунт")
    with database(request.app.state.config) as connection:
        user = connection.execute("""SELECT u.id,u.tenant_id,u.name,u.email,t.company,s.csrf_token
            FROM sessions s JOIN users u ON u.id=s.user_id JOIN tenants t ON t.id=u.tenant_id
            WHERE s.token_hash=? AND s.expires_at>?""", (digest(raw_token), now())).fetchone()
    if user is None:
        problem(401, "Сессия завершена. Войдите снова")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not hmac.compare_digest(csrf, user["csrf_token"]):
            problem(403, "Проверка безопасности не пройдена. Обновите страницу")
    return dict(user)


def insert_invoice(connection, tenant_id, data):
    invoice_id = identifier()
    connection.execute("""INSERT INTO invoices(id,tenant_id,company,inn,email,number,issued_on,due_on,amount,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (invoice_id, tenant_id, data["company"], data.get("inn", ""), data.get("email", ""), data["number"], str(data["issued_on"]), str(data["due_on"]), data["amount"], data.get("notes", ""), now()))
    event(connection, tenant_id, invoice_id, "invoice_created", "Счёт добавлен", f"№ {data['number']} · {money_text(data['amount'])} ₽")
    return invoice_row(connection, tenant_id, invoice_id)


def duplicate_keys(connection, tenant_id):
    return {(row["company"], row["number"]) for row in connection.execute("SELECT company,number FROM invoices WHERE tenant_id=?", (tenant_id,))}


def create_app():
    config = Config.from_environment()

    @asynccontextmanager
    async def lifespan(application):
        initialize(config)
        yield

    application = FastAPI(title="AgentPay API", version="1.0.0", lifespan=lifespan,
                          docs_url=None if config.production else "/api/docs", redoc_url=None,
                          openapi_url=None if config.production else "/api/openapi.json")
    application.state.config = config
    application.add_middleware(GuardMiddleware, config=config)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Never reflect passwords, CSV contents or draft bodies in validation errors.
        details = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in error.errors()]
        return JSONResponse({"detail": details}, status_code=422)

    @application.get("/api/health")
    def health():
        with database(config) as connection:
            connection.execute("SELECT 1")
        return {"status": "ok"}

    @application.post("/api/auth/register", status_code=201)
    def register(data: Register):
        import sqlite3
        password_hash = PASSWORDS.hash(data.password)
        try:
            with database(config, write=True) as connection:
                tenant_id, user_id = identifier(), identifier()
                connection.execute("INSERT INTO tenants VALUES(?,?,?)", (tenant_id, data.company, now()))
                connection.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", (user_id, tenant_id, data.name, data.email, password_hash, now()))
                connection.execute("INSERT INTO settings(tenant_id,sender_name,reply_to) VALUES(?,?,?)", (tenant_id, data.name, data.email))
                user = {"id": user_id, "name": data.name, "company": data.company, "email": data.email}
                return create_session(connection, user, config, 201)
        except sqlite3.IntegrityError:
            problem(409, "Аккаунт с таким email уже существует")

    @application.post("/api/auth/login")
    def login(data: Login, request: Request):
        with database(config, write=True) as connection:
            user = connection.execute("SELECT u.*,t.company FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE u.email=?", (data.email,)).fetchone()
            try:
                valid = PASSWORDS.verify(user["password_hash"] if user else DUMMY_HASH, data.password)
            except VerificationError:
                valid = False
            if not valid or not user:
                problem(401, "Неверный email или пароль")
            if PASSWORDS.check_needs_rehash(user["password_hash"]):
                connection.execute("UPDATE users SET password_hash=? WHERE id=?", (PASSWORDS.hash(data.password), user["id"]))
            old_token = request.cookies.get(COOKIE_NAME)
            if old_token:
                connection.execute("DELETE FROM sessions WHERE token_hash=?", (digest(old_token),))
            return create_session(connection, user, config)

    @application.get("/api/auth/me")
    def me(user=Depends(get_user)):
        return {"user": {key: user[key] for key in ("id", "name", "company", "email")}, "csrf_token": user["csrf_token"]}

    @application.post("/api/auth/logout")
    def logout(request: Request, user=Depends(get_user)):
        with database(config, write=True) as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=? AND user_id=?", (digest(request.cookies.get(COOKIE_NAME, "")), user["id"]))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE_NAME, path="/", secure=config.secure_cookies, httponly=True, samesite="lax")
        return response

    @application.get("/api/overview")
    def overview(user=Depends(get_user)):
        with database(config) as connection:
            items = [invoice_view(row) for row in connection.execute("SELECT * FROM invoices WHERE tenant_id=?", (user["tenant_id"],))]
            payments = list(connection.execute("SELECT amount,paid_on FROM payments WHERE tenant_id=?", (user["tenant_id"],)))
        labels = ["В срок", "1–7 дней", "8–30 дней", "31–60 дней", "61–90 дней", "90+ дней"]
        amounts = [0] * len(labels)
        for item in items:
            days = item["days_overdue"]
            index = 0 if not days else 1 if days <= 7 else 2 if days <= 30 else 3 if days <= 60 else 4 if days <= 90 else 5
            amounts[index] += item["balance"]
        start = business_today() - timedelta(days=6)
        totals = defaultdict(int)
        for payment in payments:
            totals[payment["paid_on"]] += payment["amount"]
        return {
            "total_outstanding": sum(item["balance"] for item in items),
            "overdue_amount": sum(item["balance"] for item in items if item["days_overdue"]),
            "collected_amount": sum(payment["amount"] for payment in payments),
            "promised_amount": sum(item["balance"] for item in items if item["status"] == "promised"),
            "invoice_count": len(items), "overdue_count": sum(1 for item in items if item["days_overdue"]),
            "aging": [{"label": label, "amount": amount} for label, amount in zip(labels, amounts)],
            "weekly": [{"date": str(start + timedelta(days=offset)), "amount": totals[str(start + timedelta(days=offset))]} for offset in range(7)],
        }

    @application.get("/api/invoices")
    def list_invoices(search: str = "", status: str = "", priority: str = "", user=Depends(get_user)):
        if len(search) > 200 or status not in ("", "open", "promised", "disputed", "paused", "paid") or priority not in ("", "high", "medium", "low"):
            problem(422, "Некорректный фильтр")
        with database(config) as connection:
            items = [invoice_view(row) for row in connection.execute("SELECT * FROM invoices WHERE tenant_id=? ORDER BY due_on,created_at", (user["tenant_id"],))]
        needle = search.casefold().strip()
        return {"items": [item for item in items if (not needle or needle in " ".join((item["company"], item["inn"], item["number"], item["email"])).casefold()) and (not status or item["status"] == status) and (not priority or item["priority"] == priority)]}

    @application.post("/api/invoices", status_code=201)
    def add_invoice(data: InvoiceInput, user=Depends(get_user)):
        import sqlite3
        try:
            with database(config, write=True) as connection:
                return invoice_view(insert_invoice(connection, user["tenant_id"], data.model_dump(mode="json")))
        except sqlite3.IntegrityError:
            problem(409, "Счёт с таким номером у этого контрагента уже существует")

    @application.post("/api/invoices/import/preview")
    def preview_import(data: CSVInput, user=Depends(get_user)):
        items, errors = parse_csv(data.content)
        with database(config) as connection:
            seen = duplicate_keys(connection, user["tenant_id"])
        duplicates = 0
        for item in items:
            key = (item["company"], item["number"])
            if key in seen:
                duplicates += 1
            seen.add(key)
        return {"items": items, "errors": errors, "duplicate_count": duplicates}

    @application.post("/api/invoices/import")
    def commit_import(data: CSVInput, user=Depends(get_user)):
        items, errors = parse_csv(data.content)
        if errors:
            problem(422, {"message": "Исправьте ошибки: ни один счёт не импортирован", "errors": errors})
        imported = skipped = 0
        with database(config, write=True) as connection:
            seen = duplicate_keys(connection, user["tenant_id"])
            for item in items:
                key = (item["company"], item["number"])
                if key in seen:
                    skipped += 1
                    continue
                insert_invoice(connection, user["tenant_id"], item)
                seen.add(key)
                imported += 1
        return {"imported": imported, "skipped": skipped}

    @application.get("/api/invoices/{invoice_id}")
    def invoice_detail(invoice_id: str, user=Depends(get_user)):
        with database(config) as connection:
            invoice = invoice_view(invoice_row(connection, user["tenant_id"], invoice_id))
            events = [{key: row[key] for key in ("id", "type", "title", "detail", "created_at")} for row in connection.execute("SELECT * FROM events WHERE invoice_id=? AND tenant_id=? ORDER BY created_at DESC", (invoice_id, user["tenant_id"]))]
            messages = [message_view(row) for row in connection.execute("SELECT * FROM messages WHERE invoice_id=? AND tenant_id=? ORDER BY created_at DESC", (invoice_id, user["tenant_id"]))]
            payments = [{key: row[key] for key in ("id", "amount", "paid_on", "reference", "created_at")} for row in connection.execute("SELECT * FROM payments WHERE invoice_id=? AND tenant_id=? ORDER BY paid_on DESC,created_at DESC", (invoice_id, user["tenant_id"]))]
        return {"invoice": invoice, "events": events, "messages": messages, "payments": payments}

    @application.patch("/api/invoices/{invoice_id}/contact")
    def update_contact(invoice_id: str, data: ContactInput, user=Depends(get_user)):
        with database(config, write=True) as connection:
            row = invoice_row(connection, user["tenant_id"], invoice_id)
            connection.execute("UPDATE invoices SET email=?,notes=? WHERE id=? AND tenant_id=?", (data.email, data.notes, invoice_id, user["tenant_id"]))
            # Old drafts keep their actual recipient and financial snapshot. They
            # must never silently become approved mail to a corrected address.
            connection.execute("UPDATE messages SET status='draft' WHERE invoice_id=? AND tenant_id=? AND status!='sent'", (invoice_id, user["tenant_id"]))
            previous = row["email"] or "не указан"
            current = data.email or "не указан"
            detail = f"Email: {previous} → {current}"
            if data.notes:
                detail += "\n" + data.notes
            event(connection, user["tenant_id"], invoice_id, "contact_updated", "Контакт обновлён", detail)
            return invoice_view(invoice_row(connection, user["tenant_id"], invoice_id))

    @application.post("/api/invoices/{invoice_id}/draft", status_code=201)
    def draft(invoice_id: str, data: DraftInput, user=Depends(get_user)):
        with database(config) as connection:
            contactable(invoice_row(connection, user["tenant_id"], invoice_id))
        wording, source = llm.phrases(data.tone)
        with database(config, write=True) as connection:
            row = invoice_row(connection, user["tenant_id"], invoice_id)
            contactable(row)
            settings = settings_view(connection, user["tenant_id"])
            balance = row["amount"] - row["paid_amount"]
            date_text = date.fromisoformat(row["due_on"]).strftime("%d.%m.%Y")
            facts = f"По счёту № {row['number']} от {date.fromisoformat(row['issued_on']).strftime('%d.%m.%Y')} остаётся к оплате {money_text(balance)} ₽. Срок оплаты — {date_text}."
            body = wording["greeting"] + "\n\n" + facts + "\n\n" + wording["request"]
            if settings["bank_details"]:
                body += "\n\nРеквизиты для оплаты:\n" + settings["bank_details"]
            body += "\n\n" + wording["closing"] + "\n" + (settings["sender_name"] or user["name"]) + "\n" + settings["company"]
            message_id = identifier()
            connection.execute("""INSERT INTO messages(id,tenant_id,invoice_id,subject,body,recipient,source,balance_snapshot,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (message_id, user["tenant_id"], invoice_id, f"Оплата счёта № {row['number']}", body, row["email"], source, balance, now()))
            event(connection, user["tenant_id"], invoice_id, "draft_created", "Подготовлено письмо", "Мягкий тон" if data.tone == "soft" else "Деловой тон")
            return message_view(message_row(connection, user["tenant_id"], message_id))

    @application.patch("/api/messages/{message_id}")
    def edit_message(message_id: str, data: MessageInput, user=Depends(get_user)):
        with database(config, write=True) as connection:
            message = message_row(connection, user["tenant_id"], message_id)
            if message["status"] == "sent":
                problem(409, "Отправленное письмо нельзя изменить")
            connection.execute("UPDATE messages SET subject=?,body=?,status='draft' WHERE id=? AND tenant_id=?", (data.subject, data.body, message_id, user["tenant_id"]))
            event(connection, user["tenant_id"], message["invoice_id"], "draft_edited", "Письмо отредактировано", "Для отправки требуется повторное согласование")
            return message_view(message_row(connection, user["tenant_id"], message_id))

    @application.post("/api/messages/{message_id}/approve")
    def approve(message_id: str, user=Depends(get_user)):
        with database(config, write=True) as connection:
            message = message_row(connection, user["tenant_id"], message_id)
            row = invoice_row(connection, user["tenant_id"], message["invoice_id"])
            contactable(row)
            if message["recipient"] != row["email"]:
                problem(409, "Адрес получателя изменился. Подготовьте новое письмо")
            if message["status"] == "sent":
                problem(409, "Письмо уже отправлено")
            if row["amount"] - row["paid_amount"] != message["balance_snapshot"]:
                problem(409, "Остаток изменился. Подготовьте новое письмо")
            connection.execute("UPDATE messages SET status='approved' WHERE id=? AND tenant_id=?", (message_id, user["tenant_id"]))
            event(connection, user["tenant_id"], message["invoice_id"], "message_approved", "Письмо согласовано", user["name"])
            return message_view(message_row(connection, user["tenant_id"], message_id))

    @application.post("/api/messages/{message_id}/send")
    def send_message(message_id: str, user=Depends(get_user)):
        failed = False
        with database(config, write=True) as connection:
            message = message_row(connection, user["tenant_id"], message_id)
            row = invoice_row(connection, user["tenant_id"], message["invoice_id"])
            contactable(row)
            if message["recipient"] != row["email"]:
                problem(409, "Адрес получателя изменился. Подготовьте новое письмо")
            if message["status"] != "approved":
                problem(409, "Перед отправкой согласуйте письмо")
            if row["amount"] - row["paid_amount"] != message["balance_snapshot"]:
                problem(409, "Остаток изменился. Подготовьте новое письмо")
            if not smtp_configuration(user["tenant_id"]):
                problem(409, "Почта компании не подключена. Письмо сохранено, но не отправлено")
            settings = settings_view(connection, user["tenant_id"])
            latest = connection.execute("SELECT sent_at FROM messages WHERE tenant_id=? AND invoice_id=? AND status='sent' ORDER BY sent_at DESC LIMIT 1", (user["tenant_id"], row["id"])).fetchone()
            if latest and datetime.fromisoformat(latest["sent_at"]) + timedelta(days=settings["cooldown_days"]) > datetime.now(timezone.utc):
                problem(409, "Выдержите интервал между письмами, заданный в настройках")
            mail = EmailMessage()
            mail["Subject"], mail["To"] = message["subject"], message["recipient"]
            mail["From"] = formataddr((settings["sender_name"] or user["name"], os.environ["SMTP_FROM"]))
            if settings["reply_to"]:
                mail["Reply-To"] = settings["reply_to"]
            mail["Message-ID"] = f"<{message_id}@{os.environ['SMTP_FROM'].split('@')[-1]}>"
            mail.set_content(message["body"])
            try:
                port = int(os.getenv("SMTP_PORT", "587"))
                use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
                smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
                arguments = {"timeout": 12}
                if use_ssl:
                    arguments["context"] = ssl.create_default_context()
                with smtp_class(os.environ["SMTP_HOST"], port, **arguments) as smtp:
                    if not use_ssl and os.getenv("SMTP_USE_TLS", "true").lower() == "true":
                        smtp.starttls(context=ssl.create_default_context())
                    if os.getenv("SMTP_USER"):
                        smtp.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
                    if smtp.send_message(mail):
                        raise smtplib.SMTPException("Recipient rejected")
                connection.execute("UPDATE messages SET status='sent',sent_at=? WHERE id=? AND tenant_id=?", (now(), message_id, user["tenant_id"]))
                event(connection, user["tenant_id"], row["id"], "message_sent", "Письмо принято почтовым сервером", message["recipient"])
            except (OSError, smtplib.SMTPException, ValueError):
                # Ambiguous SMTP failures require a human review; no automatic retries.
                connection.execute("UPDATE messages SET status='failed' WHERE id=? AND tenant_id=?", (message_id, user["tenant_id"]))
                event(connection, user["tenant_id"], row["id"], "message_failed", "Отправка не подтверждена", "Проверьте почтовый сервер перед повторным согласованием")
                failed = True
            result = message_view(message_row(connection, user["tenant_id"], message_id))
        if failed:
            problem(502, "Почтовый сервер не подтвердил отправку. Обратитесь к администратору")
        return result

    @application.post("/api/invoices/{invoice_id}/payments")
    def record_payment(invoice_id: str, data: PaymentInput, user=Depends(get_user)):
        with database(config, write=True) as connection:
            row = invoice_row(connection, user["tenant_id"], invoice_id)
            existing = connection.execute("SELECT * FROM payments WHERE tenant_id=? AND invoice_id=? AND reference=?", (user["tenant_id"], invoice_id, data.reference)).fetchone()
            if existing:
                if existing["amount"] != data.amount or existing["paid_on"] != str(data.paid_on):
                    problem(409, "Такой номер платежа уже зарегистрирован с другими данными")
                return invoice_view(row)
            if data.amount > row["amount"] - row["paid_amount"]:
                problem(422, "Сумма платежа превышает остаток по счёту")
            if str(data.paid_on) < row["issued_on"]:
                problem(422, "Дата платежа не может быть раньше даты счёта")
            connection.execute("INSERT INTO payments VALUES(?,?,?,?,?,?,?)", (identifier(), user["tenant_id"], invoice_id, data.amount, str(data.paid_on), data.reference, now()))
            connection.execute("UPDATE invoices SET paid_amount=paid_amount+? WHERE id=? AND tenant_id=?", (data.amount, invoice_id, user["tenant_id"]))
            connection.execute("UPDATE messages SET status='draft' WHERE invoice_id=? AND tenant_id=? AND status='approved'", (invoice_id, user["tenant_id"]))
            event(connection, user["tenant_id"], invoice_id, "payment_recorded", "Зарегистрирована оплата", f"{money_text(data.amount)} ₽ · {data.reference}")
            return invoice_view(invoice_row(connection, user["tenant_id"], invoice_id))

    @application.post("/api/invoices/{invoice_id}/promise")
    def promise(invoice_id: str, data: PromiseInput, user=Depends(get_user)):
        with database(config, write=True) as connection:
            row = invoice_row(connection, user["tenant_id"], invoice_id)
            if row["paid_amount"] == row["amount"]:
                problem(409, "Счёт уже оплачен")
            if row["status"] == "disputed":
                problem(409, "Сначала разрешите спор по счёту")
            connection.execute("UPDATE invoices SET promise_date=? WHERE id=? AND tenant_id=?", (str(data.date), invoice_id, user["tenant_id"]))
            event(connection, user["tenant_id"], invoice_id, "promise_recorded", "Зафиксировано обещание оплаты", data.date.strftime("%d.%m.%Y"))
            return invoice_view(invoice_row(connection, user["tenant_id"], invoice_id))

    @application.post("/api/invoices/{invoice_id}/status")
    def update_status(invoice_id: str, data: StatusInput, user=Depends(get_user)):
        with database(config, write=True) as connection:
            row = invoice_row(connection, user["tenant_id"], invoice_id)
            if row["paid_amount"] == row["amount"]:
                problem(409, "Оплаченный счёт нельзя вернуть в работу")
            connection.execute("UPDATE invoices SET status=?,notes=COALESCE(?,notes) WHERE id=? AND tenant_id=?", (data.status, data.notes, invoice_id, user["tenant_id"]))
            if data.status in ("disputed", "paused"):
                connection.execute("UPDATE messages SET status='draft' WHERE invoice_id=? AND tenant_id=? AND status='approved'", (invoice_id, user["tenant_id"]))
            titles = {"open": "Счёт возвращён в работу", "disputed": "Открыт спор по счёту", "paused": "Контакт приостановлен"}
            event(connection, user["tenant_id"], invoice_id, "status_changed", titles[data.status], data.notes or "")
            return invoice_view(invoice_row(connection, user["tenant_id"], invoice_id))

    @application.get("/api/settings")
    def get_settings(user=Depends(get_user)):
        with database(config) as connection:
            return settings_view(connection, user["tenant_id"])

    @application.patch("/api/settings")
    def patch_settings(data: SettingsInput, user=Depends(get_user)):
        values = data.model_dump(exclude_none=True)
        with database(config, write=True) as connection:
            company = values.pop("company", None)
            if company is not None:
                connection.execute("UPDATE tenants SET company=? WHERE id=?", (company, user["tenant_id"]))
            # Keys originate only from the strict Pydantic settings model.
            if values:
                columns = ",".join(key + "=?" for key in values)
                connection.execute(f"UPDATE settings SET {columns} WHERE tenant_id=?", (*values.values(), user["tenant_id"]))
            return settings_view(connection, user["tenant_id"])

    @application.get("/api/export")
    def export(user=Depends(get_user)):
        with database(config) as connection:
            items = [invoice_view(row) for row in connection.execute("SELECT * FROM invoices WHERE tenant_id=? ORDER BY due_on", (user["tenant_id"],))]

        def safe(value):
            text = str(value)
            return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(["контрагент", "инн", "email", "номер", "дата", "срок", "сумма", "оплачено", "остаток", "статус"])
        for item in items:
            writer.writerow([safe(item[key]) for key in ("company", "inn", "email", "number", "issued_on", "due_on")] + [money_text(item[key]) for key in ("amount", "paid_amount", "balance")] + [item["status"]])
        return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="agentpay-invoices.csv"'})

    @application.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"])
    def missing_api(path: str):
        problem(404, "Метод API не найден")

    web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if (web_dist / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

    @application.get("/{path:path}")
    def frontend(path: str):
        candidate = (web_dist / path).resolve()
        if candidate.is_relative_to(web_dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if (web_dist / "index.html").is_file():
            return FileResponse(web_dist / "index.html", headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Соберите фронтенд: cd web && npm run build"}, 404)

    return application


app = create_app()
