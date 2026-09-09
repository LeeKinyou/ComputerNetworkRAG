import logging
from pathlib import Path
from typing import AsyncIterator

import numpy as np
import openai
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc

from app.config import get_settings

logger = logging.getLogger(__name__)

ENTITY_TYPES_GUIDANCE = """实体类型必须从以下白名单中选择（计算机网络课程领域）：
- 协议：网络协议与标准（如 TCP、UDP、HTTP、ARP、OSPF）
- 设备：网络设备与硬件（如 路由器、交换机、集线器、网卡）
- 层次：网络体系结构中的层次（如 物理层、网络层、传输层、应用层）
- 地址：地址与编址概念（如 IP地址、MAC地址、端口号、CIDR）
- 算法：算法与机制（如 滑动窗口、拥塞控制、最长前缀匹配、三次握手）
- 性能指标：性能度量（如 带宽、时延、吞吐量、丢包率）
- 概念：上述类型之外的核心概念（如 套接字、分组、封装、复用）
仅当确实无法归入以上类型时才使用 Other。"""

_rag: LightRAG | None = None
_openai_client: openai.AsyncOpenAI | None = None


def _client() -> openai.AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY 未配置，请在 .env 中填写后再使用知识库功能")
        _openai_client = openai.AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            # 最多重试 1 次：保证最坏总时长（2 × LLM_TIMEOUT）不超 LightRAG worker 上限（LLM_TIMEOUT × 2）
            max_retries=1,
        )
    return _openai_client


async def _llm_model_func(
    prompt: str, system_prompt: str | None = None, history_messages=None, **kwargs
) -> str | AsyncIterator[str]:
    """LightRAG 的 LLM 入口。stream=True 时返回逐 token 的异步生成器（RAG 流式问答），
    否则返回完整字符串（实体抽取等建库任务）。"""
    settings = get_settings()
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages or [])
    messages.append({"role": "user", "content": prompt})

    if kwargs.get("stream"):
        stream = await _client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            timeout=settings.LLM_TIMEOUT,
            extra_body={"enable_thinking": False},
            stream=True,
        )

        async def _token_iter() -> AsyncIterator[str]:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        return _token_iter()

    resp = await _client().chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        timeout=settings.LLM_TIMEOUT,
        extra_body={"enable_thinking": False},
    )
    return resp.choices[0].message.content or ""


async def _embedding_func(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    resp = await _client().embeddings.create(
        model=settings.EMBEDDING_MODEL, input=texts, timeout=settings.LLM_TIMEOUT
    )
    return np.array([item.embedding for item in resp.data])


async def init_lightrag() -> LightRAG:
    global _rag
    if _rag is not None:
        return _rag

    settings = get_settings()
    if not settings.EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY 未配置，请在 .env 中填写后再使用知识库功能")

    probe = await _client().embeddings.create(
        model=settings.EMBEDDING_MODEL, input=["embedding 维度探测"]
    )
    embedding_dim = len(probe.data[0].embedding)
    logger.info("Embedding 模型 %s 维度=%d", settings.EMBEDDING_MODEL, embedding_dim)

    working_dir = Path(settings.LIGHTRAG_WORKING_DIR)
    working_dir.mkdir(parents=True, exist_ok=True)

    _rag = LightRAG(
        working_dir=str(working_dir),
        kv_storage="JsonKVStorage",
        vector_storage=settings.VECTOR_STORAGE,
        graph_storage=settings.GRAPH_STORAGE,
        doc_status_storage="JsonDocStatusStorage",
        llm_model_func=_llm_model_func,
        llm_model_name=settings.LLM_MODEL,
        embedding_func=EmbeddingFunc(
            embedding_dim=embedding_dim,
            func=_embedding_func,
            model_name=settings.EMBEDDING_MODEL,
        ),
        addon_params={
            "language": "Simplified Chinese",
            "entity_types_guidance": ENTITY_TYPES_GUIDANCE,
        },
    )
    await _rag.initialize_storages()
    logger.info("LightRAG 初始化完成，working_dir=%s", working_dir)
    return _rag


async def close_lightrag() -> None:
    global _rag, _openai_client
    if _rag is not None:
        await _rag.finalize_storages()
        _rag = None
    _openai_client = None


def get_lightrag() -> LightRAG:
    if _rag is None:
        raise RuntimeError("LightRAG 尚未初始化")
    return _rag


async def ainsert_text(text: str, doc_id: str, filename: str) -> None:
    await get_lightrag().ainsert(text, ids=doc_id, file_paths=filename)


async def adelete_document(doc_id: str) -> None:
    await get_lightrag().adelete_by_doc_id(doc_id)


async def get_doc_status(doc_id: str) -> dict | None:
    """从 LightRAG doc_status 读取该文档的最终处理状态（status/chunks_count/error）。"""
    try:
        return await get_lightrag().doc_status.get_by_id(doc_id)
    except Exception:
        logger.warning("读取文档 %s 状态失败", doc_id, exc_info=True)
        return None


async def get_chunk(chunk_id: str) -> dict | None:
    """读取分块元数据（含 file_path/full_doc_id），实体聚合丢失 file_path 时用于反查。"""
    try:
        return await get_lightrag().text_chunks.get_by_id(chunk_id)
    except Exception:
        logger.warning("读取分块 %s 失败", chunk_id, exc_info=True)
        return None


async def aquery(question: str, mode: str, conversation_history=None) -> str:
    param = QueryParam(
        mode=mode,
        conversation_history=conversation_history or [],
        enable_rerank=False,
    )
    return await get_lightrag().aquery(question, param=param)


async def aquery_context(question: str, mode: str) -> dict:
    """返回结构化检索数据：entities/relationships/chunks/references（不生成答案）。"""
    param = QueryParam(mode=mode, only_need_context=True, enable_rerank=False)
    data = await get_lightrag().aquery_data(question, param=param)
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


async def astream_query(
    question: str, mode: str
) -> tuple[list[dict], AsyncIterator[str]]:
    """流式问答：单次检索+生成，返回（来源分块列表, token 迭代器）。

    缓存命中或无上下文时 LightRAG 返回整段字符串，此处包装为单元素迭代器，
    调用方无需区分。检索/调用失败抛 RuntimeError（aquery_llm 不抛异常而是返回
    failure 字典，必须在这里转成异常，service 层才能发 error 事件）。
    """
    param = QueryParam(mode=mode, stream=True, enable_rerank=False)
    result = await get_lightrag().aquery_llm(question, param)
    if result.get("status") != "success":
        raise RuntimeError(result.get("message") or "RAG 查询失败")

    chunks = list((result.get("data") or {}).get("chunks") or [])
    llm_resp = result.get("llm_response") or {}
    iterator = llm_resp.get("response_iterator")

    if iterator is not None:
        return chunks, iterator

    async def _single() -> AsyncIterator[str]:
        yield llm_resp.get("content") or ""

    return chunks, _single()


async def get_graph_snapshot(max_nodes: int | None = None) -> tuple[list, list]:
    kg = await get_lightrag().get_knowledge_graph(node_label="*", max_nodes=max_nodes)
    return kg.nodes, kg.edges


async def get_entity_subgraph(name: str, max_depth: int = 1, max_nodes: int = 100) -> tuple:
    kg = await get_lightrag().get_knowledge_graph(
        node_label=name, max_depth=max_depth, max_nodes=max_nodes
    )
    info = await get_lightrag().get_entity_info(name)
    return kg.nodes, kg.edges, info
