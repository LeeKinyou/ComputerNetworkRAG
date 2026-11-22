"""检索层契约：分词、向量、索引刷新与融合排序。

全部在内存库上重建索引，不依赖 runtime 索引与远端 embedding。
"""

from __future__ import annotations

import pytest

from app import embedding
from app.models import Chunk, Document
from app.retrieval import Retriever, VECTOR_DIM, cosine, embed, tokenize
from _support import memory_db


def doc(doc_id: str, *, chapter_id: str = "ch1", title: str = "讲义", status: str = "ready") -> Document:
    return Document(
        id=doc_id,
        course_id="course_cn",
        chapter_id=chapter_id,
        title=title,
        filename=f"{doc_id}.md",
        mime="text/markdown",
        size=10,
        status=status,
        chunk_count=1,
    )


def chunk(chunk_id: str, doc_id: str, text: str, ordinal: int = 0, page: int | None = None) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=doc_id,
        ordinal=ordinal,
        section_path=["4.3 IPv4"],
        page=page,
        text=text,
    )


def test_tokenize_keeps_ipv4_cidr_whole():
    """IP/前缀是课程检索的关键词，分词不应把整串拆成数字碎片。"""
    tokens = tokenize("192.168.10.137/27 的广播地址")
    assert "192.168.10.137/27" in tokens


def test_embed_is_deterministic_and_unit_length():
    first = embed("TCP 三次握手")
    second = embed("TCP 三次握手")
    assert first == second
    assert len(first) == VECTOR_DIM
    assert cosine(first, second) == pytest.approx(1.0, abs=1e-9)
    assert cosine(first, embed("子网掩码")) < 1.0


def test_empty_text_embeds_to_zero_vector():
    vector = embed("")
    assert len(vector) == VECTOR_DIM
    assert sum(abs(value) for value in vector) == 0


async def test_refresh_excludes_documents_not_ready():
    async with memory_db() as factory:
        async with factory() as session:
            session.add_all([doc("d1", title="网络层讲义", status="ready"), doc("d2", title="解析中", status="parsing")])
            session.add_all([chunk("c1", "d1", "IPv4 地址由网络位与主机位组成。"), chunk("c2", "d2", "IPv4 地址由网络位与主机位组成。")])
            await session.commit()

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        assert retriever.ready
        assert [record.chunk_id for record in retriever._records] == ["c1"]
        results = retriever.search("IPv4 地址", top_k=2)
        assert [item["chunk_id"] for item in results] == ["c1"]


async def test_search_fuses_bm25_and_vector_channels():
    async with memory_db() as factory:
        async with factory() as session:
            session.add(doc("d1", title="网络层讲义"))
            session.add(chunk("c1", "d1", "IPv4 地址由网络位与主机位组成，掩码决定边界。", page=3))
            await session.commit()

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        results = retriever.search("IPv4 地址", top_k=1)
        assert results
        item = results[0]
        assert item["chunk_id"] == "c1"
        assert item["title"] == "网络层讲义"
        assert item["channels"] == ["bm25", "vector"]
        assert item["locator"] == {"section_path": ["4.3 IPv4"], "page": 3}
        assert item["excerpt"].startswith("IPv4 地址")


async def test_search_returns_empty_for_blank_query_or_cold_index():
    retriever = Retriever()
    assert retriever.search("TCP") == []

    async with memory_db() as factory:
        async with factory() as session:
            await retriever.refresh(session)
    assert retriever.ready
    assert retriever.search("TCP") == []
    assert retriever.search("   ") == []


async def test_search_can_be_scoped_to_chapter():
    async with memory_db() as factory:
        async with factory() as session:
            session.add_all(
                [
                    doc("d1", chapter_id="ch1", title="链路层"),
                    doc("d2", chapter_id="ch2", title="网络层"),
                ]
            )
            session.add_all(
                [
                    chunk("c1", "d1", "ARP 通过广播请求解析 MAC 地址。"),
                    chunk("c2", "d2", "ARP 通过广播请求解析 MAC 地址。"),
                ]
            )
            await session.commit()

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        all_results = retriever.search("ARP", top_k=5)
        assert {item["chunk_id"] for item in all_results} == {"c1", "c2"}

        scoped = retriever.search("ARP", top_k=5, chapter_id="ch2")
        assert [item["chunk_id"] for item in scoped] == ["c2"]

        assert retriever.search("ARP", chapter_id="ch_missing") == []


async def test_boost_chapters_lifts_weak_chapter_chunk():
    """两段文本完全一致时靠章节加权打破平局，验证画像加权真的生效。"""
    async with memory_db() as factory:
        async with factory() as session:
            session.add_all([doc("d1", chapter_id="ch1"), doc("d2", chapter_id="ch2")])
            session.add_all(
                [
                    chunk("c1", "d1", "拥塞控制通过 cwnd 调节发送速率。"),
                    chunk("c2", "d2", "拥塞控制通过 cwnd 调节发送速率。"),
                ]
            )
            await session.commit()

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        plain = retriever.search("拥塞控制", top_k=1)
        boosted = retriever.search("拥塞控制", top_k=1, boost_chapters={"ch2"})

        assert plain[0]["chunk_id"] == "c1"  # 平局按索引先后
        assert boosted[0]["chunk_id"] == "c2"
        assert boosted[0]["score"] > plain[0]["score"]


async def test_read_source_returns_neighbors_with_bounds():
    async with memory_db() as factory:
        async with factory() as session:
            session.add(doc("d1", title="讲义"))
            session.add_all(
                [
                    chunk(f"c{index}", "d1", f"第 {index} 段内容", ordinal=index)
                    for index in range(3)
                ]
            )
            await session.commit()

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        middle = retriever.read_source("c1", neighbor_count=1)
        assert middle is not None
        assert middle["text"] == "第 1 段内容"
        assert [item["ordinal"] for item in middle["neighbors"]] == [-1, 0, 1]
        assert [item["chunk_id"] for item in middle["neighbors"]] == ["c0", "c1", "c2"]

        first = retriever.read_source("c0", neighbor_count=1)
        assert [item["chunk_id"] for item in first["neighbors"]] == ["c0", "c1"]

        assert retriever.read_source("missing") is None


async def test_remote_embedding_failure_falls_back_to_hash(monkeypatch):
    async with memory_db() as factory:
        async with factory() as session:
            session.add(doc("d1"))
            session.add(chunk("c1", "d1", "IPv4 地址由网络位与主机位组成。"))
            await session.commit()

        monkeypatch.setattr(embedding, "enabled", lambda: True)
        monkeypatch.setattr(embedding, "load_cache", lambda: {})
        monkeypatch.setattr(embedding, "save_cache", lambda cache: None)

        def boom(texts):
            raise RuntimeError("remote down")

        monkeypatch.setattr(embedding, "embed_documents", boom)

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        assert retriever.vector_mode == "hash"
        assert retriever.embedder_label == f"hash/{VECTOR_DIM}d"
        assert len(retriever._records[0].vector) == VECTOR_DIM


async def test_remote_embedding_success_switches_vector_mode(monkeypatch):
    async with memory_db() as factory:
        async with factory() as session:
            session.add(doc("d1"))
            session.add(chunk("c1", "d1", "IPv4 地址由网络位与主机位组成。"))
            await session.commit()

        monkeypatch.setattr(embedding, "enabled", lambda: True)
        monkeypatch.setattr(embedding, "load_cache", lambda: {})
        monkeypatch.setattr(embedding, "save_cache", lambda cache: None)
        monkeypatch.setattr(embedding, "embed_documents", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
        monkeypatch.setattr(embedding, "embed_query", lambda text: [1.0, 0.0, 0.0])
        monkeypatch.setattr(embedding.settings, "embedding_model", "bge-m3")

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        assert retriever.vector_mode == "remote"
        assert retriever.embedder_label == "remote:bge-m3/3d"
        results = retriever.search("IPv4 地址", top_k=1)
        assert results[0]["channels"] == ["bm25", "vector"]


async def test_query_embedding_failure_degrades_to_bm25_only(monkeypatch):
    async with memory_db() as factory:
        async with factory() as session:
            session.add(doc("d1"))
            session.add(chunk("c1", "d1", "IPv4 地址由网络位与主机位组成。"))
            await session.commit()

        monkeypatch.setattr(embedding, "enabled", lambda: True)
        monkeypatch.setattr(embedding, "load_cache", lambda: {})
        monkeypatch.setattr(embedding, "save_cache", lambda cache: None)
        monkeypatch.setattr(embedding, "embed_documents", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])

        def boom(text):
            raise RuntimeError("query down")

        monkeypatch.setattr(embedding, "embed_query", boom)

        retriever = Retriever()
        async with factory() as session:
            await retriever.refresh(session)

        results = retriever.search("IPv4 地址", top_k=1)
        assert results[0]["channels"] == ["bm25"]
        assert retriever._query_warned is True
