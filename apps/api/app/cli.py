"""
CLI для административных операций. Запуск:

    python -m app.cli import-bitrix24 --integration-id <id> [--days 30]

Без внешних зависимостей — только stdlib argparse, чтобы не раздувать requirements.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

import json

from app.db.models import ImportJob, Integration
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.crm import extract_crm_refs_from_session
from app.integrations.bitrix24.importer import run_import_job


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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
