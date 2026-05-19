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

from app.db.models import ImportJob, Integration
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixClient
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="ai-message admin CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser(
        "import-bitrix24",
        help="Импорт исторических диалогов Open Channels из Bitrix24",
    )
    imp.add_argument("--integration-id", required=True)
    imp.add_argument("--days", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "import-bitrix24":
        return asyncio.run(
            _cmd_import_bitrix24(args.integration_id, args.days)
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
