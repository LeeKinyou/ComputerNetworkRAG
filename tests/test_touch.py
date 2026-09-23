"""知识点触达埋点测试（docs/09 §3.2 / Task 5.4）。

两处埋点：RAGService.stream_answer（via='rag_hit'）与 RAGService.retrieve
（via='agent_tool'，即 course_rag_query 工具）。埋点先于 knowledge_node 建表上线，
故以 kp_name 为准、kp_id 可空，构建脚本 --relink 时按 name 回填。
"""

import logging

import aiosqlite
import pytest

from app.agent.tools import create_registry
from app.services import touch_service
from app.services.rag_service import RAGService
from app.storage.sqlite_repo import SqliteRepository

TOUCH_COLS = {"id", "kp_name", "kp_id", "session_id", "run_id", "via", "created_at"}


async def read_touches(db_path) -> list[dict]:
    """另开连接读库：验证的是真正落盘的内容（而非内存态）。"""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM knowledge_touch ORDER BY id") as cur:
            return [dict(r) for r in await cur.fetchall()]


@pytest.fixture
async def db(tmp_path):
    path = tmp_path / "t.db"
    repo = SqliteRepository(path)
    await repo.init()
    yield repo, path
    await repo.close()


async def seed_knowledge_node(path, *pairs) -> None:
    """往真实 knowledge_node（Task 5.5 建表）塞两条 (kp_id, name)。"""
    async with aiosqlite.connect(path) as conn:
        await conn.executemany(
            "INSERT INTO knowledge_node (kp_id, name, chapter, built_at) VALUES (?, ?, 4, ?)",
            [(kp, name, "2026-09-22T00:00:00") for kp, name in pairs],
        )
        await conn.commit()


def patch_astream(monkeypatch, entities=(), chunks=(), deltas=("TCP",)):
    async def _astream(question, mode):
        async def _gen():
            for d in deltas:
                yield d

        return list(chunks), list(entities), _gen()

    monkeypatch.setattr(
        "app.services.rag_service.lightrag_factory.astream_query", _astream
    )


# ----- 存储层 -----


async def test_schema_contract(db):
    repo, path = db
    async with aiosqlite.connect(path) as conn:
        async with conn.execute("PRAGMA table_info(knowledge_touch)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        async with conn.execute("PRAGMA index_list(knowledge_touch)") as cur:
            idx = {r[1] for r in await cur.fetchall()}
    assert cols == TOUCH_COLS
    assert {"idx_kt_kp", "idx_kt_name"} <= idx


async def test_lookup_kp_ids_skips_names_not_in_snapshot(db):
    repo, _ = db
    assert await repo.lookup_kp_ids(["TCP 三次握手"]) == {}


# ----- 记录逻辑 -----


async def test_record_touches_writes_rows(db):
    repo, path = db
    written = await touch_service.record_touches(
        repo, ["TCP 三次握手", "IP地址"], via="rag_hit", session_id="s_1"
    )
    assert written == 2
    rows = await read_touches(path)
    assert [r["kp_name"] for r in rows] == ["TCP 三次握手", "IP地址"]
    assert {r["via"] for r in rows} == {"rag_hit"}
    assert {r["session_id"] for r in rows} == {"s_1"}
    assert {r["kp_id"] for r in rows} == {None}
    assert all(r["created_at"] for r in rows)


async def test_dedupe_blank_and_cap(db):
    repo, path = db
    assert await touch_service.record_touches(
        repo, ["A", " A ", "A\t", "", "  ", None, "B"], via="rag_hit"
    ) == 2
    assert [r["kp_name"] for r in await read_touches(path)] == ["A", "B"]

    many = [f"实体{i}" for i in range(touch_service.MAX_TOUCH_NAMES + 10)]
    assert await touch_service.record_touches(repo, many, via="rag_hit") == (
        touch_service.MAX_TOUCH_NAMES
    )


async def test_kp_id_resolved_once_node_table_ready(db):
    repo, path = db
    await seed_knowledge_node(path, ("kp_ab12", "TCP 三次握手"))
    await touch_service.record_touches(
        repo, ["TCP 三次握手", "图谱外长尾实体"], via="rag_hit"
    )
    rows = await read_touches(path)
    assert [(r["kp_name"], r["kp_id"]) for r in rows] == [
        ("TCP 三次握手", "kp_ab12"),
        ("图谱外长尾实体", None),
    ]


async def test_unknown_via_ignored(db, caplog):
    repo, path = db
    with caplog.at_level(logging.WARNING):
        written = await touch_service.record_touches(repo, ["TCP"], via="whatever")
    assert written == 0
    assert await read_touches(path) == []
    assert "via" in caplog.text


async def test_write_failure_swallowed(db, caplog, monkeypatch):
    repo, path = db

    async def boom(records):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repo, "add_touches", boom)
    with caplog.at_level(logging.WARNING):
        written = await touch_service.record_touches(repo, ["TCP"], via="rag_hit")
    assert written == 0
    assert "触达埋点写入失败" in caplog.text
    assert await read_touches(path) == []


async def test_entity_names_shapes():
    assert touch_service.entity_names(
        {"entities": [{"entity_name": "TCP"}, {"entity_name": " TCP "}, {}, "裸字符串"]}
    ) == ["TCP", "裸字符串"]
    assert touch_service.entity_names([{"entity_name": "SYN"}, "ACK"]) == ["SYN", "ACK"]
    assert touch_service.entity_names({}) == []
    assert touch_service.entity_names(None) == []


# ----- 两处埋点 -----


async def test_stream_answer_records_rag_hit(db, monkeypatch):
    repo, path = db
    patch_astream(
        monkeypatch,
        entities=[{"entity_name": "TCP 三次握手"}, {"entity_name": "TCP 三次握手"}, {"entity_name": "SYN"}],
    )
    events = [
        ev async for ev in RAGService(repo).stream_answer("简述 TCP 三次握手的过程", "hybrid")
    ]
    session_id = events[0].data["session_id"]
    rows = await read_touches(path)
    assert [r["kp_name"] for r in rows] == ["TCP 三次握手", "SYN"]
    assert {r["via"] for r in rows} == {"rag_hit"}
    assert {r["session_id"] for r in rows} == {session_id}


async def test_retrieve_records_agent_tool(db, monkeypatch):
    repo, path = db

    async def _ctx(query, mode):
        return {"chunks": [], "entities": [{"entity_name": "IP地址"}]}

    monkeypatch.setattr("app.services.rag_service.lightrag_factory.aquery_context", _ctx)
    await RAGService(repo).retrieve("IP 地址分类")
    rows = await read_touches(path)
    assert [(r["kp_name"], r["via"]) for r in rows] == [("IP地址", "agent_tool")]


async def test_course_rag_tool_records_touch(db, monkeypatch):
    repo, path = db

    async def _ctx(query, mode):
        return {
            "chunks": [{"content": "三次握手", "file_path": "第5章-传输层.md", "chunk_id": "c-1"}],
            "entities": [{"entity_name": "三次握手"}, {"entity_name": "SYN"}],
        }

    monkeypatch.setattr("app.services.rag_service.lightrag_factory.aquery_context", _ctx)
    registry = create_registry(rag_service=RAGService(repo))
    result = await registry.run("course_rag_query", {"query": "TCP 三次握手"})
    assert result.status == "success"
    assert [r["kp_name"] for r in await read_touches(path)] == ["三次握手", "SYN"]


async def test_qa_stream_survives_touch_failure(db, monkeypatch):
    repo, path = db
    patch_astream(monkeypatch, entities=[{"entity_name": "TCP"}])

    async def boom(records):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repo, "add_touches", boom)
    events = [
        ev async for ev in RAGService(repo).stream_answer("简述 TCP 三次握手的过程", "hybrid")
    ]
    assert [ev.name for ev in events] == ["meta", "sources", "token", "final"]
    assert await read_touches(path) == []
