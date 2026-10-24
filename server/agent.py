"""Tenant-scoped incoming correspondence proposals, reviewed and executed once."""
import json
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command
from langsmith import tracing_context

from .agent_graph import extract_yandex, persistent_graph
from .agent_models import IngestInput, ReviewInput, RevisionInput, validate_extraction
from .agent_observability import AgentObservability
from .agent_policy import provider_allowed, provider_configured


def initialize_schema(connection):
    statements = ["""CREATE TABLE IF NOT EXISTS agent_proposals (
        id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, invoice_id TEXT NOT NULL,
        thread_id TEXT NOT NULL UNIQUE, source_key TEXT NOT NULL, source_text TEXT NOT NULL,
        received_at TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, status TEXT NOT NULL, extraction_json TEXT,
        provider_json TEXT, snapshot_json TEXT, snapshot_hash TEXT, reasons_json TEXT NOT NULL DEFAULT '[]',
        decision TEXT, review_reason TEXT, reviewed_by TEXT, reviewed_at TEXT, outcome_json TEXT,
        revision_of TEXT, UNIQUE(tenant_id,source_key),
        FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id) ON DELETE CASCADE
    )""", """CREATE TABLE IF NOT EXISTS agent_verifications (
        id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, invoice_id TEXT NOT NULL,
        proposal_id TEXT NOT NULL UNIQUE REFERENCES agent_proposals(id),
        status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
        FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id) ON DELETE CASCADE
    )""", "CREATE INDEX IF NOT EXISTS agent_proposals_tenant ON agent_proposals(tenant_id,created_at)"]
    for statement in statements:
        connection.execute(statement)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def view(row):
    result = {key: row[key] for key in ("id", "invoice_id", "thread_id", "source_text", "received_at", "status",
        "created_at", "expires_at", "decision", "review_reason", "reviewed_by", "reviewed_at", "revision_of")}
    for public, column, default in (("extraction", "extraction_json", {}), ("provider", "provider_json", {}),
        ("snapshot", "snapshot_json", {}), ("reasons", "reasons_json", []), ("outcome", "outcome_json", None)):
        result[public] = json.loads(row[column]) if row[column] else default
    result["intent"] = result["extraction"].get("intent", "unknown")
    result["action"] = result["extraction"].get("action", "manual_review")
    return result


class AgentRuntime:
    def __init__(self, ctx, *, services=None):
        self.ctx = ctx
        if services is None:
            from . import finance
            services = finance
        self.services = services
        self.observer = AgentObservability()

    def load(self, state, connection=None):
        if connection is None:
            with self.ctx.database(self.ctx.config) as connection:
                return self.load(state, connection)
        row = connection.execute("SELECT * FROM agent_proposals WHERE id=? AND tenant_id=?",
            (state["proposal_id"], state["tenant_id"])).fetchone()
        if row is None:
            raise HTTPException(404, "Предложение не найдено")
        return dict(row)

    def ingest_node(self, state):
        proposal = self.load(state)
        return {"status": proposal["status"]}

    def extract_node(self, state):
        proposal = self.load(state)
        if proposal["provider_json"]:
            return {}
        if provider_allowed(proposal["tenant_id"], production=self.ctx.config.production):
            result = extract_yandex(proposal["source_text"], proposal["received_at"], proposal["id"], observer=self.observer)
        else:
            result = {"payload": None, "error": "provider_tenant_denied", "usage": {}, "latency_ms": 0}
        provider = {key: value for key, value in result.items() if key != "payload"}
        with self.ctx.database(self.ctx.config, write=True) as connection:
            # Exactly one persisted extraction is authoritative even if a failed
            # worker resumes before the checkpoint following this node was saved.
            connection.execute("UPDATE agent_proposals SET provider_json=?,extraction_json=? WHERE id=? AND tenant_id=? AND provider_json IS NULL",
                (encoded(provider), encoded(result["payload"]) if result["payload"] is not None else None, proposal["id"], proposal["tenant_id"]))
        return {}

    def validate_node(self, state):
        with self.ctx.database(self.ctx.config, write=True) as connection:
            proposal = self.load(state, connection)
            if proposal["status"] != "processing":
                return {"status": proposal["status"]}
            metadata = json.loads(proposal["provider_json"] or "{}")
            if metadata.get("error"):
                extracted, reasons = {"intent": "unknown", "action": "manual_review", "evidence": []}, [metadata["error"]]
            else:
                extracted, reasons = validate_extraction(proposal["source_text"], json.loads(proposal["extraction_json"] or "null"), datetime.fromisoformat(proposal["received_at"]))
            snapshot = self.services.financial_snapshot(connection, proposal["tenant_id"], proposal["invoice_id"])
            if not reasons:
                reasons += self.services.agent_gate(connection, proposal["tenant_id"], proposal["invoice_id"], extracted["intent"],
                    amount=extracted.get("amount_kopeks"), due_date=extracted.get("due_date"))
            status = "handoff" if reasons else "review_required"
            connection.execute("UPDATE agent_proposals SET extraction_json=?,snapshot_json=?,snapshot_hash=?,reasons_json=?,status=? WHERE id=? AND tenant_id=?",
                (encoded(extracted), encoded(snapshot), snapshot["snapshot_hash"], encoded(reasons), status, proposal["id"], proposal["tenant_id"]))
            return {"status": status}

    def review_node(self, state):
        proposal = self.load(state)
        if proposal["decision"] not in ("approve", "reject") or not proposal["reviewed_by"]:
            raise HTTPException(409, "Нужно подтверждение сотрудника в Mandato")
        return {"status": proposal["status"]}

    def execute_node(self, state):
        with self.ctx.database(self.ctx.config, write=True) as connection:
            proposal = self.load(state, connection)
            if proposal["status"] in ("executed", "rejected", "stale", "superseded"):
                return {"status": proposal["status"]}
            if proposal["decision"] == "reject":
                connection.execute("UPDATE agent_proposals SET status='rejected' WHERE id=? AND tenant_id=?", (proposal["id"], proposal["tenant_id"]))
                return {"status": "rejected"}
            if proposal["status"] != "review_required" or proposal["decision"] != "approve" or not proposal["reviewed_by"]:
                raise HTTPException(409, "Исполнение требует проверенного согласования")
            extracted = json.loads(proposal["extraction_json"])
            current = self.services.financial_snapshot(connection, proposal["tenant_id"], proposal["invoice_id"])
            reasons = []
            if datetime.fromisoformat(proposal["expires_at"]) <= datetime.now(timezone.utc):
                reasons.append("approval_expired")
            if current["snapshot_hash"] != proposal["snapshot_hash"]:
                reasons.append("stale_snapshot")
            reasons += self.services.agent_gate(connection, proposal["tenant_id"], proposal["invoice_id"], extracted["intent"],
                amount=extracted.get("amount_kopeks"), due_date=extracted.get("due_date"))
            if reasons:
                connection.execute("UPDATE agent_proposals SET status='stale',reasons_json=? WHERE id=? AND tenant_id=?",
                    (encoded(list(dict.fromkeys(reasons))), proposal["id"], proposal["tenant_id"]))
                return {"status": "stale"}
            # The business transaction (BEGIN IMMEDIATE / PG row lock) includes
            # domain write and terminal proposal status, so retry cannot replay it.
            if extracted["intent"] == "promise":
                outcome = self.services.record_promise(connection, proposal["tenant_id"], proposal["invoice_id"],
                    extracted["amount_kopeks"], extracted["due_date"], proposal["reviewed_by"], "agent:" + proposal["id"])
            elif extracted["intent"] == "dispute":
                outcome = self.services.set_dispute(connection, proposal["tenant_id"], proposal["invoice_id"], True,
                    "Спор подтверждён по входящему сообщению", proposal["reviewed_by"], source_key="agent:" + proposal["id"])
            elif extracted["intent"] == "payment_claim":
                connection.execute("INSERT INTO agent_verifications(id,tenant_id,invoice_id,proposal_id,status,created_at) VALUES(?,?,?,?,?,?)",
                    (self.ctx.identifier(), proposal["tenant_id"], proposal["invoice_id"], proposal["id"], "open", self.ctx.now()))
                outcome = {"action": "verify_payment", "status": "open", "message": "Поступление требует сверки; остаток не изменён"}
            else:
                raise HTTPException(409, "Действие не разрешено")
            connection.execute("UPDATE agent_proposals SET status='executed',outcome_json=? WHERE id=? AND tenant_id=?",
                (encoded(outcome), proposal["id"], proposal["tenant_id"]))
            self.ctx.event(connection, proposal["tenant_id"], proposal["invoice_id"], "agent_action", "Предложение агента подтверждено", extracted["action"])
            return {"status": "executed"}

    def run(self, proposal, *, resume=False):
        config = {"configurable": {"thread_id": proposal["thread_id"]}, "recursion_limit": 12, "callbacks": []}
        initial = {"proposal_id": proposal["id"], "tenant_id": proposal["tenant_id"]}
        # LANGSMITH_TRACING in an operator shell must not enable a second,
        # automatic raw-payload trace sink behind this minimized integration.
        started = time.monotonic()
        error = None
        with self.observer.observe("workflow", proposal["id"]) as observation:
            try:
                with tracing_context(enabled=False), persistent_graph(self) as graph:
                    checkpoint = graph.get_state(config)
                    if resume and checkpoint.next:
                        graph.invoke(Command(resume={"review_recorded": True}), config)
                    elif not checkpoint.values:
                        graph.invoke(initial, config)
                    elif checkpoint.next and not resume:
                        graph.invoke(None, config)
            except Exception as exc:
                # Leave SDK context without the domain exception: an automatic
                # exception event could include sensitive facts in its message.
                error = exc
            status = "workflow_error" if error else self.load(initial)["status"]
            observation.finish(status=status, usage={}, latency_ms=int((time.monotonic() - started) * 1000))
        if error:
            raise error
        return self.load(initial)


def create_router(ctx, *, services=None):
    router = APIRouter(prefix="/api/agent", tags=["agent"])
    runtime = AgentRuntime(ctx, services=services)

    @router.get("/status")
    def status(user=Depends(ctx.get_user)):
        allowed = provider_allowed(user["tenant_id"], production=ctx.config.production)
        configured = provider_configured()
        return {"organization_id": user["tenant_id"], "enabled": allowed and configured,
                "observability_configured": runtime.observer.configured,
                "reason": "provider_tenant_denied" if not allowed else "ready" if configured else "provider_unconfigured"}

    def create(data, user, *, revision_of=None):
        received = data.received_at if isinstance(data, IngestInput) and data.received_at else datetime.now(timezone.utc)
        if received.tzinfo is None or received > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise HTTPException(422, "Укажите корректное время получения с часовым поясом")
        with ctx.database(ctx.config, write=True) as connection:
            runtime.services.financial_snapshot(connection, user["tenant_id"], data.invoice_id)
            previous = connection.execute("SELECT * FROM agent_proposals WHERE tenant_id=? AND source_key=?", (user["tenant_id"], data.idempotency_key)).fetchone()
            if previous:
                if previous["source_text"] != data.text or previous["invoice_id"] != data.invoice_id or previous["revision_of"] != revision_of:
                    raise HTTPException(409, "Ключ события уже использован с другими данными")
                proposal = dict(previous)
            else:
                hour = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
                day = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
                count = connection.execute("SELECT COUNT(*) AS n FROM agent_proposals WHERE tenant_id=? AND created_at>?", (user["tenant_id"], hour)).fetchone()["n"]
                total = connection.execute("SELECT COUNT(*) AS n FROM agent_proposals WHERE created_at>?", (day,)).fetchone()["n"]
                if count >= 30 or total >= 1000:
                    raise HTTPException(429, "Достигнут лимит обработки сообщений")
                proposal_id, timestamp = ctx.identifier(), ctx.now()
                thread_id = ctx.identifier()  # supplied thread/tenant IDs never come from a client
                if revision_of:
                    old = runtime.load({"proposal_id": revision_of, "tenant_id": user["tenant_id"]}, connection)
                    if old["status"] == "executed":
                        raise HTTPException(409, "Исполненное предложение не редактируется")
                    connection.execute("UPDATE agent_proposals SET status='superseded' WHERE id=? AND tenant_id=?", (revision_of, user["tenant_id"]))
                connection.execute("""INSERT INTO agent_proposals(id,tenant_id,invoice_id,thread_id,source_key,source_text,
                    received_at,created_by,created_at,expires_at,status,revision_of) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (proposal_id, user["tenant_id"], data.invoice_id, thread_id, data.idempotency_key, data.text,
                     received.isoformat(), user["id"], timestamp, (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(), "processing", revision_of))
                proposal = runtime.load({"proposal_id": proposal_id, "tenant_id": user["tenant_id"]}, connection)
        return view(runtime.run(proposal) if proposal["status"] == "processing" else proposal)

    @router.get("/proposals")
    def proposals(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:
            rows = connection.execute("SELECT * FROM agent_proposals WHERE tenant_id=? ORDER BY created_at DESC LIMIT 200", (user["tenant_id"],)).fetchall()
        return {"proposals": [view(row) for row in rows]}

    @router.get("/proposals/{proposal_id}")
    def proposal(proposal_id: str, user=Depends(ctx.get_user)):
        return view(runtime.load({"proposal_id": proposal_id, "tenant_id": user["tenant_id"]}))

    @router.post("/ingest", status_code=201)
    def ingest(data: IngestInput, user=Depends(ctx.get_user)):
        return create(data, user)

    @router.post("/proposals/{proposal_id}/revise", status_code=201)
    def revise(proposal_id: str, data: RevisionInput, user=Depends(ctx.get_user)):
        old = runtime.load({"proposal_id": proposal_id, "tenant_id": user["tenant_id"]})
        incoming = IngestInput(invoice_id=old["invoice_id"], text=data.text, idempotency_key=data.idempotency_key, received_at=datetime.fromisoformat(old["received_at"]))
        return create(incoming, user, revision_of=proposal_id)

    @router.post("/proposals/{proposal_id}/review")
    def review(proposal_id: str, data: ReviewInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as connection:
            proposal = runtime.load({"proposal_id": proposal_id, "tenant_id": user["tenant_id"]}, connection)
            if proposal["decision"] and proposal["decision"] != data.decision:
                raise HTTPException(409, "Решение уже записано; создайте новую редакцию")
            if proposal["status"] in ("executed", "rejected") and proposal["decision"] == data.decision:
                return view(proposal)
            if proposal["status"] != "review_required":
                raise HTTPException(409, "Предложение требует ручной доработки или устарело")
            connection.execute("UPDATE agent_proposals SET decision=?,review_reason=?,reviewed_by=?,reviewed_at=? WHERE id=? AND tenant_id=? AND decision IS NULL",
                (data.decision, data.reason, user["id"], ctx.now(), proposal_id, user["tenant_id"]))
        result = runtime.run(proposal, resume=True)
        if result["status"] == "stale":
            raise HTTPException(409, "Данные изменились или согласование истекло. Создайте новую редакцию")
        return view(result)

    return router
