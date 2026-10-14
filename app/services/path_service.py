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
LIMIT_CAP = 200                 # /api/path?limit= 的硬上限：防止演示现场手改 URL 拖死浏览器
MAX_DROP_RATE = 0.3
MAX_DESC_CHARS = 120          # 单条描述截断长度：一章 40 个节点也不会把 context 撑爆
DEFAULT_CONFIDENCE = 0.6
CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")


class PrereqExtractionError(RuntimeError):
    """抽边调用失败（额度 403、超时、网络）。上抛而不是吞成空列表：
    空列表会被读成"这一章没有前置关系"，进而把已建好的边覆盖掉。"""


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
    """一章的抽边。调用失败一律上抛 PrereqExtractionError，由 build_chapter 决定不覆盖旧边。"""
    if not nodes:
        return []
    try:
        text = await llm(_extract_prompt(nodes), _EXTRACT_SYSTEM)
    except Exception as exc:
        raise PrereqExtractionError(f"第 {nodes[0].chapter} 章前驱抽取调用失败：{exc}") from exc
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
        "write_skipped": False,
        "error": "",
    }
    if not selected:
        logger.info("第 %s 章没有可参与路径的知识点，跳过", chapter)
        await repo.replace_prereq_edges(chapter, [])
        return report

    by_name = {n.name: n for n in selected}
    try:
        drafts = await extract_prereqs(selected, llm)
    except PrereqExtractionError as exc:
        logger.error("%s——保留第 %s 章已有的 %s 条前驱边", exc, chapter,
                     await repo.count_prereq_edges(chapter))
        return {**report, "passed": False, "write_skipped": True, "error": str(exc)}

    kept, dropped = validate_edges(drafts, by_name, chapter=chapter)
    acyclic, removed = break_cycles(kept)
    drop_rate = sum(dropped.values()) / len(drafts) if drafts else 0.0

    # 空结果集绝不覆盖非空旧数据：403 之后模型回一句"无法回答"和"这一章真的没有前置"
    # 在计数上长得一样，前者会把已经建好的边静默删光。
    if not acyclic:
        existing = await repo.count_prereq_edges(chapter)
        if existing:
            logger.warning("第 %s 章本轮只抽出 0 条边，库中已有 %s 条：不覆盖，判为失败",
                           chapter, existing)
            return {**report, "kept": existing, "dropped": dropped,
                    "cross_chapter": dropped["cross_chapter"],
                    "removed_cycles": len(removed),
                    "drop_rate": drop_rate,
                    "passed": False, "write_skipped": True,
                    "error": f"本轮 0 条边，库中已有 {existing} 条"}

    await repo.replace_prereq_edges(chapter, acyclic)

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


# ----- 路径查询（Task 5.6） -----


async def get_path(repo, chapter: int | None = None, limit: int = DEFAULT_TOP_N) -> dict:
    """章节 DAG。边一律裁到两端都在节点集内——留一条悬空边，ECharts 关系图直接报错。

    节点带 layer：前端画的是手工坐标（x = 层号 × 180），分层只在这里算一份。
    """
    nodes = await repo.list_knowledge_nodes(chapter)
    selected = select_top(nodes, max(1, min(limit, LIMIT_CAP)))
    kept = {n.kp_id for n in selected}
    edges = [
        e for e in await repo.list_prereq_edges() if e.source in kept and e.target in kept
    ]
    layers = _layers(kept, edges)
    counts = await repo.touch_counts_by_kp(sorted(kept))
    return {
        "nodes": [
            {
                "kp_id": n.kp_id, "name": n.name, "type": n.entity_type,
                "chapter": n.chapter, "degree": n.degree, "description": n.description,
                "layer": layers.get(n.kp_id, 0),
                "touch_count": counts.get(n.kp_id, 0),
            }
            for n in selected
        ],
        "edges": [
            {
                "source": e.source, "target": e.target, "chapter": e.chapter,
                "reason": e.reason, "confidence": e.confidence,
            }
            for e in edges
        ],
        "chapters": await repo.list_chapters(),
        "truncated": len(selected) < sum(1 for n in nodes if n.chapter is not None),
    }


async def plan(repo, target: str) -> dict:
    """到 target 的必修链：反向 BFS 取前驱闭包，再按（章号，拓扑层）排序。

    章号作主键是刻意的——LLM 抽错边也只会把同章内部顺序排歪，不会让第 8 章插到第 2 章前面。
    """
    nodes = {n.kp_id: n for n in await repo.list_knowledge_nodes()}
    if target not in nodes:
        raise KeyError(target)

    all_edges = await repo.list_prereq_edges()
    incoming: dict[str, list[PrereqEdge]] = defaultdict(list)
    for e in all_edges:
        if e.source in nodes and e.target in nodes:      # 重建改名后会留下悬空边，跳过而不是 500
            incoming[e.target].append(e)

    closure = {target}
    queue = [target]
    while queue:
        for e in incoming[queue.pop(0)]:
            if e.source not in closure:
                closure.add(e.source)
                queue.append(e.source)

    sub = [e for e in all_edges if e.source in closure and e.target in closure and e.source != e.target]
    layers = _layers(closure, sub)
    strongest: dict[str, PrereqEdge] = {}
    for e in sub:
        if e.target not in strongest or e.confidence > strongest[e.target].confidence:
            strongest[e.target] = e
    counts = await repo.touch_counts_by_kp(sorted(closure))

    def step(n: KnowledgeNode) -> dict:
        return {
            "kp_id": n.kp_id, "name": n.name, "type": n.entity_type,
            "chapter": n.chapter, "degree": n.degree,
            "reason": strongest[n.kp_id].reason if n.kp_id in strongest else "",
            "touch_count": counts.get(n.kp_id, 0),
        }

    steps = sorted(
        (step(nodes[kp_id]) for kp_id in closure),
        key=lambda s: (s["chapter"] or 0, layers[s["kp_id"]], s["name"]),
    )
    goal = step(nodes[target])
    return {
        "target": {k: goal[k] for k in ("kp_id", "name", "type", "chapter", "degree")},
        "steps": steps,
        "no_prereq": len(steps) == 1,
    }


def _layers(names, edges) -> dict[str, int]:
    """最长路径分层：层号 = 到该点的最长链长度。环内节点强行取最小 ID 入队，保证一定收敛。"""
    outgoing: dict[str, list[str]] = defaultdict(list)
    indegree: Counter = Counter()
    for e in edges:
        outgoing[e.source].append(e.target)
        indegree[e.target] += 1
    layer = dict.fromkeys(names, 0)
    remaining = set(names)
    ready = sorted(n for n in names if indegree[n] == 0)
    while remaining:
        batch = ready or [min(remaining)]
        ready = []
        for node in batch:
            if node not in remaining:
                continue
            remaining.discard(node)
            for nxt in outgoing[node]:
                if nxt not in remaining:      # 环里的回边：不能回写已发出节点的层号
                    continue
                layer[nxt] = max(layer[nxt], layer[node] + 1)
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
        ready = sorted(set(ready))
    return layer
