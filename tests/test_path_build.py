"""学习路径构建测试（docs/09 §3.2 / §3.3 / Task 5.5）。

纯逻辑直接断言；LLM 章内抽取用注入的假函数，真跑留给额度恢复后。
"""

import hashlib
import json
import logging
import random
from collections import deque

import aiosqlite
import pytest

from app.schemas import KnowledgeNode, PrereqEdge
from app.services import path_service
from app.storage.sqlite_repo import SqliteRepository

KN_COLS = {"kp_id", "name", "entity_type", "chapter", "description", "degree",
           "doc_id", "source_chunk", "built_at"}
PE_COLS = {"source", "target", "chapter", "reason", "confidence", "status"}


async def read_touches(db_path) -> dict[str, str | None]:
    """kp_name → kp_id：验证 relink 真正落到磁盘上。"""
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT kp_name, kp_id FROM knowledge_touch") as cur:
            return {r[0]: r[1] for r in await cur.fetchall()}


@pytest.fixture
async def repo(tmp_path):
    r = SqliteRepository(tmp_path / "p.db")
    await r.init()
    yield r
    await r.close()


def node(name, chapter, degree=1, kp=None, **kw) -> KnowledgeNode:
    return KnowledgeNode(
        kp_id=kp or path_service.kp_id_for(name),
        name=name,
        entity_type=kw.pop("entity_type", "概念"),
        chapter=chapter,
        degree=degree,
        built_at=kw.pop("built_at", "2026-09-22T00:00:00"),
        **kw,
    )


def edge(src, dst, confidence=0.6, **kw) -> PrereqEdge:
    return PrereqEdge(
        source=path_service.kp_id_for(src),
        target=path_service.kp_id_for(dst),
        chapter=kw.pop("chapter", 4),
        reason=kw.pop("reason", "依据"),
        confidence=confidence,
        **kw,
    )


# ----- 表结构 -----


async def test_path_tables_contract(repo, tmp_path):
    async with aiosqlite.connect(tmp_path / "p.db") as conn:
        async with conn.execute("PRAGMA table_info(knowledge_node)") as cur:
            kn = {r[1] for r in await cur.fetchall()}
        async with conn.execute("PRAGMA table_info(prereq_edge)") as cur:
            pe = {r[1] for r in await cur.fetchall()}
    assert kn == KN_COLS
    assert pe == PE_COLS


# ----- 归章 -----


def test_chapter_of_file_path():
    assert path_service.chapter_of_file_path("谢希仁第八版课件-第4章-网络层.pptx") == 4
    assert path_service.chapter_of_file_path("第 9 章 万维网.pptx") == 9
    assert path_service.chapter_of_file_path("概览要点.txt") is None


def test_assign_chapter_majority_and_tie():
    assert path_service.assign_chapter(["第4章-网络层.md", "第4章-x.md", "第5章-y.md"]) == 4
    assert path_service.assign_chapter(["第5章-a.md", "第4章-b.md"]) == 4
    assert path_service.assign_chapter(["概览.txt", ""]) is None
    assert path_service.assign_chapter([]) is None


# ----- 物化 -----


def test_kp_id_is_deterministic():
    assert path_service.kp_id_for("TCP 三次握手") == path_service.kp_id_for("TCP 三次握手")
    assert path_service.kp_id_for("TCP 三次握手").startswith("kp_")
    assert len(path_service.kp_id_for("TCP 三次握手")) == 11
    assert path_service.kp_id_for("IP数据报") != path_service.kp_id_for("IP 数据报")


def test_build_node_rows():
    snapshot = [
        {"name": "滑动窗口", "type": "算法", "description": "流量控制机制<SEP>另有退避用法"},
        {"name": "太阳光", "type": "概念", "description": "与课程无关"},
    ]
    degrees = {"滑动窗口": 12, "太阳光": 0}
    chunks = {
        "c-1": {"file_path": "第5章-传输层.md", "doc_id": "d_111"},
        "c-2": {"file_path": "课件-第4章-网络层.pptx", "doc_id": "d_222"},
        "c-3": {"file_path": "课件-第4章-网络层.pptx", "doc_id": "d_222"},
    }
    entity_chunk_ids = {"滑动窗口": ["c-1", "c-2", "c-3"], "太阳光": []}

    rows = path_service.build_node_rows(
        snapshot, degrees, chunks, entity_chunk_ids, built_at="2026-09-22T10:00:00"
    )
    by_name = {r.name: r for r in rows}
    assert by_name["滑动窗口"].chapter == 4          # 多数表决：2 票第 4 章 > 1 票第 5 章
    assert by_name["滑动窗口"].degree == 12
    assert by_name["滑动窗口"].entity_type == "算法"
    assert by_name["滑动窗口"].description == "流量控制机制；另有退避用法"  # <SEP> 归一
    assert by_name["滑动窗口"].source_chunk == "c-2"  # 取归属章内的第一个分块
    assert by_name["滑动窗口"].doc_id == "d_222"
    assert by_name["太阳光"].chapter is None          # 识别不出章节：入库但不进路径
    assert by_name["太阳光"].source_chunk == "" and by_name["太阳光"].doc_id == ""
    assert all(r.built_at == "2026-09-22T10:00:00" for r in rows)


def test_select_top_nodes_by_degree_then_name():
    nodes = [node("a", 4, degree=5), node("b", 4, degree=9), node("c", 4, degree=5),
             node("d", 4, degree=1), node("e", None, degree=99)]
    picked = path_service.select_top(nodes, per_chapter=3)
    assert [n.name for n in picked] == ["b", "a", "c"]  # 度数降序、同度按名；chapter=NULL 不参与


# ----- 边的校验与破环 -----


def by_name_map(*nodes):
    return {n.name: n for n in nodes}


def test_validate_edges_drops_bad_names_self_and_dup():
    nodes = by_name_map(node("IP地址", 4), node("子网掩码", 4))
    drafts = [
        {"source": "IP地址", "target": "子网掩码", "reason": "先会编址才会划分子网", "confidence": 0.9},
        {"source": "IP地址", "target": "不存在的实体", "confidence": 0.9},
        {"source": "子网掩码", "target": "子网掩码", "confidence": 0.9},
        {"source": "IP地址", "target": "子网掩码", "confidence": 0.5},  # 重复对
    ]
    kept, dropped = path_service.validate_edges(drafts, nodes)
    assert len(kept) == 1
    assert kept[0].source == path_service.kp_id_for("IP地址")
    assert kept[0].target == path_service.kp_id_for("子网掩码")
    assert kept[0].confidence == 0.9                    # 重复对保留先出现的那条
    assert kept[0].chapter == 4                         # 边的 chapter 由源节点归属章推导
    assert dropped == {"unknown": 1, "self": 1, "dup": 1, "cross_chapter": 0, "chapter": 0}
    assert kept[0].status == "auto" and kept[0].reason


def test_validate_edges_drops_edges_outside_the_building_chapter():
    nodes = by_name_map(node("物理层", 2), node("滑动窗口", 5))
    kept, dropped = path_service.validate_edges(
        [{"source": "物理层", "target": "滑动窗口", "confidence": 0.7}], nodes, chapter=2
    )
    assert kept == [] and dropped["chapter"] == 1


def test_validate_edges_enforces_chapter_direction():
    nodes = by_name_map(node("物理层", 2), node("滑动窗口", 5))
    drafts = [
        {"source": "物理层", "target": "滑动窗口", "confidence": 0.7},
        {"source": "滑动窗口", "target": "物理层", "confidence": 0.7},
    ]
    kept, dropped = path_service.validate_edges(drafts, nodes)
    assert len(kept) == 1 and kept[0].source == path_service.kp_id_for("物理层")
    assert dropped["cross_chapter"] == 1


def test_confidence_coerced_into_range():
    nodes = by_name_map(node("A", 4), node("B", 4))
    kept, _ = path_service.validate_edges(
        [{"source": "A", "target": "B", "confidence": 42}], nodes
    )
    assert kept[0].confidence == 1.0
    kept, _ = path_service.validate_edges([{"source": "A", "target": "B"}], nodes)
    assert kept[0].confidence == 0.6  # 缺省值


def test_break_cycles_removes_lowest_confidence_edge():
    edges = [
        edge("A", "B", 0.9),
        edge("B", "C", 0.8),
        edge("C", "A", 0.3),   # 环里最弱的一条
        edge("C", "D", 0.7),
    ]
    kept, removed = path_service.break_cycles(edges)
    assert [e.source for e in removed] == [path_service.kp_id_for("C")]
    assert len(kept) == 3
    assert path_service.has_cycle(kept) is False


def test_break_cycles_handles_multiple_cycles():
    edges = [edge("A", "B", 0.9), edge("B", "A", 0.4), edge("C", "D", 0.9),
             edge("D", "E", 0.9), edge("E", "C", 0.2)]
    kept, removed = path_service.break_cycles(edges)
    assert len(removed) == 2
    assert path_service.has_cycle(kept) is False
    assert len(kept) == 3


def test_has_cycle_detects_self_loop():
    e = PrereqEdge(source="x", target="x", chapter=4)
    assert path_service.has_cycle([e]) is True


def _kahn_cyclic(names, edges) -> bool:
    """独立实现的判环 oracle（拓扑排序数得完即无环），用来对拍 DFS。"""
    indegree = {n: 0 for n in names}
    outgoing = {n: [] for n in names}
    for e in edges:
        outgoing[e.source].append(e.target)
        indegree[e.target] += 1
    queue = deque(n for n, d in indegree.items() if d == 0)
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        for nxt in outgoing[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return seen != len(names)


@pytest.mark.parametrize("seed", range(30))
def test_cycle_detection_matches_oracle_and_breaking_always_terminates(seed):
    """破环是"页面不会因环白屏"的唯一防线，随机图对拍锁死（含自环、重边、孤立点）。"""
    rng = random.Random(seed)
    names = [f"kp_{i}" for i in range(rng.randint(1, 14))]
    edges = [
        PrereqEdge(
            source=rng.choice(names), target=rng.choice(names), chapter=4,
            confidence=round(rng.random(), 2),
        )
        for _ in range(rng.randint(0, len(names) * len(names)))
    ]
    assert path_service.has_cycle(edges) == _kahn_cyclic(names, edges)

    kept, removed = path_service.break_cycles(edges)
    assert path_service.has_cycle(kept) is False
    assert len(kept) + len(removed) == len(edges)


# ----- LLM 步骤 -----


def test_parse_edges_tolerates_fence_and_prose():
    text = '好的，结果如下：\n```json\n{"edges":[{"source":"A","target":"B","reason":"r","confidence":0.8}]}\n```'
    drafts = path_service.parse_edges(text)
    assert drafts == [{"source": "A", "target": "B", "reason": "r", "confidence": 0.8}]


def test_parse_edges_accepts_bare_list():
    drafts = path_service.parse_edges('[{"source":"A","target":"B"}]')
    assert drafts == [{"source": "A", "target": "B"}]


def test_parse_edges_returns_empty_on_garbage():
    assert path_service.parse_edges("对不起，我无法回答") == []
    assert path_service.parse_edges("") == []
    assert path_service.parse_edges('{"edges": "not-a-list"}') == []


async def test_extract_prereqs_prompt_carries_names_and_truncated_desc():
    nodes = [node("滑动窗口", 4, degree=12, description="流量控制" + "很" * 200),
             node("拥塞控制", 4, degree=8, description="阻塞处理")]

    async def fake_llm(prompt, system=""):
        assert "滑动窗口" in prompt and "拥塞控制" in prompt
        assert "流量控制" in prompt
        assert len(prompt) < 6000                      # 描述必须截断，否则一章就爆 context
        return json.dumps({"edges": [{"source": "滑动窗口", "target": "拥塞控制",
                                      "reason": "先学窗口才谈拥塞", "confidence": 0.8}]},
                          ensure_ascii=False)

    drafts = await path_service.extract_prereqs(nodes, fake_llm)
    assert drafts[0]["source"] == "滑动窗口"


async def test_extract_prereqs_llm_failure_raises():
    """失败必须上抛：吞成空列表会让"额度 403"看起来像"这一章没有前置关系"。"""
    async def boom(prompt, system=""):
        raise RuntimeError("HTTP 403")

    with pytest.raises(path_service.PrereqExtractionError):
        await path_service.extract_prereqs([node("A", 4)], boom)


# ----- 落库 -----


async def test_save_nodes_and_edges_roundtrip(repo):
    rows = [node("IP地址", 4, degree=46, description="编址"), node("子网掩码", 4, degree=20)]
    assert await repo.upsert_knowledge_nodes(rows) == 2
    assert {n.name for n in await repo.list_knowledge_nodes(4)} == {"IP地址", "子网掩码"}

    edges = [edge("IP地址", "子网掩码", 0.9, reason="先学编址")]
    assert await repo.replace_prereq_edges(4, edges) == 1
    saved = await repo.list_prereq_edges(4)
    assert saved[0].reason == "先学编址" and saved[0].status == "auto"
    assert saved[0].source == path_service.kp_id_for("IP地址")


async def test_replace_prereq_edges_is_idempotent(repo):
    await repo.upsert_knowledge_nodes([node("A", 4), node("B", 4)])
    for _ in range(2):
        await repo.replace_prereq_edges(4, [edge("A", "B")])
    assert len(await repo.list_prereq_edges(4)) == 1


async def test_replace_prereq_edges_skips_key_owned_by_other_chapter(repo):
    """主键是 (source,target)：边被人工挪到别的章后重跑本章不能整批崩掉。"""
    await repo.replace_prereq_edges(5, [edge("A", "B", chapter=5)])
    assert await repo.replace_prereq_edges(4, [edge("A", "B")]) == 0
    saved = await repo.list_prereq_edges()
    assert len(saved) == 1 and saved[0].chapter == 5       # 别章的边保持原样


async def test_replace_prereq_edges_rolls_back_on_bad_row(repo):
    """删+插必须同事务：批次中途报错不能留下"旧边已删、新边半截"的空章。"""
    await repo.replace_prereq_edges(4, [edge("A", "B", reason="已建")])

    with pytest.raises(Exception):
        await repo.replace_prereq_edges(4, [edge("C", "D"), edge("C", "D")])  # 批内撞主键

    saved = await repo.list_prereq_edges(4)
    assert [e.source for e in saved] == [path_service.kp_id_for("A")]


async def test_count_prereq_edges_is_per_chapter(repo):
    assert await repo.count_prereq_edges(4) == 0
    await repo.replace_prereq_edges(4, [edge("A", "B")])
    await repo.replace_prereq_edges(5, [edge("C", "D", chapter=5)])
    assert await repo.count_prereq_edges(4) == 1
    assert await repo.count_prereq_edges(6) == 0


async def test_upsert_nodes_keeps_stable_kp_id(repo):
    await repo.upsert_knowledge_nodes([node("A", 4, degree=1)])
    await repo.upsert_knowledge_nodes([node("A", 4, degree=7)])
    rows = await repo.list_knowledge_nodes(4)
    assert len(rows) == 1 and rows[0].degree == 7
    assert rows[0].kp_id == path_service.kp_id_for("A")


async def test_relink_touch_backfills_kp_id(repo, tmp_path):
    from app.schemas import TouchRecord

    await repo.upsert_knowledge_nodes([node("IP地址", 4)])
    await repo.add_touches([
        TouchRecord(kp_name="IP地址", via="rag_hit"),
        TouchRecord(kp_name="已改名的实体", via="rag_hit"),
    ])
    assert await repo.relink_touch_kp_ids() == 1
    by_name = await read_touches(tmp_path / "p.db")
    assert by_name["IP地址"] == path_service.kp_id_for("IP地址")
    assert by_name["已改名的实体"] is None


async def test_relink_does_not_clobber_existing_kp_id(repo, tmp_path):
    from app.schemas import TouchRecord

    await repo.upsert_knowledge_nodes([node("IP地址", 4)])
    await repo.add_touches([TouchRecord(kp_name="IP地址", kp_id="kp_old", via="rag_hit")])
    await repo.relink_touch_kp_ids()
    assert list((await read_touches(tmp_path / "p.db")).values()) == ["kp_old"]


# ----- 一章的完整构建 -----


async def test_build_chapter_reports_counts_and_is_acyclic(repo):
    await repo.upsert_knowledge_nodes([node("A", 4, degree=9), node("B", 4, degree=5),
                                        node("C", 4, degree=3)])

    async def fake_llm(prompt, system=""):
        return json.dumps({"edges": [
            {"source": "A", "target": "B", "reason": "r1", "confidence": 0.9},
            {"source": "B", "target": "C", "reason": "r2", "confidence": 0.8},
            {"source": "C", "target": "A", "reason": "r3", "confidence": 0.2},  # 成环
            {"source": "A", "target": "幽灵", "reason": "r4", "confidence": 0.9},  # 白名单外
        ]}, ensure_ascii=False)

    report = await path_service.build_chapter(repo, 4, fake_llm)
    assert report["nodes"] == 3
    assert report["kept"] == 2 and report["removed_cycles"] == 1
    assert report["dropped"]["unknown"] == 1
    assert report["cross_chapter"] == 0
    assert report["drop_rate"] == pytest.approx(1 / 4)
    assert report["passed"] is True                     # 丢弃率 25% < 30%
    edges = await repo.list_prereq_edges(4)
    assert path_service.has_cycle(edges) is False
    assert all(e.chapter == 4 for e in edges)


async def test_build_chapter_flags_high_drop_rate(repo):
    await repo.upsert_knowledge_nodes([node("A", 4), node("B", 4)])

    async def noisy_llm(prompt, system=""):
        return json.dumps({"edges": [{"source": "A", "target": "B", "confidence": 0.9}] +
                           [{"source": "X%d" % i, "target": "Y%d" % i, "confidence": 0.9}
                            for i in range(5)]}, ensure_ascii=False)

    report = await path_service.build_chapter(repo, 4, noisy_llm)
    assert report["passed"] is False and report["drop_rate"] > 0.3


async def test_build_chapter_without_nodes_is_noop(repo):
    async def never(prompt, system=""):
        raise AssertionError("不该调 LLM")

    report = await path_service.build_chapter(repo, 7, never)
    assert report["nodes"] == 0 and report["kept"] == 0 and report["passed"] is True


async def test_build_chapter_llm_failure_preserves_edges(repo):
    """百炼免费额度 403 时：原实现吞异常→空边集→按章 DELETE 把已建好的边清空，还打 [OK] 退 0。"""
    await repo.upsert_knowledge_nodes([node("A", 4), node("B", 4)])
    await repo.replace_prereq_edges(4, [edge("A", "B", reason="已建")])

    async def boom(prompt, system=""):
        raise RuntimeError("HTTP 403：免费额度已耗尽")

    report = await path_service.build_chapter(repo, 4, boom)
    assert report["passed"] is False and report["write_skipped"] is True
    saved = await repo.list_prereq_edges(4)
    assert len(saved) == 1 and saved[0].reason == "已建"


async def test_build_chapter_unusable_output_preserves_edges(repo):
    """调用成功但一个字都没抽出来，同样不能当成"这一章没有前置关系"覆盖掉旧数据。"""
    await repo.upsert_knowledge_nodes([node("A", 4), node("B", 4)])
    await repo.replace_prereq_edges(4, [edge("A", "B", reason="已建")])

    async def junk(prompt, system=""):
        return "抱歉，我无法回答这个问题。"

    report = await path_service.build_chapter(repo, 4, junk)
    assert report["passed"] is False and report["write_skipped"] is True
    assert len(await repo.list_prereq_edges(4)) == 1


async def test_build_chapter_success_marks_write_not_skipped(repo):
    await repo.upsert_knowledge_nodes([node("A", 4), node("B", 4)])

    async def ok(prompt, system=""):
        return json.dumps({"edges": [{"source": "A", "target": "B", "confidence": 0.9}]})

    report = await path_service.build_chapter(repo, 4, ok)
    assert report["write_skipped"] is False and report["passed"] is True


# ----- CLI -----


def test_parse_args():
    from scripts.build_learning_path import parse_args

    assert parse_args(["--all"]).all is True and parse_args(["--all"]).nodes_only is False
    args = parse_args(["--chapter", "4", "--nodes-only"])
    assert args.chapters == [4] and args.nodes_only is True
    assert parse_args(["--chapter", "4"]).top_n == path_service.DEFAULT_TOP_N
    assert parse_args(["--chapter", "4", "--chapter", "6"]).chapters == [4, 6]
