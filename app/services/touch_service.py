"""知识点触达埋点（docs/09 §3.2 / Task 5.4）。

两处调用点：RAGService.stream_answer（via='rag_hit'）与 RAGService.retrieve
（via='agent_tool'，即 course_rag_query 工具）。埋点失败只记 warning，
绝不向上抛——问答主流程优先。
"""

import logging
from collections.abc import Iterable
from typing import Any

from app.schemas import TouchRecord
from app.storage.repository import Repository

logger = logging.getLogger(__name__)

VIA_VALUES = frozenset({"rag_hit", "agent_tool", "path_view"})
MAX_TOUCH_NAMES = 50


def _clean(names: Iterable[str | None]) -> list[str]:
    seen: dict[str, None] = {}
    for raw in names or []:
        name = " ".join(str(raw or "").split())
        if name:
            seen.setdefault(name, None)
    return list(seen)[:MAX_TOUCH_NAMES]


def entity_names(data: Any) -> list[str]:
    """取命中实体名（去空白、去重、封顶）。入参可以是检索结果字典（读 entities 键）
    或实体列表本身，元素兼容 dict（entity_name）与裸字符串两种形态。"""
    items = data.get("entities") if isinstance(data, dict) else data
    return _clean(
        (item.get("entity_name") if isinstance(item, dict) else item) for item in items or []
    )


async def record_touches(
    repo: Repository,
    names: Iterable[str | None],
    via: str,
    session_id: str | None = None,
    run_id: str | None = None,
) -> int:
    """写触达记录（去重、封顶 50 条），返回写入条数；任何异常吞掉并 warning。"""
    if via not in VIA_VALUES:
        logger.warning("触达埋点 via 非法：%r", via)
        return 0
    cleaned = _clean(names)
    if not cleaned:
        return 0
    try:
        kp_ids = await repo.lookup_kp_ids(cleaned)
        records = [
            TouchRecord(
                kp_name=name,
                kp_id=kp_ids.get(name),
                session_id=session_id,
                run_id=run_id,
                via=via,
            )
            for name in cleaned
        ]
        return await repo.add_touches(records)
    except Exception:  # noqa: BLE001 — 埋点绝不打断问答
        logger.warning(
            "触达埋点写入失败（已忽略）：via=%s names=%d", via, len(cleaned), exc_info=True
        )
        return 0
