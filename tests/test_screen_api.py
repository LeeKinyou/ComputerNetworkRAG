"""大屏数据端点（09 号文档 Task 5.2）：GET /api/screen/overview 九字段聚合。

三个必须锁住的点：
1. 字段级容错——LightRAG 挂掉时 SQL 部分照常返回，不整屏降级；
2. 口径一致——entity_types 求和 == stats.entities（现前端聚合受 limit 截断，两边数字对不上）；
3. 工具统计——agent_steps 里 tool_name 落在 action 行、status/耗时落在 observation 行，
   必须按 (run_id, step_no) 自连接，直接 GROUP BY tool_name 会得到全 0 耗时。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import aiosqlite
import httpx
import pytest

from app.rag import lightrag_factory
from app.schemas import DocumentMeta, StepRecord
from app.services import screen_service
from app.storage.sqlite_repo import SqliteRepository, get_repo, init_repo

NINE_FIELDS = {
    "stats", "entity_types", "top_entities", "top_relations",
    "chapters", "tools", "trend", "runs", "feed",
}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


@pytest.fixture
async def repo(db_path):
    r = SqliteRepository(db_path)
    await r.init()
    yield r
    await r.close()


def _node(name: str, etype: str):
    return SimpleNamespace(id=name, properties={"entity_id": name, "entity_type": etype})


def _edge(source: str, target: str, label: str):
    return SimpleNamespace(
        source=source, target=target,
        properties={"keywords": label, "description": ""},
    )


def _patch_snapshot(monkeypatch, nodes, edges):
    async def fake(*_a, **_k):
        return nodes, edges

    monkeypatch.setattr(lightrag_factory, "get_graph_snapshot", fake)


def _patch_snapshot_down(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("LightRAG 未初始化")

    monkeypatch.setattr(lightrag_factory, "get_graph_snapshot", boom)


async def _add_document(repo, doc_id: str, filename: str, chunks: int = 0, status: str = "indexed"):
    await repo.upsert_document(
        DocumentMeta(
            doc_id=doc_id, filename=filename, safe_name=f"{doc_id}.md", ext=".md",
            size_bytes=10, parser="MdParser", raw_path=f"data/uploads/{doc_id}.md",
        )
    )
    if status == "indexed":
        await repo.set_document_status(doc_id, status, chunk_count=chunks)


async def _raw_insert_message(db_path, role: str, content: str, created_at: str):
    """add_message 只能写当前时间；补窗口外/历史数据需直接落库。"""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO messages (msg_id, session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"m_{created_at}_{role}", "s_raw", role, content, created_at),
        )
        await conn.commit()


async def test_overview_returns_exactly_nine_fields(repo, monkeypatch):
    _patch_snapshot(monkeypatch, [_node("IP", "协议")], [])
    data = await screen_service.overview(repo)
    assert set(data) == NINE_FIELDS


async def test_lightrag_down_keeps_sql_fields(repo, monkeypatch):
    """LightRAG 抛 RuntimeError 时只有图相关三字段降级，SQL 部分必须照常返回。"""
    sid = await repo.create_session("rag", "测试会话")
    await repo.add_message(sid, "user", "TCP 三次握手的过程？")
    await _add_document(repo, "d_1", "第4章-网络层.md", chunks=7)
    _patch_snapshot_down(monkeypatch)

    data = await screen_service.overview(repo)

    assert set(data) == NINE_FIELDS
    assert data["entity_types"] == []
    assert data["top_entities"] == []
    assert data["top_relations"] == []
    assert data["stats"]["documents"] == 1
    assert data["stats"]["documents_indexed"] == 1
    assert data["stats"]["chunks"] == 7
    assert data["stats"]["sessions"] == 1
    assert data["stats"]["entities"] == 0
    assert data["trend"][-1]["count"] == 1
    assert data["chapters"] == [{"chapter": 4, "documents": 1, "chunks": 7, "entities": 0}]


async def test_entity_types_sum_equals_stats_entities(repo, monkeypatch):
    """验收口径：类型分布求和 == /api/stats.entities（全量快照，不受 limit 截断）。"""
    nodes = [_node("IP", "协议"), _node("ARP", "协议"), _node("路由器", "设备"), _node("???", "UNKNOWN")]
    _patch_snapshot(monkeypatch, nodes, [_edge("IP", "ARP", "包含")])

    data = await screen_service.overview(repo)

    types = {t["type"]: t["count"] for t in data["entity_types"]}
    assert types == {"协议": 2, "设备": 1, "其他": 1}       # UNKNOWN 归一为“其他”
    assert sum(types.values()) == data["stats"]["entities"] == len(nodes)
    assert [t["count"] for t in data["entity_types"]] == [2, 1, 1]   # 按数量降序


async def test_top_entities_top10_by_degree(repo, monkeypatch):
    nodes = [_node(f"E{i}", "协议") for i in range(12)]
    edges = [_edge("E0", f"E{i}", "包含") for i in range(1, 12)] + [_edge("E1", "E2", "包含")]
    _patch_snapshot(monkeypatch, nodes, edges)

    data = await screen_service.overview(repo)

    assert len(data["top_entities"]) == 10
    assert data["top_entities"][0] == {"name": "E0", "type": "协议", "degree": 11}
    degrees = [e["degree"] for e in data["top_entities"]]
    assert degrees == sorted(degrees, reverse=True)


async def test_top_relations_counts_edge_labels(repo, monkeypatch):
    nodes = [_node("A", "协议"), _node("B", "协议"), _node("C", "协议")]
    edges = [_edge("A", "B", "包含"), _edge("A", "B", "包含"), _edge("B", "C", "调用")]
    _patch_snapshot(monkeypatch, nodes, edges)

    data = await screen_service.overview(repo)

    assert data["top_relations"][0] == {"label": "包含", "count": 2}
    assert data["top_relations"][1] == {"label": "调用", "count": 1}


async def test_tools_joins_action_with_observation(repo, monkeypatch):
    """耗时/成功率只能取自 observation 行；action 行的 elapsed_ms 恒为 0，取错则全图数字是假的。"""
    _patch_snapshot(monkeypatch, [], [])
    sid = await repo.create_session("agent", "测试会话")

    r1 = await repo.create_run(sid, "192.168.10.137/27 属于哪个子网？")
    await repo.append_step(r1, StepRecord(run_id=r1, step_no=1, kind="action",
                                          tool_name="subnet_calculator", elapsed_ms=0))
    await repo.append_step(r1, StepRecord(run_id=r1, step_no=1, kind="observation",
                                          status="success", elapsed_ms=1200))
    await repo.finish_run(r1, "success", "答案", 1)

    r2 = await repo.create_run(sid, "ping 一下")
    await repo.append_step(r2, StepRecord(run_id=r2, step_no=1, kind="action",
                                          tool_name="ping_host", elapsed_ms=0))
    await repo.append_step(r2, StepRecord(run_id=r2, step_no=1, kind="observation",
                                          status="failed", elapsed_ms=3000))
    await repo.finish_run(r2, "failed", None, 1)

    r3 = await repo.create_run(sid, "再算一个子网")
    await repo.append_step(r3, StepRecord(run_id=r3, step_no=1, kind="action",
                                          tool_name="subnet_calculator", elapsed_ms=0))
    await repo.append_step(r3, StepRecord(run_id=r3, step_no=1, kind="observation",
                                          status="success", elapsed_ms=800))

    r4 = await repo.create_run(sid, "查域名")
    await repo.append_step(r4, StepRecord(run_id=r4, step_no=1, kind="action",
                                          tool_name="dns_lookup", elapsed_ms=0))

    data = await screen_service.overview(repo)

    tools = {t["name"]: t for t in data["tools"]}
    assert data["tools"][0]["name"] == "subnet_calculator"       # 按调用次数降序
    assert tools["subnet_calculator"] == {"name": "subnet_calculator", "calls": 2,
                                          "avg_ms": 1000, "ok_rate": 1.0}
    assert tools["ping_host"]["calls"] == 1
    assert tools["ping_host"]["avg_ms"] == 3000
    assert tools["ping_host"]["ok_rate"] == 0.0
    assert tools["dns_lookup"]["avg_ms"] is None      # 无 observation，不知道快慢
    assert tools["dns_lookup"]["ok_rate"] is None


async def test_runs_counts_total_steps_interrupted(repo, monkeypatch):
    _patch_snapshot(monkeypatch, [], [])
    sid = await repo.create_session("agent", "测试会话")

    r1 = await repo.create_run(sid, "q1")
    await repo.append_step(r1, StepRecord(run_id=r1, step_no=1, kind="thought", content="想"))
    await repo.append_step(r1, StepRecord(run_id=r1, step_no=2, kind="action", tool_name="ping_host"))
    await repo.finish_run(r1, "success", "答案", 2)

    r2 = await repo.create_run(sid, "q2")
    await repo.finish_run(r2, "failed", None, 0)

    data = await screen_service.overview(repo)

    assert data["runs"] == {"total": 2, "steps": 2, "interrupted": 1}


async def test_trend_is_fourteen_zero_filled_days(repo, db_path, monkeypatch):
    _patch_snapshot(monkeypatch, [], [])
    sid = await repo.create_session("rag", "测试会话")
    await repo.add_message(sid, "user", "今天的问题")
    await repo.add_message(sid, "assistant", "今天的回答")
    old = (datetime.now() - timedelta(days=20)).isoformat(timespec="seconds")
    await _raw_insert_message(db_path, "user", "上个月的问题", old)

    data = await screen_service.overview(repo)

    trend = data["trend"]
    dates = [t["date"] for t in trend]
    today = datetime.now().date()
    assert len(trend) == 14
    assert dates == [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    assert trend[-1]["count"] == 1          # 只数 user，assistant 不计
    assert trend[0]["count"] == 0           # 无数据日补 0，保证折线连续
    assert sum(t["count"] for t in trend) == 1      # 20 天前的不在窗口内


async def test_chapters_from_filename_regex(repo, monkeypatch):
    _patch_snapshot(monkeypatch, [], [])
    await _add_document(repo, "d_1", "第4章-网络层.md", chunks=1)
    await _add_document(repo, "d_2", "计算机网络第8版课件-第4章-网络层.pptx", chunks=44)
    await _add_document(repo, "d_3", "第 9 章 无线网络和移动网络.pptx", chunks=0, status="failed")
    await _add_document(repo, "d_4", "课程大纲.txt", chunks=3)

    data = await screen_service.overview(repo)

    chapters = {c["chapter"]: c for c in data["chapters"]}
    assert chapters[4] == {"chapter": 4, "documents": 2, "chunks": 45, "entities": 0}
    assert chapters[9]["documents"] == 1
    assert 0 not in chapters                        # 文件名无章号的不入榜
    assert [c["chapter"] for c in data["chapters"]] == [4, 9]


async def test_chapter_entities_from_materialized_table(db_path, repo, monkeypatch):
    """knowledge_node 由 Task 5.5 建表；建了之后 chapters.entities 自动亮起来。"""
    _patch_snapshot(monkeypatch, [], [])
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "CREATE TABLE knowledge_node (kp_id TEXT PRIMARY KEY, name TEXT, chapter INTEGER)"
        )
        await conn.executemany(
            "INSERT INTO knowledge_node (kp_id, name, chapter) VALUES (?, ?, ?)",
            [("kp_1", "IP", 4), ("kp_2", "ARP", 4), ("kp_3", "TCP", 5), ("kp_4", "无章", None)],
        )
        await conn.commit()
    await _add_document(repo, "d_1", "第4章-网络层.md", chunks=1)
    await _add_document(repo, "d_2", "第5章-运输层.md", chunks=2)

    data = await screen_service.overview(repo)

    chapters = {c["chapter"]: c for c in data["chapters"]}
    assert chapters[4]["entities"] == 2
    assert chapters[5]["entities"] == 1


async def test_feed_recent_user_questions_only(repo, monkeypatch):
    _patch_snapshot(monkeypatch, [], [])
    sid = await repo.create_session("rag", "测试会话")
    for i in range(22):
        await repo.add_message(sid, "user", f"问题{i}")
        await repo.add_message(sid, "assistant", f"回答{i}")

    data = await screen_service.overview(repo)

    feed = data["feed"]
    assert len(feed) == 20
    assert set(feed[0]) == {"text", "created_at"}
    assert all(f["text"].startswith("问题") for f in feed)
    assert feed[0]["text"] == "问题21"               # 最新在前（同秒插入靠 rowid 兜底）


async def test_overview_endpoint_over_http(db_path, monkeypatch):
    from main import app

    init_repo(db_path)
    repo = get_repo()
    await repo.init()
    try:
        sid = await repo.create_session("rag", "测试会话")
        await repo.add_message(sid, "user", "虚电路和数据报服务的区别？")
        _patch_snapshot(monkeypatch, [_node("虚电路", "概念")], [])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/screen/overview")
            stats_resp = await client.get("/api/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == NINE_FIELDS
        assert body["stats"] == stats_resp.json()    # 与 /api/stats 同源同口径，防漂移
        assert body["feed"][0]["text"] == "虚电路和数据报服务的区别？"
        assert body["entity_types"] == [{"type": "概念", "count": 1}]
    finally:
        await repo.close()
