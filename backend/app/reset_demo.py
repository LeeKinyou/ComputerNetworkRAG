"""演示前重置：清空会话与运行记录，保留课程种子与预置文档。

用法（在 backend 目录，先停掉正在运行的服务）：

    uv run python -m app.reset_demo              # 只清任务、消息、运行记录
    uv run python -m app.reset_demo --documents  # 同时清掉后台上传的文档

检查点文件不在这里处理；如需一并清空，删除 runtime/checkpoints.db 后重启服务即可。
"""

import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.db import SessionFactory, shutdown_db
from app.models import ChatSession, Chunk, Document, Message, Run, RunStep


async def reset(with_documents: bool) -> None:
    async with SessionFactory() as session:
        runs = await session.scalar(select(func.count()).select_from(Run)) or 0
        sessions = await session.scalar(select(func.count()).select_from(ChatSession)) or 0
        messages = await session.scalar(select(func.count()).select_from(Message)) or 0
        steps = await session.scalar(select(func.count()).select_from(RunStep)) or 0

        await session.execute(delete(RunStep))
        await session.execute(delete(Run))
        await session.execute(delete(Message))
        await session.execute(delete(ChatSession))

        removed_docs = 0
        if with_documents:
            doc_ids = [
                doc.id
                for doc in (await session.execute(select(Document))).scalars().all()
                if not doc.id.startswith("doc_seed")
            ]
            if doc_ids:
                await session.execute(delete(Chunk).where(Chunk.document_id.in_(doc_ids)))
                await session.execute(delete(Document).where(Document.id.in_(doc_ids)))
            removed_docs = len(doc_ids)

        await session.commit()

    print(f"已清空：{runs} 条运行、{sessions} 个会话、{messages} 条消息、{steps} 个步骤。")
    if with_documents:
        print(f"已移除 {removed_docs} 份后台上传文档（预置文档保留）。")
    else:
        print("后台上传文档保留；需要一并清除时加 --documents。")


def main() -> None:
    parser = argparse.ArgumentParser(description="清空演示运行数据")
    parser.add_argument("--documents", action="store_true", help="同时移除后台上传的文档")
    args = parser.parse_args()

    async def runner() -> None:
        try:
            await reset(args.documents)
        finally:
            await shutdown_db()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
