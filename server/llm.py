"""Optional generic wording only; this module never receives customer records.

Official request contract checked 2026-10-24:
https://aistudio.yandex.ru/en/docs/ai-studio/text-generation/api-ref/TextGeneration/completion
"""
import json
import os
import re
import hashlib
import threading
import time

import httpx

ENDPOINT = "https://ai.api.cloud.yandex.net/foundationModels/v1/completion"
FORBIDDEN = re.compile(r"руб|копе|сумм|стоим|процент|скид|реквизит|банк|карт|бик|сч[её]т|суд|штраф|пен[яию]|закон|пристав|иск|угроз|санкц|обязат|долг|задолж|немед|претенз|коллект|уголов|арест|изъят|досудеб|должны|перевед|перечисл|срочн", re.IGNORECASE)
CHARACTERS = re.compile(r"[А-Яа-яЁё .,!?;:—–()«»\"\-]+")
# An allowlist makes semantic scope small: no newly invented action, amount,
# condition, recipient, legal claim or physical visit can pass this boundary.
VOCABULARY = set("""подскажите пожалуйста когда планируется оплата просим сообщить
дату оплаты и подтвердить её ее ответным письмом если нужны документы для сверки
сообщите нам по поставке есть разногласия детали благодарим вас за обратную связь
можете ли вы уточнить ожидаемую направить информацию планируемой дате ожидаем
вашего ответа поможем подготовить недостающие уточняющие уточнения уточните чтобы
проверить данные добрый день здравствуйте приветствуем уважением спасибо
сотрудничество благодарностью ответ с о в готовы будем признательны""".split())
_cache = {}
_cache_lock = threading.Lock()


def configured():
    return bool(os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_MODEL"))


def fallback(tone):
    return {
        "greeting": "Здравствуйте!",
        "request": "Подскажите, пожалуйста, когда планируется оплата? Если нужны документы для сверки, сообщите нам." if tone == "soft" else "Просим сообщить дату оплаты и подтвердить её ответным письмом. Если по поставке есть разногласия, сообщите детали для сверки.",
        "closing": "С уважением,",
    }


def validate_fragments(value):
    if not isinstance(value, dict) or set(value) != {"greeting", "request", "closing"}:
        raise ValueError("Invalid fragment structure")
    for key, text in value.items():
        maximum = 240 if key == "request" else 80
        if not isinstance(text, str) or not 2 <= len(text) <= maximum:
            raise ValueError("Invalid fragment length")
        if not CHARACTERS.fullmatch(text) or FORBIDDEN.search(text):
            raise ValueError("Unsafe generated wording")
        if any(word.casefold() not in VOCABULARY for word in re.findall(r"[А-Яа-яЁё]+", text)):
            raise ValueError("Generated wording exceeds the permitted vocabulary")
    return {key: text.strip() for key, text in value.items()}


def phrases(tone):
    """Return (safe fragments, source). Input is a two-value tone enum only."""
    if tone not in ("soft", "firm") or not configured():
        return fallback(tone), "template"
    key = (tone, hashlib.sha256(os.environ["YANDEX_API_KEY"].encode()).hexdigest(), os.environ["YANDEX_MODEL"])
    # The request depends only on tone. Reuse it across tenants without customer
    # data; serialize misses to avoid paid-call amplification from public signup.
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            return dict(cached[1]), cached[2]
        result, source = _generate(tone)
        if len(_cache) > 8:
            _cache.clear()
        _cache[key] = (time.monotonic() + (300 if source == "yandex" else 30), dict(result), source)
        return result, source


def _generate(tone):
    payload = {
        "modelUri": os.environ["YANDEX_MODEL"],
        "completionOptions": {"stream": False, "temperature": 0.15, "maxTokens": "220"},
        "jsonObject": True,
        "messages": [
            {"role": "system", "text": "Составь только нейтральные общие фразы делового письма на русском. Верни JSON с тремя строками greeting, request, closing. Приветствие и завершение до восьмидесяти символов, просьба сообщить планируемую дату оплаты до двухсот сорока символов. Только русские буквы, пробелы и обычная пунктуация. Не используй цифры, факты о получателе, суммы словами, угрозы, правовые обещания, сроки, скидки, реквизиты и ссылки."},
            {"role": "user", "text": "Тон: " + tone + ". Сформулируй приветствие, просьбу сообщить дату оплаты и вежливое завершение. Только JSON."},
        ],
    }
    try:
        response = httpx.post(ENDPOINT, json=payload,
                              headers={"Authorization": "Api-Key " + os.environ["YANDEX_API_KEY"]},
                              timeout=7.0, follow_redirects=False, trust_env=False)
        response.raise_for_status()
        if len(response.content) > 32000:
            raise ValueError("Oversized provider response")
        result = response.json()
        # Both the established result envelope and current documented direct body.
        text = result.get("result", result)["alternatives"][0]["message"]["text"]
        fragments = validate_fragments(json.loads(text))
        return fragments, "yandex"
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return fallback(tone), "template"
