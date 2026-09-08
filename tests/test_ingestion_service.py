"""入库流水线失败隔离与文本清洗测试（不依赖真实 LLM）。"""

import pytest

from app.rag import lightrag_factory
from app.services.ingestion_service import IngestionService, clean_text
from app.storage.sqlite_repo import SqliteRepository


@pytest.fixture
async def repo(tmp_path):
    repo = SqliteRepository(tmp_path / "test.db")
    await repo.init()
    yield repo
    await repo.close()


@pytest.fixture
def service(repo, tmp_path):
    return IngestionService(repo, tmp_path)


def test_clean_text_strips_noise_and_collapses_blank_lines():
    text = "第一段内容。\r\n- 12 -\r\n\r\n\r\n\r\n第二段内容。\n第 3 页\n12/45\n"
    out = clean_text(text)
    assert "第一段内容。" in out
    assert "第二段内容。" in out
    assert "- 12 -" not in out
    assert "第 3 页" not in out
    assert "12/45" not in out
    assert "\n\n\n" not in out


async def test_save_upload_rejects_unsupported_and_oversize(repo, service):
    with pytest.raises(Exception, match="不支持的文件格式"):
        await service.save_upload("a.pdf", b"%PDF-1.4")
    with pytest.raises(Exception, match="超过限制"):
        await service.save_upload("big.md", b"x" * (21 * 1024 * 1024))


async def test_single_failure_does_not_block_next_document(repo, service, tmp_path, monkeypatch):
    """某篇建库失败（如断 key）时：该篇 failed 且原因可查，后续篇正常 indexed。"""
    for name in ("a.md", "b.md"):
        content = f"# 标题{name}\n\n正文内容 {name}".encode("utf-8")
        await service.save_upload(name, content)
    docs = await repo.list_documents()
    doc_a, doc_b = docs[1], docs[0]  # 列表按创建时间倒序，a 在后

    async def boom(text, doc_id, filename):
        raise RuntimeError("模拟 LLM 服务不可用")

    monkeypatch.setattr(lightrag_factory, "ainsert_text", boom)
    await service.ingest(doc_a.doc_id)

    async def ok(text, doc_id, filename):
        return None

    async def fake_status(doc_id):
        return {"status": "processed", "chunks_count": 3}

    monkeypatch.setattr(lightrag_factory, "ainsert_text", ok)
    monkeypatch.setattr(lightrag_factory, "get_doc_status", fake_status)
    await service.ingest(doc_b.doc_id)

    by_id = {d.doc_id: d for d in await repo.list_documents()}
    assert by_id[doc_a.doc_id].status == "failed"
    assert "模拟 LLM 服务不可用" in by_id[doc_a.doc_id].error
    assert by_id[doc_b.doc_id].status == "indexed"
    assert by_id[doc_b.doc_id].chunk_count == 3
