"""大屏一次性聚合数据（09 §2.4 / Task 5.7）：十个字段，**每个字段各自容错**。

LightRAG 挂掉或单条 SQL 出错只降级该字段（图域三字段为空数组、数字为 0），
SQL 部分照常返回；大屏对空数组渲染“暂无数据”占位，不整屏降级。
"""

import logging
import re
from datetime import datetime, timedelta

from app.services import graph_service
from app.services.stats_service import core_stats
from app.storage.repository import Repository

logger = logging.getLogger(__name__)

TREND_DAYS = 14
FEED_LIMIT = 20

_CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
_EMPTY_STATS = {"documents": 0, "documents_indexed": 0, "chunks": 0,
                "entities": 0, "relations": 0, "sessions": 0}
_EMPTY_RUNS = {"total": 0, "steps": 0, "interrupted": 0}
_EMPTY_COVERAGE = {"touched": 0, "total": 0, "rate": 0.0}


async def _safe(field: str, factory, fallback):
    try:
        return await factory()
    except Exception:  # noqa: BLE001 — 单字段失败不拖垮整屏
        logger.warning("大屏字段 %s 取数失败，已降级", field, exc_info=True)
        return fallback


def _trend_series(counts: dict[str, int], days: int = TREND_DAYS) -> list[dict]:
    """补零成连续 N 天，前端折线才不会因为缺日期而断点。"""
    today = datetime.now().date()
    series = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        series.append({"date": day, "count": int(counts.get(day, 0))})
    return series


async def _tools(repo: Repository) -> list[dict]:
    tools = []
    for row in await repo.screen_tool_stats():
        calls = int(row["calls"])
        observed = calls - int(row["unobserved"] or 0)
        avg_ms = row["avg_ms"]
        tools.append({
            "name": row["name"],
            "calls": calls,
            "avg_ms": None if avg_ms is None else int(round(avg_ms)),
            "ok_rate": None if observed <= 0 else round(int(row["ok_count"] or 0) / observed, 3),
        })
    return tools


async def _trend(repo: Repository) -> list[dict]:
    since = (datetime.now().date() - timedelta(days=TREND_DAYS - 1)).isoformat()
    return _trend_series(await repo.screen_message_trend(since))


async def _chapters(repo: Repository) -> list[dict]:
    entity_counts = await repo.screen_chapter_entities()
    merged: dict[int, dict] = {}
    for doc in await repo.list_documents():
        match = _CHAPTER_RE.search(doc.filename or "")
        if not match:
            continue
        chapter = int(match.group(1))
        item = merged.setdefault(chapter, {"chapter": chapter, "documents": 0, "chunks": 0})
        item["documents"] += 1
        item["chunks"] += int(doc.chunk_count or 0)
    return [
        {**item, "entities": int(entity_counts.get(item["chapter"], 0))}
        for item in sorted(merged.values(), key=lambda x: x["chapter"])
    ]


async def _feed(repo: Repository) -> list[dict]:
    return [
        {"text": row["content"], "created_at": row["created_at"]}
        for row in await repo.screen_feed(FEED_LIMIT)
    ]


async def overview(repo: Repository) -> dict:
    stats = await _safe("stats", lambda: core_stats(repo), dict(_EMPTY_STATS))
    graph_agg = await _safe("graph", graph_service.get_screen_aggregates,
                            {"entity_types": [], "top_entities": [], "top_relations": []})

    return {
        "stats": stats,
        "entity_types": graph_agg.get("entity_types") or [],
        "top_entities": graph_agg.get("top_entities") or [],
        "top_relations": graph_agg.get("top_relations") or [],
        "chapters": await _safe("chapters", lambda: _chapters(repo), []),
        "tools": await _safe("tools", lambda: _tools(repo), []),
        "trend": await _safe("trend", lambda: _trend(repo), _trend_series({})),
        "runs": await _safe("runs", lambda: repo.screen_run_stats(), dict(_EMPTY_RUNS)),
        "feed": await _safe("feed", lambda: _feed(repo), []),
        "coverage": await _safe("coverage", lambda: repo.touch_coverage(), dict(_EMPTY_COVERAGE)),
    }
