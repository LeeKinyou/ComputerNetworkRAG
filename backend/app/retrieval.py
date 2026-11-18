"""进程内检索：BM25 + 轻量哈希向量 + RRF 融合。

lite 档不引入向量库；chunk 数量在演示规模内（数百条），启动时一次性装载，
上传后调用 refresh() 重建。接口保持 search() 一个入口，后续可替换为远端 embedding。
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document

VECTOR_DIM = 256
TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./:_-]*")

# 课程术语，避免被 jieba 切碎
_COURSE_TERMS = (
    "CIDR 子网划分 广播地址 网络地址 子网掩码 最长前缀匹配 路由聚合 "
    "拥塞控制 三次握手 慢启动 CSMA/CD CSMA/CA IPv4 IPv6 TCP UDP HTTP HTTPS TLS DNS ARP ICMP NAT OSI"
)
for _term in _COURSE_TERMS.split():
    jieba.add_word(_term)


def tokenize(text: str) -> list[str]:
    """中文用 jieba，英文/编号保持整体（如 192.168.10.137/27、TCP）。"""
    tokens: list[str] = []
    for raw in jieba.lcut(text.lower()):
        term = raw.strip()
        if not term:
            continue
        tokens.append(term)
        for extra in TERM_RE.findall(term):
            if extra != term:
                tokens.append(extra)
    return tokens


def embed(text: str) -> list[float]:
    """确定性哈希向量：无需外部 embedding 服务也能跑通向量通道。"""
    vec = [0.0] * VECTOR_DIM
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % VECTOR_DIM
        sign = 1.0 if digest[0] % 2 == 0 else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    document_title: str
    section_path: list[str]
    page: int | None
    text: str
    chapter_id: str | None
    tokens: list[str] = field(default_factory=list)
    vector: list[float] = field(default_factory=list)


class Retriever:
    def __init__(self) -> None:
        self._records: list[ChunkRecord] = []
        self._bm25: BM25Okapi | None = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def refresh(self, session: AsyncSession) -> None:
        rows = (
            await session.execute(
                select(Chunk, Document).join(Document, Chunk.document_id == Document.id).where(
                    Document.status == "ready"
                )
            )
        ).all()
        records: list[ChunkRecord] = []
        for chunk, document in rows:
            text = chunk.text or ""
            records.append(
                ChunkRecord(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    section_path=list(chunk.section_path or []),
                    page=chunk.page,
                    text=text,
                    chapter_id=document.chapter_id,
                    tokens=tokenize(text),
                    vector=embed(text),
                )
            )
        self._records = records
        self._bm25 = BM25Okapi([r.tokens for r in records]) if records else None
        self._ready = True

    def search(
        self,
        query: str,
        top_k: int = 5,
        chapter_id: str | None = None,
        pool: int = 20,
    ) -> list[dict]:
        if not self._ready or not self._records or not query.strip():
            return []

        candidates = [
            (index, record)
            for index, record in enumerate(self._records)
            if not chapter_id or record.chapter_id == chapter_id
        ]
        if not candidates:
            return []

        bm25_ranks: list[tuple[int, float]] = []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(tokenize(query))
            for index, record in candidates:
                bm25_ranks.append((index, float(scores[index])))
        bm25_sorted = sorted(bm25_ranks, key=lambda item: (-item[1], item[0]))[:pool]
        bm25_order = {index: rank for rank, (index, _) in enumerate(bm25_sorted, start=1)}

        query_vec = embed(query)
        vector_scores = [
            (index, cosine(query_vec, record.vector)) for index, record in candidates
        ]
        vector_sorted = sorted(vector_scores, key=lambda item: (-item[1], item[0]))[:pool]
        vector_order = {index: rank for rank, (index, _) in enumerate(vector_sorted, start=1)}

        fused: dict[int, float] = {}
        for index, rank in bm25_order.items():
            fused[index] = fused.get(index, 0.0) + 1.0 / (60 + rank)
        for index, rank in vector_order.items():
            fused[index] = fused.get(index, 0.0) + 1.0 / (60 + rank)

        ordered = sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        results = []
        for index, score in ordered:
            record = self._records[index]
            channels = []
            if index in bm25_order:
                channels.append("bm25")
            if index in vector_order:
                channels.append("vector")
            results.append(
                {
                    "chunk_id": record.chunk_id,
                    "document_id": record.document_id,
                    "title": record.document_title,
                    "locator": {"section_path": record.section_path, "page": record.page},
                    "excerpt": record.text[:400],
                    "channels": channels,
                    "score": round(score, 4),
                }
            )
        return results

    def read_source(self, chunk_id: str, neighbor_count: int = 1) -> dict | None:
        for index, record in enumerate(self._records):
            if record.chunk_id != chunk_id:
                continue
            neighbors = []
            for offset in range(-neighbor_count, neighbor_count + 1):
                pos = index + offset
                if 0 <= pos < len(self._records):
                    neighbors.append(
                        {
                            "chunk_id": self._records[pos].chunk_id,
                            "excerpt": self._records[pos].text[:240],
                            "ordinal": offset,
                        }
                    )
            return {
                "chunk_id": record.chunk_id,
                "title": record.document_title,
                "locator": {"section_path": record.section_path, "page": record.page},
                "text": record.text,
                "neighbors": neighbors,
            }
        return None


retriever = Retriever()
