import logging
from typing import AsyncIterator

from lightrag.query_validation import MIN_RAG_QUERY_WEIGHT, rag_query_weight

from app.config import get_settings
from app.rag import lightrag_factory
from app.schemas import Event
from app.storage.repository import Repository

logger = logging.getLogger(__name__)

VALID_MODES = {"naive", "local", "global", "hybrid"}

_SNIPPET_LEN = 120
_SNIPPET_FULL_LEN = 400
_TITLE_LEN = 30


def validate_question(question: str) -> None:
    """与 LightRAG 检索阈值一致（权重 ≥3，中文按 2 计），不满足直接 422。"""
    if rag_query_weight(question or "") < MIN_RAG_QUERY_WEIGHT:
        raise ValueError("问题太短：请至少输入 2 个中文词或 3 个英文字符")


def _snippet(text: str) -> str:
    flat = " ".join(str(text or "").split())
    return flat[:_SNIPPET_LEN] + ("…" if len(flat) > _SNIPPET_LEN else "")


def _snippet_full(text: str) -> str:
    """检索工具用的长片段：压平空白并截到 400 字，避免单个分块吃满 1500 字上下文。"""
    flat = " ".join(str(text or "").split())
    return flat[:_SNIPPET_FULL_LEN] + ("…" if len(flat) > _SNIPPET_FULL_LEN else "")


def _title(question: str) -> str:
    return question if len(question) <= _TITLE_LEN else question[:_TITLE_LEN] + "…"


def resolve_mode(mode: str | None) -> str:
    """非法/缺省模式回退全局配置默认；回退标注由调用方按需记录。"""
    settings = get_settings()
    default_mode = settings.RAG_QUERY_MODE if settings.RAG_QUERY_MODE in VALID_MODES else "hybrid"
    requested = (mode or "").strip().lower()
    return requested if requested in VALID_MODES else default_mode


def _error_message(exc: Exception) -> str:
    raw = str(exc or "")
    lowered = raw.lower()
    if isinstance(exc, TimeoutError) or "timed out" in lowered or "timeout" in lowered:
        return "模型服务超时，请重试"
    if "api key" in lowered or "unauthorized" in lowered or "401" in lowered:
        return "模型服务鉴权失败，请检查 .env 中的密钥配置"
    logger.warning("RAG 问答失败：%s", raw)
    return "模型服务异常，请稍后重试"


class RAGService:
    def __init__(self, repo: Repository):
        self._repo = repo

    async def stream_answer(
        self, question: str, mode: str | None = None, session_id: str | None = None
    ) -> AsyncIterator[Event]:
        requested = (mode or "").strip().lower()
        fallback = bool(requested) and requested not in VALID_MODES
        mode = resolve_mode(mode)

        if not session_id:
            session_id = await self._repo.create_session("rag", _title(question))
        meta = {"session_id": session_id, "mode": mode}
        if fallback:
            meta["mode_requested"] = requested
        yield Event(name="meta", data=meta)

        try:
            await self._repo.add_message(session_id, "user", question)
            chunks, token_iter = await lightrag_factory.astream_query(question, mode)
            sources = [
                {"doc_name": c.get("file_path") or "未知文档",
                 "chunk_id": c.get("chunk_id") or "",
                 "snippet": _snippet(c.get("content"))}
                for c in chunks
            ]
            yield Event(name="sources", data={"items": sources})

            answer_parts: list[str] = []
            async for delta in token_iter:
                if not delta:
                    continue
                answer_parts.append(delta)
                yield Event(name="token", data={"delta": delta})

            answer = "".join(answer_parts)
            yield Event(name="final", data={"answer": answer})
            await self._repo.add_message(session_id, "assistant", answer)
        except Exception as exc:  # noqa: BLE001 — 统一转 error 事件
            yield Event(name="error", data={"message": _error_message(exc)})

    async def retrieve(self, query: str, mode: str | None = None) -> dict:
        """课程检索（不生成答案），供 course_rag_query 工具使用（05 §2.4）。"""
        resolved = resolve_mode(mode)
        data = await lightrag_factory.aquery_context(query, resolved)
        chunks = [
            {
                "doc_name": c.get("file_path") or "未知文档",
                "chunk_id": c.get("chunk_id") or "",
                "content": _snippet_full(c.get("content")),
            }
            for c in data.get("chunks") or []
        ]
        return {"mode": resolved, "chunks": chunks}


def init_rag_service(repo: Repository) -> RAGService:
    global _rag_service
    _rag_service = RAGService(repo)
    return _rag_service


def get_rag_service() -> RAGService:
    if _rag_service is None:
        raise RuntimeError("RAGService 尚未初始化")
    return _rag_service


_rag_service: RAGService | None = None
