"""一次性数据迁移：清理已删除文档遗留的分块。

SQLite 默认不开启外键约束，历史上删除 documents 后 chunks 可能残留。
脚本默认只统计，加 `--apply` 才真正删除；可重复执行。

用法：
    .\\.venv\\Scripts\\python.exe -m app.cleanup_orphans
    .\\.venv\\Scripts\\python.exe -m app.cleanup_orphans --apply
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionFactory
from app.models import Chunk, Document


def _orphan_condition():
    return ~Chunk.document_id.in_(select(Document.id))


async def find_orphan_chunk_ids(session: AsyncSession) -> list[str]:
    rows = await session.execute(
        select(Chunk.id).where(_orphan_condition()).order_by(Chunk.id)
    )
    return list(rows.scalars().all())


async def delete_orphan_chunks(session: AsyncSession) -> int:
    result = await session.execute(delete(Chunk).where(_orphan_condition()))
    return int(result.rowcount or 0)


async def main(apply: bool) -> int:
    settings.ensure_runtime()
    async with SessionFactory() as session:
        try:
            ids = await find_orphan_chunk_ids(session)
        except OperationalError as exc:
            print(f"数据库尚未初始化，跳过迁移：{exc.orig}")
            return 0
        print(f"orphan_chunks = {len(ids)}")
        if ids:
            print("sample:", ", ".join(ids[:5]))
        if not ids or not apply:
            if ids:
                print("dry-run：加 --apply 才会删除")
            return 0
        deleted = await delete_orphan_chunks(session)
        await session.commit()
        print(f"deleted = {deleted}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理已删除文档遗留的分块")
    parser.add_argument("--apply", action="store_true", help="真正删除；缺省只统计")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.apply)))
