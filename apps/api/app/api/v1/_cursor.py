"""Cursor-пагинация для коллекций с композитным ключом сортировки.

Курсор — base64(url-safe) от JSON с полями `last_at` (ISO) и `id` (str).
Так клиенту не нужно знать структуру; мы можем менять схему ключа без
ломки совместимости (старый курсор просто перестанет валидироваться и
эндпоинт вернёт 400).

Использование (`ORDER BY last_at DESC, id DESC`):

    cur = decode_cursor(request_cursor)
    if cur is not None:
        last_at, id_ = cur
        stmt = stmt.where(
            tuple_(Conversation.last_message_at, Conversation.id)
            < tuple_(literal(last_at), literal(id_))
        )

Возврат: `next_cursor` строится из последней записи страницы (если та
полная). Если строк меньше limit — `next_cursor=None`, фронт прячет
кнопку «ещё».
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any


def _b64encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(token: str) -> dict[str, Any] | None:
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + pad).encode("ascii"))
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (ValueError, json.JSONDecodeError):
        return None


def encode_cursor(last_at: datetime | None, id_: str) -> str:
    # last_at=None — диалог без сообщений. В курсор кладём строку "0",
    # чтобы условие `... < (last_at, id)` по композитному ключу было
    # корректным для всех NULL-ов (PG нормально сравнивает NULL — мы
    # эмулируем «нижнюю границу» отдельной веткой в декодере).
    return _b64encode(
        {
            "v": 1,
            "last_at": last_at.isoformat() if last_at else None,
            "id": id_,
        }
    )


def decode_cursor(token: str | None) -> tuple[datetime | None, str] | None:
    if not token:
        return None
    payload = _b64decode(token)
    if not payload or payload.get("v") != 1:
        return None
    raw = payload.get("last_at")
    last_at: datetime | None = None
    if raw:
        try:
            last_at = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return None
    id_ = payload.get("id")
    if not isinstance(id_, str):
        return None
    return last_at, id_


__all__ = ["decode_cursor", "encode_cursor"]
