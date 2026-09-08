import pytest

from app.schemas import DocumentMeta, StepRecord
from app.storage.sqlite_repo import SqliteRepository


@pytest.fixture
async def repo(tmp_path):
    r = SqliteRepository(tmp_path / "app.db")
    await r.init()
    yield r
    await r.close()


async def test_document_roundtrip(repo):
    meta = DocumentMeta(
        doc_id="d_abc123",
        filename="第4章-网络层.docx",
        safe_name="d_abc123.docx",
        ext=".docx",
        size_bytes=248113,
        parser="DocxParser",
        raw_path="data/uploads/d_abc123.docx",
    )
    await repo.upsert_document(meta)

    items = await repo.list_documents()
    assert len(items) == 1
    assert items[0].status == "pending"
    assert items[0].filename == "第4章-网络层.docx"

    await repo.set_document_status("d_abc123", "indexed", chunk_count=42)
    items = await repo.list_documents()
    assert items[0].status == "indexed"
    assert items[0].chunk_count == 42

    await repo.delete_document("d_abc123")
    assert await repo.list_documents() == []


async def test_session_message_run_steps(repo):
    sid = await repo.create_session("agent", "测试会话")
    await repo.add_message(sid, "user", "192.168.10.137/27 属于哪个子网？")

    rid = await repo.create_run(sid, "192.168.10.137/27 属于哪个子网？")
    await repo.append_step(
        rid, StepRecord(run_id=rid, step_no=1, kind="thought", content="这是子网计算题")
    )
    await repo.append_step(
        rid,
        StepRecord(
            run_id=rid,
            step_no=1,
            kind="action",
            tool_name="subnet_calculator",
            tool_args={"ip_cidr": "192.168.10.137/27"},
        ),
    )
    await repo.append_step(
        rid,
        StepRecord(
            run_id=rid,
            step_no=1,
            kind="observation",
            status="success",
            elapsed_ms=12,
            content="网络地址 192.168.10.128/27",
            structured={"network": "192.168.10.128", "host_count": 30},
        ),
    )
    await repo.finish_run(rid, "success", "网络地址 192.168.10.128/27……", 1)

    steps = await repo.get_run_steps(rid)
    assert [s.kind for s in steps] == ["thought", "action", "observation"]
    assert steps[1].tool_args == {"ip_cidr": "192.168.10.137/27"}
    assert steps[2].structured["host_count"] == 30
    assert steps[2].elapsed_ms == 12

    sessions = await repo.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].session_id == sid
    assert sessions[0].mode == "agent"
    assert sessions[0].last_active_at != ""


async def test_repeated_init_idempotent(tmp_path):
    r = SqliteRepository(tmp_path / "app.db")
    await r.init()
    await r.close()
    r2 = SqliteRepository(tmp_path / "app.db")
    await r2.init()
    await r2.close()
