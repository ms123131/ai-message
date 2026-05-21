"""Извлечение сущностей из текста сообщений (фаза 6.6).

Архитектура:
- Регулярки — для всего, где есть строгая форма: телефоны, email, URL,
  трек-номера (СДЭК/Boxberry/PostRU/DHL/EMS/USPS), денежные суммы.
- Natasha — для русского NER: имена, города, организации. Работает локально
  на CPU, без сети и токенов. Модели грузятся один раз lazy (см. _get_*),
  потом переиспользуются — иначе на батче в 200 сообщений было бы по 200
  загрузок ~150мб эмбеддингов.

Возвращаемый формат — flat dict вида:
    {"phone": ["+79991234567"], "email": ["a@b.ru"], "money": [{...}], ...}
Пустые категории не включаем — БД хранит компактный JSON.

Дизайн-решение: Natasha может не быть установлена в окружении (тонкий
test-runner, минимальный CI). Импорт обёрнут в try/except, при отсутствии
NER часть просто пропускается, регулярки работают всегда.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Регулярки
# ---------------------------------------------------------------------------

# Email. Хвостовая пунктуация типа «a@b.ru.» — точку срежем в постобработке.
_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# URL — http(s) или www. Без хвостовой пунктуации.
_RE_URL = re.compile(
    r"\b(?:https?://|www\.)[^\s<>\"']+",
    re.IGNORECASE,
)

# Социальные хэндлы (Telegram, Instagram, X). @username длиной 3-32 символа.
# В начале строки или после пробела/пунктуации (но не после @ или буквы —
# чтобы не цеплять email-хвосты).
_RE_SOCIAL = re.compile(
    r"(?:(?<=^)|(?<=[\s,.;:!?()\[\]{}|]))@([A-Za-z][A-Za-z0-9_]{2,31})\b"
)

# Российский номер телефона. Принимаем форматы:
#   +7 999 123-45-67, 8(999)123-45-67, 79991234567, +7-999-123-4567,
#   а также голые 11 цифр начинающихся с 7.
_RE_PHONE_RU = re.compile(
    r"(?:(?<=\D)|(?<=^))"
    r"(?:\+?7|8)[\s\-().]?"
    r"\(?\d{3}\)?[\s\-().]?"
    r"\d{3}[\s\-().]?"
    r"\d{2}[\s\-().]?"
    r"\d{2}"
    r"(?!\d)"
)

# Международные номера. Строго с +, длина 8-15 цифр (E.164). Без + слишком
# легко ловить трек-номера и артикулы — тогда только RU-формы выше.
_RE_PHONE_INTL = re.compile(
    r"(?:(?<=\D)|(?<=^))"
    r"\+(?:[1-9]\d{0,2})"  # country code 1-3 цифры, не начинается с 0
    r"[\s\-().]?"
    r"(?:\d[\s\-().]?){6,14}"  # 7-15 цифр всего после кода
    r"(?!\d)"
)

# Telegram/SIP-явные ссылки t.me/, tg://, telegram.me/ — уже в URL.

# ИНН — 10 цифр (юрлицо) или 12 цифр (физлицо/ИП). Без контекста
# легко перепутать с другим числом, поэтому требуем хинт.
_RE_INN = re.compile(
    r"\bИНН\D{0,10}?([0-9]{10}|[0-9]{12})\b",
    re.IGNORECASE,
)
# ОГРН — 13 цифр (юр), ОГРНИП — 15 цифр (ИП). Формат уникальный, можно
# и без хинта, но требование хинта снижает false positive.
_RE_OGRN = re.compile(
    r"\bОГРН(?:ИП)?\D{0,10}?([0-9]{13}|[0-9]{15})\b",
    re.IGNORECASE,
)
# КПП — 9 цифр, всегда упоминается явно.
_RE_KPP = re.compile(
    r"\bКПП\D{0,10}?([0-9]{9})\b",
    re.IGNORECASE,
)
# Расчётный счёт — 20 цифр (обычно с «р/с» или «счёт»).
_RE_ACCOUNT = re.compile(
    r"\b(?:р/?с|расч[её]тный\s+сч[её]т|сч[её]т|account)\D{0,10}?([0-9]{20})\b",
    re.IGNORECASE,
)

# Номер банковской карты — 13-19 цифр, чаще всего 16, в виде 4 групп по 4.
# Маскируется в постобработке. Luhn-валидация повышает precision.
_RE_CARD = re.compile(
    r"\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7})\b"
)

# IBAN — XX(2 буквы страны) + 2 контрольные цифры + 11-30 alphanumeric.
# Без пробелов в исходнике или с пробелами через каждые 4 символа.
_RE_IBAN = re.compile(
    r"\b([A-Z]{2}\d{2}(?:[\s]?[A-Z0-9]{4}){2,7}[\s]?[A-Z0-9]{0,4})\b"
)

# Дата — DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD.
_RE_DATE = re.compile(
    r"\b("
    r"(?:0?[1-9]|[12]\d|3[01])[./\-](?:0?[1-9]|1[0-2])[./\-]\d{2,4}"
    r"|\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r")\b"
)

# Денежная сумма с валютой. «1 000 руб», «1500₽», «$199.99», «12,5 тыс. ₽».
# Возвращаем нормализованный amount как float + currency-код ISO.
_CURRENCY_MAP = {
    "₽": "RUB", "руб": "RUB", "руб.": "RUB", "рублей": "RUB", "р.": "RUB",
    "$": "USD", "usd": "USD",
    "€": "EUR", "eur": "EUR",
    "₸": "KZT", "тенге": "KZT",
    "₴": "UAH", "грн": "UAH",
}
_RE_MONEY = re.compile(
    r"(?P<pre>[$€₽₸₴])?\s?"
    # Либо группами «1 000» / «1,500.99», либо просто «2500» / «12.5»
    r"(?P<num>\d{1,3}(?:[\s.,\xa0]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s?(?P<post>₽|\$|€|₸|₴|руб\.?|рублей|р\.|usd|eur|тенге|грн)?",
    re.IGNORECASE,
)

# Трек-номер посылки. Грубо: 10-20 алфанумерик с буквами и цифрами вместе
# (чтобы отсечь обычные числа и слова). Префикс ключевых слов «трек/track»
# поднимает достоверность.
_RE_TRACKING_HINT = re.compile(
    r"(?:трек[-\s]?номер|трек\b|track\s*number|трекинг|tracking|"
    r"номер\s+отправлен[ия]\w*)\D{0,10}([A-Z0-9]{8,30})",
    re.IGNORECASE,
)
# Самостоятельные трек-номера известных форматов (без хинта):
#   EMS/Почта России: 13 символов XX123456789YY
#   UPS: 1Z + 16 символов
#   Boxberry: 6-8 буквенно-цифровых (например BSP1234567)
#   СДЭК: новые — 10 цифр; старые трек-коды — 8-12 alphanumeric
#   DHL/FedEx-подобные: 12-14 цифр
_RE_TRACKING_KNOWN = re.compile(
    r"\b(?:"
    r"[A-Z]{2}\d{9}[A-Z]{2}"  # EMS / Почта России
    r"|1Z[A-Z0-9]{16}"  # UPS
    r"|BSP\d{6,10}"  # Boxberry SP
    r"|BB\d{8,12}"  # Boxberry
    r"|\d{12,14}"  # DHL/FedEx/DPD
    r")\b"
)


def _parse_money_amount(num_raw: str) -> float | None:
    """Из «1 000,50» / «1,500.99» делает float. Эвристика: если есть и
    точка, и запятая — последний из них — десятичный разделитель."""
    s = num_raw.strip()
    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        # Десятичный — тот, что правее
        dec_sep = "." if s.rfind(".") > s.rfind(",") else ","
        thou_sep = "," if dec_sep == "." else "."
        s = s.replace(thou_sep, "").replace(dec_sep, ".")
    elif has_comma:
        # «1,5» — десятичный, «1,500» — разделитель тысяч.
        # Если справа от запятой ровно 3 цифры и одна запятая — тысячи.
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    s = s.replace(" ", "").replace("\xa0", "")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_money(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()
    for m in _RE_MONEY.finditer(text):
        pre = (m.group("pre") or "").lower()
        post = (m.group("post") or "").lower()
        currency = _CURRENCY_MAP.get(pre) or _CURRENCY_MAP.get(post)
        if not currency:
            # Без явной валюты денежной суммой не считаем — слишком много
            # ложных срабатываний на номерах телефонов, артикулах и пр.
            continue
        amount = _parse_money_amount(m.group("num"))
        if amount is None or amount <= 0:
            continue
        key = (amount, currency)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "amount": amount,
            "currency": currency,
            "raw": m.group(0).strip(),
        })
    return out


def _normalize_phone(raw: str) -> str:
    """+7 (999) 123-45-67 → +79991234567. 8XXX… → +7XXX…
    Международные оставляем как +XXXX (только цифры, без разделителей)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if digits and 8 <= len(digits) <= 15:
        return "+" + digits
    return raw.strip()


def _luhn_valid(card_digits: str) -> bool:
    """Алгоритм Луна — стандартная контрольная сумма банковских карт.
    Без этого regex 4×4 ловит любые наборы цифр (артикулы, треки)."""
    total = 0
    parity = len(card_digits) % 2
    for i, ch in enumerate(card_digits):
        n = int(ch)
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _mask_card(card_digits: str) -> str:
    """1234 5678 9012 3456 → **** **** **** 3456 — не светим полный номер."""
    last4 = card_digits[-4:]
    return f"**** **** **** {last4}"


def _normalize_iban(raw: str) -> str:
    return re.sub(r"\s+", "", raw.upper())


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _extract_regex(text: str) -> dict[str, Any]:
    """Извлекает всё, что находится регулярками. Pure function."""
    result: dict[str, Any] = {}

    # Email — точку в конце «спасибо, a@b.ru.» съедаем.
    emails = sorted(
        {m.group(0).rstrip(".,;:!?").lower() for m in _RE_EMAIL.finditer(text)}
    )
    if emails:
        result["email"] = emails

    urls = sorted({m.group(0).rstrip(".,;:!?)") for m in _RE_URL.finditer(text)})
    if urls:
        result["url"] = urls

    # Telegram/Instagram @username. Игнорим, если совпало внутри email
    # (защита уже в lookbehind regex).
    socials = sorted({"@" + m.group(1) for m in _RE_SOCIAL.finditer(text)})
    if socials:
        result["social"] = socials

    # Телефоны — сначала международные (с +), потом RU.
    phones: list[str] = []
    seen_phones: set[str] = set()
    for regex in (_RE_PHONE_INTL, _RE_PHONE_RU):
        for m in regex.finditer(text):
            norm = _normalize_phone(m.group(0))
            if norm not in seen_phones:
                seen_phones.add(norm)
                phones.append(norm)
    if phones:
        result["phone"] = phones

    money = _extract_money(text)
    if money:
        result["money"] = money

    # Реквизиты и идентификаторы юрлица.
    inns = sorted({m.group(1) for m in _RE_INN.finditer(text)})
    if inns:
        result["inn"] = inns
    ogrns = sorted({m.group(1) for m in _RE_OGRN.finditer(text)})
    if ogrns:
        result["ogrn"] = ogrns
    kpps = sorted({m.group(1) for m in _RE_KPP.finditer(text)})
    if kpps:
        result["kpp"] = kpps
    accounts = sorted({m.group(1) for m in _RE_ACCOUNT.finditer(text)})
    if accounts:
        result["account"] = accounts

    # Карты — Luhn-валидация. Маскируем, чтобы не светить полный PAN.
    cards: list[str] = []
    seen_cards: set[str] = set()
    for m in _RE_CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            masked = _mask_card(digits)
            if masked not in seen_cards:
                seen_cards.add(masked)
                cards.append(masked)
    if cards:
        result["card"] = cards

    # IBAN — strip пробелов в нормализации.
    ibans: list[str] = []
    seen_iban: set[str] = set()
    for m in _RE_IBAN.finditer(text):
        norm = _normalize_iban(m.group(1))
        # Минимальная длина IBAN — 15 (NO), максимальная — 34.
        if 15 <= len(norm) <= 34 and norm not in seen_iban:
            seen_iban.add(norm)
            ibans.append(norm)
    if ibans:
        result["iban"] = ibans

    # Даты — все варианты.
    dates = _dedupe([m.group(1) for m in _RE_DATE.finditer(text)])
    if dates:
        result["date"] = dates

    tracking: list[str] = []
    seen_t: set[str] = set()
    for m in _RE_TRACKING_HINT.finditer(text):
        t = m.group(1).upper()
        if t not in seen_t:
            seen_t.add(t)
            tracking.append(t)
    for m in _RE_TRACKING_KNOWN.finditer(text):
        t = m.group(0).upper()
        # Не подхватываем как трек то, что уже распознали как телефон/счёт/
        # дату/ИНН — длинные цифры пересекаются.
        digits_only = re.sub(r"\D", "", t)
        if digits_only and (
            "+" + digits_only in seen_phones
            or digits_only in inns
            or digits_only in ogrns
            or digits_only in accounts
        ):
            continue
        if t not in seen_t:
            seen_t.add(t)
            tracking.append(t)
    if tracking:
        result["tracking"] = tracking

    return result


# ---------------------------------------------------------------------------
# Natasha NER — lazy init
# ---------------------------------------------------------------------------

_natasha_state: dict[str, Any] = {"ready": None}


def _get_natasha():
    """Возвращает (segmenter, morph_tagger, ner_tagger, Doc) или None
    если Natasha не установлена. Инициализация однократная — модели весят
    ~150мб, грузить на каждый вызов разорительно."""
    cached = _natasha_state.get("ready")
    if cached is not None:
        return cached or None

    try:
        from natasha import (  # type: ignore[import-untyped]
            Doc,
            NewsEmbedding,
            NewsMorphTagger,
            NewsNERTagger,
            Segmenter,
        )
    except ImportError:
        logger.info(
            "entities: natasha не установлена — NER пропускается, "
            "регулярки продолжают работать"
        )
        _natasha_state["ready"] = False
        return None

    segmenter = Segmenter()
    emb = NewsEmbedding()
    morph_tagger = NewsMorphTagger(emb)
    ner_tagger = NewsNERTagger(emb)
    tools = (segmenter, morph_tagger, ner_tagger, Doc)
    _natasha_state["ready"] = tools
    return tools


# Маппинг типов сущностей Natasha → наши ключи. PER/LOC/ORG — стандарт.
_NATASHA_TYPE_MAP = {"PER": "person", "LOC": "location", "ORG": "organization"}


def _extract_natasha(text: str) -> dict[str, list[str]]:
    tools = _get_natasha()
    if not tools:
        return {}
    segmenter, morph_tagger, ner_tagger, Doc = tools

    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    doc.tag_ner(ner_tagger)

    out: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for span in doc.spans:
        key = _NATASHA_TYPE_MAP.get(span.type)
        if not key:
            continue
        value = span.text.strip()
        if not value or len(value) < 2:
            continue
        bucket = seen.setdefault(key, set())
        if value.lower() in bucket:
            continue
        bucket.add(value.lower())
        out.setdefault(key, []).append(value)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Слишком короткие сообщения проверять регулярками всё равно полезно
# (могут быть «8 999 …»), а NER — нет смысла.
_NER_MIN_TEXT_LEN = 16


def extract_entities(text: str) -> dict[str, Any]:
    """Извлекает все сущности из текста. Возвращает dict без пустых ключей.
    Pure-функция. Если текст пуст — пустой dict."""
    if not text or not text.strip():
        return {}

    result = _extract_regex(text)

    if len(text.strip()) >= _NER_MIN_TEXT_LEN:
        try:
            ner = _extract_natasha(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("entities: natasha failed: %s", exc)
            ner = {}
        for key, values in ner.items():
            result[key] = values

    return result


async def analyze_messages_entities_batch(
    session: AsyncSession,
    message_ids: list[str],
) -> int:
    """Извлекает сущности из переданных сообщений и пишет в БД.
    Возвращает число обработанных. Не коммитит — за вызывающим."""
    if not message_ids:
        return 0

    rows = (
        await session.execute(select(Message).where(Message.id.in_(message_ids)))
    ).scalars().all()

    processed = 0
    now = datetime.now(UTC)
    for msg in rows:
        if msg.entities is not None:
            continue
        try:
            ents = extract_entities(msg.text or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "entities: message %s failed: %s", msg.id, exc
            )
            continue
        # Пустой dict — валидный результат («ничего не нашли»), записываем,
        # чтобы воркер не возвращался к этому сообщению.
        msg.entities = ents
        msg.entities_at = now
        processed += 1
    return processed
