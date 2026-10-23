"""Strict public input contracts. All API monetary values are integer kopeks."""
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .business_time import business_today

Money = Annotated[StrictInt, Field(gt=0, le=1_000_000_000_000_000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def single_line(value):
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Поле не должно содержать управляющих символов")
    return value.strip()


def valid_email(value, *, optional=False):
    value = value.strip()
    if optional and not value:
        return ""
    try:
        local, domain = value.rsplit("@", 1)
        domain = domain.encode("idna").decode("ascii").lower()
        labels = domain.split(".")
        valid_domain = len(labels) >= 2 and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
    except (ValueError, UnicodeError):
        raise ValueError("Укажите корректный email") from None
    if (not re.fullmatch(r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
            or local.startswith(".") or local.endswith(".") or ".." in local
            or not valid_domain or len(value) > 254):
        raise ValueError("Укажите корректный email")
    return local.lower() + "@" + domain


class Login(Input):
    # Password bytes are significant: never trim or case-fold them.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        return valid_email(value)


class Register(Login):
    name: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=256)

    @field_validator("name", "company", mode="before")
    @classmethod
    def header_safe(cls, value):
        return single_line(value) if isinstance(value, str) else value


class InvoiceInput(Input):
    company: str = Field(min_length=1, max_length=200)
    inn: str = Field(default="", max_length=12)
    email: str = Field(default="", max_length=254)
    number: str = Field(min_length=1, max_length=100)
    issued_on: date
    due_on: date
    amount: Money
    notes: str = Field(default="", max_length=5000)

    @field_validator("company", "number", mode="before")
    @classmethod
    def header_safe(cls, value):
        return single_line(value) if isinstance(value, str) else value

    @field_validator("inn")
    @classmethod
    def inn_format(cls, value):
        if value and not re.fullmatch(r"\d{10}|\d{12}", value):
            raise ValueError("ИНН должен содержать 10 или 12 цифр")
        return value

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        return valid_email(value, optional=True)

    @model_validator(mode="after")
    def dates_valid(self):
        if self.due_on < self.issued_on:
            raise ValueError("Срок оплаты не может быть раньше даты счёта")
        return self


class CSVInput(Input):
    content: str = Field(min_length=1, max_length=1_500_000)


class DraftInput(Input):
    tone: Literal["soft", "firm"] = "soft"


class MessageInput(Input):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("subject")
    @classmethod
    def subject_single_line(cls, value):
        if any(char in value for char in "\r\n\x00"):
            raise ValueError("Тема должна быть одной строкой")
        return value


class PaymentInput(Input):
    amount: Money
    paid_on: date
    reference: str = Field(min_length=1, max_length=200)

    @field_validator("paid_on")
    @classmethod
    def real_payment_date(cls, value):
        if value > business_today():
            raise ValueError("Дата фактического платежа не может быть в будущем")
        return value


class PromiseInput(Input):
    date: date

    @field_validator("date")
    @classmethod
    def promise_not_past(cls, value):
        if value < business_today():
            raise ValueError("Укажите сегодняшнюю или будущую дату обещания")
        return value


class StatusInput(Input):
    status: Literal["open", "disputed", "paused"]
    notes: str | None = Field(default=None, max_length=5000)


class ContactInput(Input):
    email: str = Field(max_length=254)
    notes: str = Field(max_length=5000)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        return valid_email(value, optional=True)


class SettingsInput(Input):
    company: str | None = Field(default=None, min_length=1, max_length=200)
    sender_name: str | None = Field(default=None, max_length=200)
    reply_to: str | None = Field(default=None, max_length=254)
    bank_details: str | None = Field(default=None, max_length=3000)
    annual_rate: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    cooldown_days: StrictInt | None = Field(default=None, ge=0, le=365)

    @field_validator("company", "sender_name", mode="before")
    @classmethod
    def header_safe(cls, value):
        return single_line(value) if isinstance(value, str) else value

    @field_validator("reply_to")
    @classmethod
    def email_format(cls, value):
        return valid_email(value, optional=True) if value is not None else None
