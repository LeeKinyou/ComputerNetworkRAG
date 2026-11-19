"""可选的远端 embedding 通道（OpenAI 兼容 `/embeddings`）。

默认不启用：`EMBEDDING_BASE_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL` 任一为空时，
检索继续使用 `retrieval.embed()` 的本地哈希向量，零外部依赖。

三项齐全后：
- 刷新索引：切片批量向量化，结果按「切片 id + 文本」缓存到本地，续跑不重复计费；
- 查询问题：用同一模型编码，保证与索引同维度；
- 任一次远端失败：索引整体回退哈希向量（不混用两种维度），查询只走 BM25 并记一条警告。

因此这个模块是“可插拔”的：填上 Key 就启用，删掉就回到纯本地，不需要改检索代码。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger("cnrag.embedding")

BATCH_SIZE = 32
TIMEOUT_SECONDS = 20.0
MAX_TEXT_CHARS = 2000


def enabled() -> bool:
    return all(
        value.strip()
        for value in (
            settings.embedding_base_url,
            settings.embedding_api_key,
            settings.embedding_model,
        )
    )


def endpoint() -> str:
    base = settings.embedding_base_url.rstrip("/")
    return base if base.endswith("/embeddings") else f"{base}/embeddings"


def cache_key(chunk_id: str, text: str) -> str:
    """切片内容变化时自动失效，避免旧向量被复用。"""
    return hashlib.sha1(f"{chunk_id}|{text}".encode("utf-8")).hexdigest()


def _cache_path() -> Path:
    fingerprint = hashlib.sha1(
        f"{settings.embedding_base_url}|{settings.embedding_model}".encode("utf-8")
    ).hexdigest()[:12]
    directory = settings.resolve_path(settings.retrieval_cache_dir)
    return directory / f"embeddings-{fingerprint}.json"


def load_cache() -> dict[str, list[float]]:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        logger.warning("embedding 缓存损坏，按空缓存处理：%s", path)
        return {}


def save_cache(cache: dict[str, list[float]]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError as exc:
        logger.warning("embedding 缓存写入失败：%s", exc)


def _request(texts: list[str]) -> list[list[float]]:
    response = httpx.post(
        endpoint(),
        headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        json={"model": settings.embedding_model, "input": texts},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()["data"]
    ordered = sorted(payload, key=lambda item: item.get("index", 0))
    return [item["embedding"] for item in ordered]


def embed_documents(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for offset in range(0, len(texts), BATCH_SIZE):
        batch = [text[:MAX_TEXT_CHARS] for text in texts[offset : offset + BATCH_SIZE]]
        if not batch:
            continue
        vectors.extend(_request(batch))
    return vectors


def embed_query(text: str) -> list[float]:
    return _request([text[:MAX_TEXT_CHARS]])[0]
