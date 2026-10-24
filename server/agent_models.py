"""Strict model boundary: extraction never grants authority to change a ledger."""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictBool

from .business_time import business_timezone


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestInput(Input):
    invoice_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=3, max_length=12000)
    received_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class ReviewInput(Input):
    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=1000)


class RevisionInput(Input):
    text: str = Field(min_length=3, max_length=12000)
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class Evidence(Input):
    field: Literal["intent", "amount", "due_date"]
    quote: str = Field(min_length=1, max_length=700)


class Extraction(Input):
    intent: Literal["promise", "dispute", "payment_claim", "unknown"]
    amount_kopeks: StrictInt | None = Field(ge=1, le=1_000_000_000_000_000)
    due_date: str | None = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    currency: Literal["RUB", "other", "unknown"]
    ambiguous: StrictBool
    evidence: list[Evidence] = Field(max_length=8)


INJECTION = re.compile(r"ignore.{0,40}instructions|system\s*(?:prompt|instruction)|"
                       r"игнорируй.{0,50}(?:правил|инструкц)|системн\w*\s+инструкц|"
                       r"(?:вызови|выполни).{0,30}(?:api|sql|инструмент)|<\|(?:system|assistant)", re.I | re.S)
NEGATION = re.compile(r"\bне\s+(?:обеща\w*|оплат\w*|заплат\w*|перечисл\w*)|не\s+можем|не\s+сможем", re.I)
INTENTS = {
    "promise": re.compile(r"обеща\w*\s+(?:вам\s+)?(?:оплат|заплат|перечисл)|\b(?:оплатим|заплатим|перечислим)\b", re.I),
    "payment_claim": re.compile(r"\b(?:оплатили|оплачен[аоы]?|заплатили|перечислили)\b", re.I),
    "dispute": re.compile(r"\bспор\w*|не\s+согласны|расхожден\w*|не\s+принимаем", re.I),
}
AMOUNT = re.compile(r"(?<![\d.,])([0-9]+(?:[ \u00a0\u202f][0-9]{3})*(?:[,.][0-9]{1,2})?)\s*(?:руб(?:\.|ля|лей|ль)?|₽|RUB)(?![А-Яа-яA-Za-z])", re.I)
FULL_DATE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b")
FOREIGN = re.compile(r"\b(?:usd|eur|доллар\w*|евро|тенге)\b|[$€₸]", re.I)
QUOTED = re.compile(r"^\s*>|^\s*(?:From|От):|forwarded message|пересылаемое сообщение|wrote:", re.I | re.M)


def amounts(text):
    found = []
    for match in AMOUNT.finditer(text):
        try:
            value = Decimal(re.sub(r"[ \u00a0\u202f]", "", match.group(1)).replace(",", ".")) * 100
            if value == value.to_integral_value():
                found.append(int(value))
        except InvalidOperation:
            continue
    return found


def dates(text, received_at):
    found = []
    for token in FULL_DATE.findall(text):
        try:
            found.append(date.fromisoformat(token) if "-" in token else datetime.strptime(token, "%d.%m.%Y").date())
        except ValueError:
            continue
    day = received_at.astimezone(business_timezone()).date()
    for word, delta in (("послезавтра", 2), ("завтра", 1), ("сегодня", 0)):
        if re.search(r"\b" + word + r"\b", text, re.I):
            found.append(day + timedelta(days=delta))
    return found


def validate_extraction(text, payload, received_at):
    """Return safe normalized data + handoff reasons; no model confidence bypass."""
    reasons = []
    try:
        extracted = Extraction.model_validate(payload).model_dump()
    except (ValueError, TypeError):
        return {"intent": "unknown", "action": "manual_review", "evidence": []}, ["invalid_schema"]
    intent = extracted["intent"]
    extracted["action"] = {"promise": "record_promise", "dispute": "record_dispute",
                           "payment_claim": "verify_payment", "unknown": "manual_review"}[intent]
    if INJECTION.search(text):
        reasons.append("untrusted_instruction")
    if QUOTED.search(text):
        reasons.append("quoted_history")
    if extracted["ambiguous"]:
        reasons.append("ambiguous")
    if intent == "unknown":
        reasons.append("unknown_intent")
    evidence = {}
    for item in extracted["evidence"]:
        if item["quote"] not in text:
            reasons.append("evidence_mismatch")
        else:
            item["start"] = text.index(item["quote"])
            item["end"] = item["start"] + len(item["quote"])
        evidence.setdefault(item["field"], []).append(item["quote"])
    intent_text = " ".join(evidence.get("intent", []))
    if not intent_text or (intent in INTENTS and not INTENTS[intent].search(intent_text)):
        reasons.append("intent_unverified")
    if intent == "promise" and NEGATION.search(text):
        reasons.append("negated_promise")
    if intent == "payment_claim" and NEGATION.search(text):
        reasons.append("negated_claim")
    if extracted["amount_kopeks"] is not None:
        supported = amounts(" ".join(evidence.get("amount", [])))
        if extracted["amount_kopeks"] not in supported:
            reasons.append("amount_mismatch")
        if extracted["currency"] != "RUB" or FOREIGN.search(text):
            reasons.append("currency_unsupported")
    elif intent == "promise":
        reasons.append("amount_required")
    if extracted["due_date"] is not None:
        try:
            selected = date.fromisoformat(extracted["due_date"])
            supported = dates(" ".join(evidence.get("due_date", [])), received_at)
            if not supported:
                reasons.append("date_unverified")
            elif selected not in supported:
                reasons.append("date_mismatch")
        except (ValueError, TypeError):
            reasons.append("date_unverified")
    elif intent == "promise":
        reasons.append("date_required")
    if intent == "promise":
        if len(set(amounts(text))) != 1 or len(set(dates(text, received_at))) != 1:
            reasons.append("ambiguous_facts")
    return extracted, list(dict.fromkeys(reasons))
