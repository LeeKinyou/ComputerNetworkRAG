import logging
import re

from app.rag import lightrag_factory

logger = logging.getLogger(__name__)

_NODE_LIMIT_CAP = 2000


def _clean_desc(text) -> str:
    """LightRAG 会用内部 <SEP> 拼接多段描述，展示时换成中文分号。"""
    return re.sub(r"\s*<SEP>\s*", "；", str(text or ""))


def _node_name(node) -> str:
    props = node.properties or {}
    return props.get("entity_id") or node.id


def _node_type(props: dict) -> str:
    t = props.get("entity_type") or "概念"
    return "其他" if t.upper() == "UNKNOWN" else t


def _sources(props: dict) -> list[dict]:
    """file_path 与 source_id（chunk 列表）按顺序配对为来源列表；实体聚合可能丢失部分 file_path，由 _resolve_sources 反查补全。"""
    files = [f for f in str(props.get("file_path") or "").split("<SEP>") if f]
    chunks = [c for c in str(props.get("source_id") or "").split("<SEP>") if c]
    return [
        {"doc_name": files[i] if i < len(files) else "",
         "chunk_id": chunks[i] if i < len(chunks) else ""}
        for i in range(max(len(files), len(chunks)))
    ]


async def _resolve_sources(sources: list[dict]) -> list[dict]:
    """实体聚合可能只保留一个 file_path，缺失项用分块 kv 里的 file_path 反查补全。"""
    out = []
    for s in sources:
        if not s["doc_name"] and s["chunk_id"]:
            chunk = await lightrag_factory.get_chunk(s["chunk_id"])
            file_path = str((chunk or {}).get("file_path") or "").split("<SEP>")[0]
            if file_path:
                s = {**s, "doc_name": file_path}
        out.append(s)
    return out


def _type_of_edge(edge) -> tuple[str, str]:
    props = edge.properties or {}
    return props.get("keywords") or "关联", props.get("description") or ""


async def get_graph(keyword: str = "", entity_type: str = "", limit: int = 500) -> dict:
    limit = max(1, min(limit, _NODE_LIMIT_CAP))
    nodes_raw, edges_raw = await lightrag_factory.get_graph_snapshot()

    types = sorted({_node_type(n.properties or {}) for n in nodes_raw})

    kw = keyword.strip().lower()
    wanted_types = {t.strip() for t in entity_type.split(",") if t.strip()} if entity_type else None

    def keep(props: dict) -> bool:
        if wanted_types is not None and _node_type(props) not in wanted_types:
            return False
        if kw:
            name = str(props.get("entity_id") or "").lower()
            desc = str(props.get("description") or "").lower()
            if kw not in name and kw not in desc:
                return False
        return True

    selected = [n for n in nodes_raw if keep(n.properties or {})]
    truncated = len(selected) > limit
    selected = selected[:limit]

    degree: dict[str, int] = {}
    for e in edges_raw:
        degree[e.source] = degree.get(e.source, 0) + 1
        degree[e.target] = degree.get(e.target, 0) + 1

    nodes = []
    ids: set[str] = set()
    for n in selected:
        props = n.properties or {}
        name = _node_name(n)
        ids.add(name)
        nodes.append({
            "id": name,
            "name": name,
            "type": _node_type(props),
            "description": _clean_desc(props.get("description")),
            "sources": _sources(props),
            "degree": degree.get(name, 0),
        })

    edges = []
    for e in edges_raw:
        if e.source in ids and e.target in ids:
            label, desc = _type_of_edge(e)
            edges.append({
                "source": e.source,
                "target": e.target,
                "label": label,
                "description": _clean_desc(desc),
            })

    return {"nodes": nodes, "edges": edges, "types": types, "truncated": truncated}


async def get_entity_detail(name: str) -> dict:
    nodes_raw, edges_raw, _ = await lightrag_factory.get_entity_subgraph(name, max_depth=1)

    if not any(_node_name(n) == name for n in nodes_raw):
        raise KeyError(name)

    props = next((n.properties or {} for n in nodes_raw if _node_name(n) == name), {})

    neighbors = []
    seen: set[str] = {name}
    for e in edges_raw:
        other = e.target if e.source == name else (e.source if e.target == name else None)
        if other is None or other in seen:
            continue
        label, desc = _type_of_edge(e)
        other_props = next((n.properties or {} for n in nodes_raw if _node_name(n) == other), {})
        neighbors.append({
            "name": other,
            "relation": label,
            "description": _clean_desc(desc) or _clean_desc(other_props.get("description"))[:80],
        })

    sub_nodes = [
        {"id": _node_name(n), "name": _node_name(n), "type": _node_type(n.properties or {}),
         "description": _clean_desc((n.properties or {}).get("description")), "sources": [], "degree": 0}
        for n in nodes_raw
    ]
    sub_ids = {n["id"] for n in sub_nodes}
    sub_edges = []
    for e in edges_raw:
        if e.source in sub_ids and e.target in sub_ids:
            label, desc = _type_of_edge(e)
            sub_edges.append({"source": e.source, "target": e.target, "label": label,
                              "description": _clean_desc(desc)})

    return {
        "entity": {
            "name": name,
            "type": _node_type(props),
            "description": _clean_desc(props.get("description")),
            "sources": await _resolve_sources(_sources(props)),
        },
        "neighbors": neighbors,
        "subgraph": {"nodes": sub_nodes, "edges": sub_edges},
    }
