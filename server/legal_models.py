"""Input facts supplied by a client/operator and explicitly reviewed by a human."""
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from .business_time import business_today
from .models import Input, Money, valid_email
from .legal_fees import TARIFF


class LegalInput(Input):
    @field_validator("*",mode="before")
    @classmethod
    def xml_safe_text(cls,value):
        if isinstance(value,str) and any(not (ord(c) in (9,10,13) or 0x20<=ord(c)<=0xD7FF or 0xE000<=ord(c)<=0xFFFD or 0x10000<=ord(c)<=0x10FFFF) for c in value):
            raise ValueError("Текст содержит недопустимые символы")
        return value


Percent=Annotated[str,Field(pattern=r"^\d{1,4}(?:\.\d{1,8})?$",max_length=14)]


class RatePeriod(LegalInput):
    from_on:date
    to_on:date
    annual_percent:Percent
    source:str=Field(min_length=3,max_length=1000)


class ExcludedPeriod(LegalInput):
    from_on:date
    to_on:date
    basis:str=Field(min_length=3,max_length=3000)


class OpeningReduction(LegalInput):
    effective_on:date
    amount:Money
    evidence:str=Field(min_length=3,max_length=2000)


class Calculation(LegalInput):
    through_on:date
    sanction:Literal["none","penalty","art395","both"]="none"
    penalty_agreed:StrictBool=False
    penalty_daily_percent:Percent|None=None
    penalty_basis:str=Field(default="",max_length=5000)
    penalty_cap_amount:Annotated[StrictInt,Field(ge=0,le=1_000_000_000_000_000)]|None=None
    combination_basis:str=Field(default="",max_length=5000)
    rate_override:list[RatePeriod]|None=Field(default=None,max_length=500)
    override_reason:str=Field(default="",max_length=3000)
    excluded_periods:list[ExcludedPeriod]=Field(default_factory=list,max_length=100)
    opening_reductions:list[OpeningReduction]=Field(default_factory=list,max_length=1000)

    @field_validator("through_on")
    @classmethod
    def not_future(cls,value):
        if value>business_today():raise ValueError("Расчёт возможен по сегодняшнюю или прошлую дату")
        return value


class CalculationRequest(Calculation):
    invoice_id:str=Field(min_length=1,max_length=100)


class Party(LegalInput):
    kind:Literal["organization","sole_proprietor"]="organization"
    name:str=Field(default="",max_length=300)
    inn:str=Field(default="",max_length=12)
    ogrn:str=Field(default="",max_length=15)
    address:str=Field(default="",max_length=2000)
    email:str=Field(default="",max_length=254)
    phone:str=Field(default="",max_length=100)
    bank_details:str=Field(default="",max_length=3000)
    birth_on:date|None=None
    birth_place:str=Field(default="",max_length=500)
    birth_details_unknown:StrictBool=False

    @field_validator("email")
    @classmethod
    def mailbox(cls,value):return valid_email(value,optional=True)

    @model_validator(mode="after")
    def identifiers(self):
        if self.inn and not re.fullmatch(r"[0-9]{10}" if self.kind=="organization" else r"[0-9]{12}",self.inn):
            raise ValueError("Проверьте ИНН организации/ИП")
        if self.ogrn and not re.fullmatch(r"[0-9]{13}" if self.kind=="organization" else r"[0-9]{15}",self.ogrn):
            raise ValueError("Проверьте ОГРН/ОГРНИП")
        return self


class CaseFacts(LegalInput):
    creditor:Party=Field(default_factory=Party)
    debtor:Party=Field(default_factory=Party)
    contract_number:str=Field(default="",max_length=200)
    contract_date:date|None=None
    obligation_description:str=Field(default="",max_length=10000)
    performance_description:str=Field(default="",max_length=10000)
    due_basis:str=Field(default="",max_length=5000)
    legal_basis:str=Field(default="",max_length=10000)
    court_name:str=Field(default="",max_length=500)
    court_address:str=Field(default="",max_length=2000)
    jurisdiction_basis:str=Field(default="",max_length=5000)
    undisputed:StrictBool=False
    business_debt_confirmed:StrictBool=False
    special_regimes_checked:StrictBool=False
    pretrial_days:StrictInt=Field(default=30,ge=0,le=365)
    pretrial_basis:str=Field(default="Часть 5 статьи 4 АПК РФ",max_length=5000)
    fee_agreement_reference:str=Field(default="",max_length=1000)
    fee_start_on:date|None=None
    fee_model_version:Literal["mandato-2026-10-26"]=TARIFF['version']
    lawyer_agreement_reference:str=Field(default="",max_length=1000)

    @model_validator(mode="after")
    def explicit_terms(self):
        if self.pretrial_days!=30 and (len(self.pretrial_basis.strip())<10 or self.pretrial_basis.strip()=="Часть 5 статьи 4 АПК РФ"):
            raise ValueError("Иной срок претензии требует основания в законе/договоре")
        if self.fee_start_on and self.fee_start_on>business_today():
            raise ValueError("Дата начала сопровождения не может быть в будущем")
        return self


class CaseCreate(LegalInput):
    invoice_id:str=Field(min_length=1,max_length=100)
    facts:CaseFacts=Field(default_factory=CaseFacts)


class CaseUpdate(LegalInput):
    facts:CaseFacts


class Evidence(LegalInput):
    kind:Literal["contract","performance","reconciliation","claim_dispatch","claim_delivery","duty_payment","application_copy_sent","filing_receipt","court_act","writ","bank_submission","fssp_submission","other"]
    title:str=Field(min_length=1,max_length=300)
    reference:str=Field(min_length=1,max_length=3000)
    occurred_on:date
    sha256:str=Field(default="",pattern=r"^(?:[a-fA-F0-9]{64})?$")

    @field_validator("occurred_on")
    @classmethod
    def occurred(cls,value):
        if value>business_today():raise ValueError("Нельзя подтвердить будущее событие")
        return value


class DocumentCreate(LegalInput):
    kind:Literal["pretrial_claim","court_order","statement_of_claim"]
    calculation:Calculation


class Review(LegalInput):
    decision:Literal["approved","changes_requested"]
    reviewer_name:str=Field(min_length=1,max_length=300)
    authority_reference:str=Field(min_length=3,max_length=2000)
    qualification_confirmed:StrictBool
    notes:str=Field(min_length=3,max_length=5000)

    @model_validator(mode="after")
    def attested_review(self):
        if self.decision=="approved" and not self.qualification_confirmed:
            raise ValueError("Подтвердите проверку уполномоченным квалифицированным лицом")
        return self


class Milestone(LegalInput):
    stage:Literal["claim_sent","claim_delivered","filed","order_issued","judgment","writ_received","bank_submitted","fssp_submitted","stopped","closed"]
    occurred_on:date
    reference:str=Field(min_length=1,max_length=2000)
    notes:str=Field(min_length=3,max_length=5000)
    document_id:str|None=Field(default=None,max_length=100)
    evidence_ids:list[str]=Field(default_factory=list,max_length=100)

    @field_validator("occurred_on")
    @classmethod
    def occurred(cls,value):
        if value>business_today():raise ValueError("Укажите дату уже состоявшегося ручного действия")
        return value
