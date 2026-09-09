"""course_rag_query 测试：mock RAGService（05 §2.4）。"""

import pytest

from app.agent.tools import create_registry
from app.agent.tools.course_rag import CourseRagTool


class FakeRagService:
    def __init__(self, data):
        self._data = data
        self.calls = []

    async def retrieve(self, query, mode=None):
        self.calls.append((query, mode))
        return self._data


def make_service(chunks, mode="hybrid"):
    return FakeRagService({"mode": mode, "chunks": chunks})


def chunk(doc, cid, content):
    return {"doc_name": doc, "chunk_id": cid, "content": content}


async def test_output_numbered_and_structured():
    service = make_service(
        [
            chunk("第4章-网络层.md", "c-1", "IP 地址分为网络位与主机位"),
            chunk("传输层要点.txt", "c-2", "端口号标识应用进程"),
        ]
    )
    result = await CourseRagTool(service)._run(query="子网掩码")
    assert result.status == "success"
    assert "[1] 第4章-网络层.md：" in result.output
    assert "[2] 传输层要点.txt：" in result.output
    assert result.structured["mode"] == "hybrid"
    assert result.structured["sources"] == [
        {"doc_name": "第4章-网络层.md", "chunk_id": "c-1", "snippet": "IP 地址分为网络位与主机位"},
        {"doc_name": "传输层要点.txt", "chunk_id": "c-2", "snippet": "端口号标识应用进程"},
    ]
    assert service.calls == [("子网掩码", None)]


async def test_mode_passthrough():
    service = make_service([], mode="naive")
    await CourseRagTool(service)._run(query="TCP", mode="naive")
    assert service.calls == [("TCP", "naive")]


async def test_empty_result():
    service = make_service([])
    result = await CourseRagTool(service)._run(query="冷门问题")
    assert result.status == "success"
    assert "未检索到" in result.output
    assert result.structured["sources"] == []


async def test_output_capped_at_1500():
    long_text = "很长的课件内容" * 500  # 单块 3500 字
    service = make_service([chunk(f"文档{i}.md", f"c-{i}", long_text) for i in range(5)])
    result = await CourseRagTool(service)._run(query="长文检索")
    assert result.status == "success"
    assert len(result.output) <= 1500


async def test_registered_with_rag_service():
    registry = create_registry(rag_service=make_service([]))
    assert "course_rag_query" in registry.names()
    assert "dns_lookup" in registry.names()
    assert {"subnet_calculator", "lpm_lookup"} <= set(registry.names())


async def test_schema_missing_query():
    registry = create_registry(rag_service=make_service([]))
    result = await registry.run("course_rag_query", {})
    assert result.status == "failed"
    assert "缺少必填参数" in result.output
