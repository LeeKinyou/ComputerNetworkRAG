import pytest

from app.services.rag_service import RAGService, validate_question
from app.storage.sqlite_repo import SqliteRepository


def _fake_chunks():
    return [
        {"content": "TCP 三次握手是建立连接的机制，客户端发送 SYN，服务器回应 SYN+ACK。",
         "file_path": "传输层要点.txt", "chunk_id": "d_41869c80-chunk-000"},
        {"content": "三次握手完成后，双方进入 ESTABLISHED 状态，开始传输数据。",
         "file_path": "第6章-应用层.docx", "chunk_id": "d_e6309662-chunk-000"},
    ]


async def _fake_tokens(*deltas):
    async def _gen():
        for d in deltas:
            yield d
    return _gen()


@pytest.fixture
async def repo(tmp_path):
    r = SqliteRepository(tmp_path / "t.db")
    await r.init()
    yield r
    await r.close()


@pytest.fixture
def patch_astream(monkeypatch):
    def _patch(chunks=None, deltas=("TCP", " 三次握手", " 是建立连接的过程。"), error=None):
        async def _astream(question, mode):
            if error is not None:
                raise error
            return (chunks if chunks is not None else _fake_chunks()), await _fake_tokens(*deltas)
        monkeypatch.setattr(
            "app.services.rag_service.lightrag_factory.astream_query", _astream
        )
    return _patch


async def collect(agen):
    return [ev async for ev in agen]


async def test_stream_answer_event_order_and_sources(repo, patch_astream):
    patch_astream()
    svc = RAGService(repo)
    events = await collect(svc.stream_answer("简述 TCP 三次握手的过程", "hybrid", None))

    names = [e.name for e in events]
    assert names[0] == "meta"
    assert names[1] == "sources"
    assert names[-1] == "final"
    assert names[2:-1] == ["token"] * 3

    meta = events[0].data
    assert meta["mode"] == "hybrid"
    assert meta["session_id"].startswith("s_")

    src = events[1].data["items"]
    assert [s["doc_name"] for s in src] == ["传输层要点.txt", "第6章-应用层.docx"]
    for s in src:
        assert set(s) == {"doc_name", "chunk_id", "snippet"}
        assert len(s["snippet"]) <= 121

    final = events[-1].data
    assert final["answer"] == "TCP 三次握手 是建立连接的过程。"

    msgs = await repo.list_messages(meta["session_id"])
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == final["answer"]


async def test_invalid_mode_falls_back_and_annotates(repo, patch_astream):
    patch_astream()
    svc = RAGService(repo)
    events = await collect(svc.stream_answer("什么是子网掩码", "bogus-mode", None))
    meta = events[0].data
    assert meta["mode"] == "hybrid"
    assert meta["mode_requested"] == "bogus-mode"


async def test_existing_session_reused_and_no_new_session(repo, patch_astream):
    patch_astream()
    svc = RAGService(repo)
    sid = await repo.create_session("rag", "已有会话")
    events = await collect(svc.stream_answer("什么是 VLAN", "local", sid))
    assert events[0].data["session_id"] == sid
    assert len(await repo.list_sessions()) == 1


async def test_llm_failure_emits_error_event(repo, patch_astream):
    patch_astream(error=RuntimeError("API key invalid: 401"))
    svc = RAGService(repo)
    events = await collect(svc.stream_answer("简述 ARP 的作用", None, None))
    names = [e.name for e in events]
    assert names[0] == "meta"
    assert names[-1] == "error"
    assert "鉴权" in events[-1].data["message"]
    sid = events[0].data["session_id"]
    msgs = await repo.list_messages(sid)
    assert [m.role for m in msgs] == ["user"]


async def test_question_validation():
    with pytest.raises(ValueError):
        validate_question("ab")
    validate_question("TCP 是什么协议")
    validate_question("arp 作用")
