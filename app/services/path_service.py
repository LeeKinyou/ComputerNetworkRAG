"""学习路径构建（docs/09 §3.2、§3.3 / Task 5.5）。

章节骨架取自教材章号（文件名正则），LLM 只回答"本章内哪些知识点有先后"，
白名单、跨章方向、成环这三类错误全部由代码硬校验，不依赖 prompt 自觉。
"""

import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Awaitable, Callable

from app.rag import lightrag_factory
from app.schemas import KnowledgeNode, PrereqEdge
from app.services.graph_service import clean_desc, degrees, node_name, node_type

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 40
MAX_DROP_RATE = 0.3
MAX_DESC_CHARS = 120          # 单条描述截断长度：一章 40 个节点也不会把 context 撑爆
DEFAULT_CONFIDENCE = 0.6
CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")

LLMComplete = Callable[[str, str], Awaitable[str]]

_EXTRACT_SYSTEM = "你是计算机网络课程的教研组助手，只输出 JSON，不输出任何解释。"


# ----- 归章 -----


def chapter_of_file_path(file_path) -> int | None:
    match = CHAPTER_RE.search(str(file_path or ""))
    return int(match.group(1)) if match else None


def assign_chapter(file_paths) -> int | None:
    """实体散落在多个分块时按票数归章；平票取更小章号（宏观序更靠前，解释成本最低）。"""
    counts = Counter(
        chapter for chapter in (chapter_of_file_path(p) for p in file_paths or []) if chapter
    )
    if not counts:
        return None
    top = max(counts.values())
    return min(chapter for chapter, votes in counts.items() if votes == top)


def kp_id_for(name: str) -> str:
    """实体名的短哈希。重建索引后名字不变则 ID 不变，触达记录不会失联。"""
    return "kp_" + hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:8]


# ----- 物化 -----


def build_node_rows(
    snapshot: list[dict],
    degrees: dict[str, int],
    chunks: dict[str, dict],
    entity_chunk_ids: dict[str, list[str]],
    built_at: str,
) -> list[KnowledgeNode]:
    """snapshot 项为 {name, type, description}；chunks 为 chunk_id → {file_path, doc_id}。

    归章不信任实体上的 file_path（聚合时会丢），一律用分块元数据反查。
    """
    rows: list[KnowledgeNode] = []
    for item in snapshot:
        name = item["name"]
        chunk_ids = entity_chunk_ids.get(name) or []
        paths = [str((chunks.get(cid) or {}).get("file_path") or "") for cid in chunk_ids]
        chapter = assign_chapter(paths)
        source_chunk = ""
        if chapter is not None:
            for cid, path in zip(chunk_ids, paths):
                if chapter_of_file_path(path) == chapter:
                    source_chunk = cid
                    break
        rows.append(KnowledgeNode(
            kp_id=kp_id_for(name),
            name=name,
            entity_type=item.get("type") or "概念",
            chapter=chapter,
            description=clean_desc(item.get("description")),
            degree=degrees.get(name, 0),
            doc_id=str((chunks.get(source_chunk) or {}).get("doc_id") or ""),
            source_chunk=source_chunk,
            built_at=built_at,
        ))
    return rows


def select_top(nodes, per_chapter: int = DEFAULT_TOP_N) -> list[KnowledgeNode]:
    """每章按（度数降序、名称升序）取前 N：路径只覆盖核心知识点，长尾不进图。"""
    by_chapter: dict[int, list[KnowledgeNode]] = defaultdict(list)
    for n in nodes:
        if n.chapter is not None:
            by_chapter[n.chapter].append(n)
    picked: list[KnowledgeNode] = []
    for chapter in sorted(by_chapter):
        picked.extend(sorted(by_chapter[chapter], key=lambda n: (-n.degree, n.name))[:per_chapter])
    return picked


# ----- LLM 抽边 -----


def _node_lines(nodes) -> str:
    lines = []
    for n in nodes:
        desc = " ".join((n.description or "").split())[:MAX_DESC_CHARS]
        lines.append(f"- {n.name}（{n.entity_type}）：{desc}" if desc else f"- {n.name}（{n.entity_type}）")
    return "\n".join(lines)


def _extract_prompt(nodes) -> str:
    chapter = nodes[0].chapter if nodes else "?"
    return f"""下面是《计算机网络》第 {chapter} 章的 {len(nodes)} 个知识点。
请判断其中哪些存在硬性的前后依赖，即"不先学 A 就学不懂 B"。

只输出 JSON，形如 {{"edges": [{{"source": "A", "target": "B", "reason": "一句话依据", "confidence": 0.9}}]}}。
要求：
1. source 是先学的、target 是后学的，名称必须逐字取自下面的列表，不得发明或改写。
2. 只给真正的强依赖，一般性的"相关""配套"不要给。宁缺毋滥。
3. 不要给出会成环的边（A→B→C→A）。

知识点列表：
{_node_lines(nodes)}"""


async def extract_prereqs(nodes, llm: LLMComplete) -> list[dict]:
    """一章的抽边。失败（额度 403、超时、返回垃圾）一律记警告返回空，不中断其余章节。"""
    if not nodes:
        return []
    try:
        text = await llm(_extract_prompt(nodes), _EXTRACT_SYSTEM)
    except Exception as exc:
        logger.warning("第 %s 章前驱抽取失败，跳过：%s", nodes[0].chapter, exc)
        return []
    return parse_edges(text)


def parse_edges(text) -> list[dict]:
    """从模型回复里抠出边数组：容忍 ```json 围栏、前后散文、顶层数组或 {"edges": [...]}。"""
    raw = str(text or "")
    fenced = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fenced:
        raw = fenced.group(1)
    opens = [i for i in (raw.find("["), raw.find("{")) if i >= 0]
    if not opens:
        return []
    start = min(opens)
    closer = "]" if raw[start] == "[" else "}"
    end = raw.rfind(closer)
    if end <= start:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("edges")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


# ----- 校验与破环 -----


def _confidence(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE
    return max(0.0, min(1.0, score))


def validate_edges(drafts, by_name: dict[str, KnowledgeNode], chapter: int | None = None):
    """丢弃名单外的边、自环、重复对、跨章反向边；返回（保留边, 各类丢弃计数）。

    章内构建时传 chapter：两端都必须落在这一章，否则归入 dropped["chapter"]。
    """
    kept: list[PrereqEdge] = []
    seen: set[tuple[str, str]] = set()
    dropped = {"unknown": 0, "self": 0, "dup": 0, "cross_chapter": 0, "chapter": 0}
    for draft in drafts or []:
        source = by_name.get(str(draft.get("source") or "").strip())
        target = by_name.get(str(draft.get("target") or "").strip())
        if source is None or target is None:
            dropped["unknown"] += 1
            continue
        if source.kp_id == target.kp_id:
            dropped["self"] += 1
            continue
        if (source.kp_id, target.kp_id) in seen:
            dropped["dup"] += 1
            continue
        if source.chapter is None or target.chapter is None:
            dropped["chapter"] += 1
            continue
        if chapter is not None and (source.chapter != chapter or target.chapter != chapter):
            dropped["chapter"] += 1
            continue
        if source.chapter > target.chapter:      # 章号即宏观序，只允许低章指向高章
            dropped["cross_chapter"] += 1
            continue
        seen.add((source.kp_id, target.kp_id))
        kept.append(PrereqEdge(
            source=source.kp_id,
            target=target.kp_id,
            chapter=source.chapter,
            reason=str(draft.get("reason") or "").strip(),
            confidence=_confidence(draft.get("confidence")),
            status="auto",
        ))
    return kept, dropped


def _find_cycle(edges):
    """返回任一环的边列表（DFS 三色标记，自环也算），无环返回 None。"""
    outgoing: dict[str, list[PrereqEdge]] = defaultdict(list)
    for e in edges:
        outgoing[e.source].append(e)
    done: set[str] = set()
    for root in list(outgoing):
        if root in done:
            continue
        path_nodes = [root]
        path_edges: list[PrereqEdge] = []
        on_path = {root}
        stack = [(root, iter(outgoing[root]))]
        while stack:
            node, iterator = stack[-1]
            moved = False
            for e in iterator:
                nxt = e.target
                if nxt in on_path:
                    return path_edges[path_nodes.index(nxt):] + [e]
                if nxt in done:
                    continue
                stack.append((nxt, iter(outgoing[nxt])))
                path_nodes.append(nxt)
                path_edges.append(e)
                on_path.add(nxt)
                moved = True
                break
            if not moved:
                stack.pop()
                done.add(node)
                on_path.discard(node)
                path_nodes.pop()
                if path_edges:
                    path_edges.pop()
    return None


def has_cycle(edges) -> bool:
    return _find_cycle(edges) is not None


def break_cycles(edges):
    """逐环剔除置信度最低的一条边（§3.3：破环必须留日志，不能静默删）。"""
    remaining = list(edges)
    removed: list[PrereqEdge] = []
    while True:
        cycle = _find_cycle(remaining)
        if cycle is None:
            return remaining, removed
        weakest = min(cycle, key=lambda e: (e.confidence, e.source, e.target))
        remaining.remove(weakest)
        removed.append(weakest)
        logger.warning(
            "第 %s 章检出前驱环，剔除最弱边 %s → %s（confidence=%.2f）",
            weakest.chapter, weakest.source, weakest.target, weakest.confidence,
        )


# ----- 一章的完整构建 -----


async def build_chapter(
    repo, chapter: int, llm: LLMComplete, top_n: int = DEFAULT_TOP_N
) -> dict:
    selected = select_top(await repo.list_knowledge_nodes(chapter), top_n)
    report = {
        "chapter": chapter,
        "nodes": len(selected),
        "kept": 0,
        "dropped": {"unknown": 0, "self": 0, "dup": 0, "cross_chapter": 0, "chapter": 0},
        "cross_chapter": 0,
        "drop_rate": 0.0,
        "removed_cycles": 0,
        "passed": True,
    }
    if not selected:
        logger.info("第 %s 章没有可参与路径的知识点，跳过", chapter)
        await repo.replace_prereq_edges(chapter, [])
        return report

    by_name = {n.name: n for n in selected}
    drafts = await extract_prereqs(selected, llm)
    kept, dropped = validate_edges(drafts, by_name, chapter=chapter)
    acyclic, removed = break_cycles(kept)
    await repo.replace_prereq_edges(chapter, acyclic)

    drop_rate = sum(dropped.values()) / len(drafts) if drafts else 0.0
    return {
        **report,
        "kept": len(acyclic),
        "dropped": dropped,
        "cross_chapter": dropped["cross_chapter"],
        "drop_rate": drop_rate,
        "removed_cycles": len(removed),
        "passed": drop_rate <= MAX_DROP_RATE,
    }


# ----- 物化入口（读 LightRAG，不调 LLM） -----


async def materialize(repo, built_at: str | None = None) -> dict:
    """LightRAG 全量快照 → knowledge_node。纯读，零额度，可反复跑。"""
    nodes_raw, edges_raw = await lightrag_factory.get_graph_snapshot()
    snapshot = [
        {
            "name": node_name(n),
            "type": node_type(n.properties or {}),
            "description": (n.properties or {}).get("description"),
        }
        for n in nodes_raw
    ]
    node_degrees = degrees(edges_raw)
    names = [item["name"] for item in snapshot]
    entity_chunk_ids = await lightrag_factory.get_entity_chunk_ids(names)
    chunk_ids = sorted({cid for ids in entity_chunk_ids.values() for cid in ids})
    chunks = await lightrag_factory.get_chunks_meta(chunk_ids)

    rows = build_node_rows(
        snapshot, node_degrees, chunks, entity_chunk_ids, built_at or _now()
    )
    written = await repo.upsert_knowledge_nodes(rows)
    chapters = {r.chapter for r in rows if r.chapter is not None}
    return {
        "nodes": written,
        "in_chapter": sum(1 for r in rows if r.chapter is not None),
        "no_chapter": sum(1 for r in rows if r.chapter is None),
        "chapters": chapters,
    }


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
