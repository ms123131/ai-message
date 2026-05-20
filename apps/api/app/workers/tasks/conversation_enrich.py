"""Дотягивание одного диалога из Open Channels по chat_id.

Зачем: webhook `OnOpenLineMessageAdd` создаёт Conversation+Message «на лету»,
но не подтягивает CRM-привязки и метаданные сессии (operator, line, контакт,
сделка/лид). Эти данные есть только в `imopenlines.session.history.get`.

Эта задача — лёгкая «достройка одного чата»: достаёт session.history,
обновляет поля диалога, создаёт ConversationCrmLink и CrmEntity, не дёргая
весь `im.recent.get` поллера.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Conversation, Integration
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixAPIError, BitrixClient
from app.integrations.bitrix24.crm import (
    enrich_entities,
    extract_crm_refs_from_session,
    sync_stages_cache,
    upsert_link,
)
from app.integrations.bitrix24.importer import (
    _channel_from_entity_id,
    _extract_contact,
    _line_id_from_entity_id,
    _recompute_conversation_analytics,
    _session_is_closed,
    _session_meta,
)
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)


async def enrich_conversation_from_chat(
    ctx: dict[str, Any], integration_id: str, chat_id: str
) -> dict[str, int]:
    """Дотягивает session.history для одного chat_id и обновляет Conversation+CRM.

    Возвращает счётчики: {crm_links_added, skipped}. Идемпотентна: всё на upsert'ах.
    """
    settings = get_settings()
    ttl = settings.worker_portal_lock_ttl_sec
    redis = ctx["redis"]

    async with portal_lock(redis, integration_id, ttl_sec=ttl, kind="poll") as got:
        if not got:
            return {"crm_links_added": 0, "skipped": 1}

        async with AsyncSessionLocal() as session:
            integration = await session.get(Integration, integration_id)
            if integration is None:
                return {"crm_links_added": 0, "skipped": 1}

            conv = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.integration_id == integration_id,
                        Conversation.external_id == str(chat_id),
                    )
                )
            ).scalar_one_or_none()
            if conv is None:
                logger.debug(
                    "enrich: conv not found integration=%s chat_id=%s",
                    integration_id,
                    chat_id,
                )
                return {"crm_links_added": 0, "skipped": 1}

            refs: list = []
            try:
                async with BitrixClient(integration, session) as client:
                    try:
                        history = await client.call(
                            "imopenlines.session.history.get",
                            {"CHAT_ID": int(chat_id)},
                        )
                    except (BitrixAPIError, ValueError) as exc:
                        logger.warning(
                            "enrich: history.get failed chat_id=%s: %s",
                            chat_id,
                            exc,
                        )
                        return {"crm_links_added": 0, "skipped": 1}
                    if not isinstance(history, dict):
                        return {"crm_links_added": 0, "skipped": 1}

                    chat_meta = {}
                    if isinstance(history.get("chat"), dict):
                        chat_meta = history["chat"].get(str(chat_id), {}) or {}
                    users = history.get("users") or {}
                    contact_name, contact_external_id = _extract_contact(
                        users, chat_meta
                    )
                    entity_id_raw = chat_meta.get("entityId") or chat_meta.get(
                        "entity_id"
                    )
                    channel = _channel_from_entity_id(entity_id_raw)
                    is_closed = _session_is_closed(history)
                    operator_id, line_id = _session_meta(history)
                    if not line_id:
                        line_id = _line_id_from_entity_id(entity_id_raw)

                    # Метаданные диалога — заполняем, если webhook оставил пустым.
                    if contact_name and not conv.contact_name:
                        conv.contact_name = contact_name
                    if contact_external_id and not conv.contact_external_id:
                        conv.contact_external_id = contact_external_id
                    if operator_id and conv.assigned_user_id != operator_id:
                        conv.assigned_user_id = operator_id
                    if line_id and conv.line_id != line_id:
                        conv.line_id = line_id
                    if channel and conv.channel != channel:
                        conv.channel = channel

                    from app.db.models import ConversationStatus

                    target = (
                        ConversationStatus.closed
                        if is_closed
                        else ConversationStatus.open
                    )
                    if conv.status != target:
                        conv.status = target

                    await _recompute_conversation_analytics(session, conv)

                    refs = extract_crm_refs_from_session(history)
                    if refs:
                        kinds = {kind for kind, _ in refs}
                        stage_index = await sync_stages_cache(
                            client, session, integration, kinds
                        )
                        new_entities = []
                        for kind, ext_id in refs:
                            ent = await upsert_link(
                                session,
                                integration,
                                conv,
                                kind=kind,
                                external_id=ext_id,
                            )
                            new_entities.append(ent)
                        await enrich_entities(
                            client, session, integration, new_entities, stage_index
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "enrich: integration=%s chat_id=%s failed: %s",
                    integration_id,
                    chat_id,
                    exc,
                )
                return {"crm_links_added": 0, "skipped": 1}

            await session.commit()
            return {"crm_links_added": len(refs) if refs else 0, "skipped": 0}
