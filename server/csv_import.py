"""Deterministic CSV import with decimal money parsing and row-local diagnostics."""
import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from .models import InvoiceInput

HEADERS = {
    "контрагент": "company", "компания": "company", "инн": "inn", "email": "email",
    "e-mail": "email", "номер": "number", "номер счета": "number", "номер счёта": "number",
    "дата": "issued_on", "дата счета": "issued_on", "дата счёта": "issued_on",
    "срок": "due_on", "срок оплаты": "due_on", "сумма": "amount", "примечание": "notes",
    **{key: key for key in ("company", "inn", "number", "issued_on", "due_on", "amount", "notes")},
}
REQUIRED = {"company", "number", "issued_on", "due_on", "amount"}


def rubles_to_kopeks(raw):
    cleaned = re.sub(r"[\s\u00a0\u202f]", "", raw).replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", cleaned):
        raise ValueError("Сумма должна быть положительной, не более двух знаков после запятой")
    try:
        return int(Decimal(cleaned) * 100)
    except InvalidOperation as error:
        raise ValueError("Некорректная сумма") from error


def parse_date(raw):
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Дата должна быть в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД")


def parse_csv(content):
    content = content.lstrip("\ufeff")
    first_line = content.splitlines()[0] if content.splitlines() else ""
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    items, errors = [], []
    try:
        reader = csv.reader(io.StringIO(content), delimiter=delimiter, strict=True)
        raw_headers = next(reader, [])
        headers = [HEADERS.get(header.strip().lower(), header.strip().lower()) for header in raw_headers]
        if len(set(headers)) != len(headers):
            return [], [{"row": 1, "message": "Названия столбцов не должны повторяться"}]
        missing = REQUIRED.difference(headers)
        if missing:
            return [], [{"row": 1, "message": "Не хватает столбцов: " + ", ".join(sorted(missing))}]
        for line_no, row in enumerate(reader, 2):
            if line_no > 10001:
                errors.append({"row": line_no, "message": "Не более 10 000 счетов за один импорт"})
                break
            if not any(value.strip() for value in row):
                continue
            if len(row) != len(headers):
                errors.append({"row": line_no, "message": "Количество ячеек не совпадает с заголовком"})
                continue
            data = {key: value.strip() for key, value in zip(headers, row) if key in HEADERS.values()}
            try:
                data["amount"] = rubles_to_kopeks(data["amount"])
                data["issued_on"] = parse_date(data["issued_on"])
                data["due_on"] = parse_date(data["due_on"])
                items.append(InvoiceInput.model_validate(data).model_dump(mode="json"))
            except ValidationError as error:
                detail = error.errors()[0]
                field = str(detail["loc"][0]) if detail["loc"] else "счёт"
                errors.append({"row": line_no, "message": field + ": " + detail["msg"]})
            except (ValueError, KeyError) as error:
                errors.append({"row": line_no, "message": str(error)})
    except csv.Error:
        errors.append({"row": len(items) + 2, "message": "Некорректное экранирование CSV"})
    if not items and not errors:
        errors.append({"row": 2, "message": "В файле нет счетов"})
    return items, errors
