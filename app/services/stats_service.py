"""六项核心计数：/api/stats 与大屏 stats 字段共用一份实现，避免两处口径漂移。"""

import logging

from app.rag import lightrag_factory
from app.storage.repository import Repository

logger = logging.getLogger(__name__)


async def core_stats(repo: Repository) -> dict:
    docs = await repo.list_documents()
    sessions = await repo.list_sessions()
    entities = relations = 0
    try:
        nodes, edges = await lightrag_factory.get_graph_snapshot()
        entities, relations = len(nodes), len(edges)
    except Exception:  # noqa: BLE001 — 知识库未初始化不该让统计端点 500
        logger.warning("统计图谱数据失败（知识库可能未初始化）", exc_info=True)
    return {
        "documents": len(docs),
        "documents_indexed": sum(1 for d in docs if d.status == "indexed"),
        "chunks": sum(d.chunk_count for d in docs),
        "entities": entities,
        "relations": relations,
        "sessions": len(sessions),
    }
