"""
CLI для административных операций. Запуск:

    python -m app.cli import-bitrix24 --integration-id <id> [--days 30]

Без внешних зависимостей — только stdlib argparse, чтобы не раздувать requirements.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys

from sqlalchemy import not_, or_, select, update

from app.db.models import (
    Conversation,
    ImportJob,
    Integration,
    Message,
)
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.crm import (
    extract_crm_refs_from_session,
    link_chats_for_integration,
    refresh_known_crm_entities,
)
from app.integrations.bitrix24.importer import run_import_job
from app.nlp.bitrix_system_text import SQL_LIKE_FRAGMENTS as _BITRIX_SYSTEM_LIKES
from app.nlp.sentiment import recompute_conversation_sentiment_score


async def _cmd_import_bitrix24(integration_id: str, days: int) -> int:
    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        if not integration:
            print(f"Integration {integration_id!r} not found", file=sys.stderr)
            return 2
        job = ImportJob(
            id=f"imp_{secrets.token_urlsafe(8).lower()}",
            integration_id=integration.id,
            days=days,
        )
        session.add(job)
        await session.commit()

        async with BitrixClient(integration, session) as client:
            await run_import_job(client, session, job, integration)

        print(
            f"job={job.id} status={job.status.value} "
            f"sessions={job.processed_sessions} messages={job.processed_messages}"
            + (f" error={job.error}" if job.error else "")
        )
        return 0 if job.status.value == "done" else 1


async def _cmd_debug_history(integration_id: str, chat_id: int, full: bool) -> int:
    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        if not integration:
            print(f"Integration {integration_id!r} not found", file=sys.stderr)
            return 2
        async with BitrixClient(integration, session) as client:
            history = await client.call(
                "imopenlines.session.history.get", {"CHAT_ID": chat_id}
            )
        if not isinstance(history, dict):
            print(f"non-dict response: {type(history).__name__}={history!r}")
            return 1

        sess = history.get("session")
        print(f"--- CHAT_ID={chat_id} ---")
        print(f"top-level keys: {sorted(history.keys())}")
        if isinstance(sess, dict):
            print(f"session keys: {sorted(sess.keys())}")
            for k in (
                "ID",
                "STATUS",
                "CONFIG_ID",
                "OPERATOR_ID",
                "CRM_ENTITY_TYPE",
                "CRM_ENTITY_ID",
                "CRM",
                "crm",
                "crm_entities",
                "CRM_ENTITIES",
            ):
                if k in sess:
                    print(f"  session[{k}] = {sess[k]!r}")
        else:
            print("session: <missing or non-dict>")
        refs = extract_crm_refs_from_session(history)
        print(f"extracted refs: {refs}")
        if full:
            print("--- raw history ---")
            print(json.dumps(history, ensure_ascii=False, indent=2, default=str))
        return 0


async def _cmd_crm_link(integration_id: str, days: int, limit: int) -> int:
    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        if not integration:
            print(f"Integration {integration_id!r} not found", file=sys.stderr)
            return 2
        async with BitrixClient(integration, session) as client:
            refreshed = await refresh_known_crm_entities(client, session, integration)
            stats = await link_chats_for_integration(
                client,
                session,
                integration,
                days=days,
                max_entities=limit,
            )
        print(
            f"refreshed={refreshed} entities_scanned={stats['entities_scanned']} "
            f"links_created={stats['links_created']}"
        )
        return 0


async def _cmd_cleanup_system_sentiment(integration_id: str | None) -> int:
    """Сбрасывает sentiment у Bitrix-служебных сообщений + пересчитывает
    `Conversation.sentiment_score` для затронутых диалогов.

    Зачем: до фикса воркер размечал «Начат новый диалог №...» и подобные
    тексты как neutral — они засоряли KPI и среднее по диалогу. Команда
    откатывает прошлую разметку, и при следующем запуске анализа в выборку
    они уже не попадут.
    """
    like_clauses = or_(*[Message.text.ilike(p) for p in _BITRIX_SYSTEM_LIKES])
    async with AsyncSessionLocal() as session:
        scope = select(Message.id, Message.conversation_id).where(
            Message.sentiment.is_not(None),
            like_clauses,
        )
        if integration_id:
            scope = scope.join(
                Conversation, Conversation.id == Message.conversation_id
            ).where(Conversation.integration_id == integration_id)
        rows = (await session.execute(scope)).all()
        if not rows:
            print("Нечего чистить — служебных сообщений с sentiment не найдено")
            return 0
        message_ids = [r[0] for r in rows]
        conv_ids = sorted({r[1] for r in rows})
        await session.execute(
            update(Message)
            .where(Message.id.in_(message_ids))
            .values(
                sentiment=None,
                sentiment_confidence=None,
                sentiment_at=None,
                sentiment_model=None,
            )
        )
        # Пересчёт денормализованного score по каждому затронутому диалогу.
        for cid in conv_ids:
            await recompute_conversation_sentiment_score(session, cid)
        await session.commit()
        print(
            f"cleanup-system-sentiment: messages_reset={len(message_ids)} "
            f"conversations_recomputed={len(conv_ids)}"
            + (f" integration={integration_id}" if integration_id else " (all)")
        )
        return 0


async def _cmd_mark_system_messages(integration_id: str | None) -> int:
    """Переключает sender_type=system у Bitrix-служебных сообщений.

    Применять после `cleanup-system-sentiment`. После этой команды
    /conversations/.../messages не будет светить служебку как «клиент»,
    и KPI «клиентских сообщений» станет честным.
    """
    from app.db.models import SenderType

    like_clauses = or_(*[Message.text.ilike(p) for p in _BITRIX_SYSTEM_LIKES])
    async with AsyncSessionLocal() as session:
        stmt = update(Message).where(
            like_clauses,
            not_(Message.sender_type == SenderType.system),
        )
        if integration_id:
            sub = select(Conversation.id).where(
                Conversation.integration_id == integration_id
            )
            stmt = stmt.where(Message.conversation_id.in_(sub))
        result = await session.execute(stmt.values(sender_type=SenderType.system))
        await session.commit()
        print(
            f"mark-system-messages: updated={result.rowcount or 0}"
            + (f" integration={integration_id}" if integration_id else " (all)")
        )
        return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="ai-message admin CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser(
        "import-bitrix24",
        help="Импорт исторических диалогов Open Channels из Bitrix24",
    )
    imp.add_argument("--integration-id", required=True)
    imp.add_argument("--days", type=int, default=30)

    dbg = sub.add_parser(
        "debug-history",
        help="Показать, что Bitrix отдаёт в imopenlines.session.history.get для chat_id",
    )
    dbg.add_argument("--integration-id", required=True)
    dbg.add_argument("--chat-id", type=int, required=True)
    dbg.add_argument(
        "--full", action="store_true", help="вывести raw history целиком"
    )

    link = sub.add_parser(
        "crm-link",
        help="Запустить обратный CRM-индекс (поиск сделок/лидов и привязка к диалогам)",
    )
    link.add_argument("--integration-id", required=True)
    link.add_argument("--days", type=int, default=30)
    link.add_argument(
        "--limit", type=int, default=1000, help="максимум сущностей за проход"
    )

    cs = sub.add_parser(
        "cleanup-system-sentiment",
        help="Сбросить sentiment у Bitrix-служебных сообщений и пересчитать score диалогов",
    )
    cs.add_argument("--integration-id", default=None)

    ms = sub.add_parser(
        "mark-system-messages",
        help="Перевести Bitrix-служебные сообщения в sender_type=system",
    )
    ms.add_argument("--integration-id", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "import-bitrix24":
        return asyncio.run(
            _cmd_import_bitrix24(args.integration_id, args.days)
        )
    if args.cmd == "debug-history":
        return asyncio.run(
            _cmd_debug_history(args.integration_id, args.chat_id, args.full)
        )
    if args.cmd == "crm-link":
        return asyncio.run(
            _cmd_crm_link(args.integration_id, args.days, args.limit)
        )
    if args.cmd == "cleanup-system-sentiment":
        return asyncio.run(_cmd_cleanup_system_sentiment(args.integration_id))
    if args.cmd == "mark-system-messages":
        return asyncio.run(_cmd_mark_system_messages(args.integration_id))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
