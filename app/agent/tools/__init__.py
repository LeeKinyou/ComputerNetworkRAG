"""P0 工具注册：新增工具 = 实现 BaseTool 后在此一行注册（03 §4.2）。

course_rag_query 需要构造注入 RAGService，未提供时跳过注册
（纯算法与 DNS 工具始终可用）。
"""

from app.agent.registry import ToolRegistry
from app.agent.tools.course_rag import CourseRagTool
from app.agent.tools.dns import DnsLookupTool
from app.agent.tools.lpm import LpmLookupTool
from app.agent.tools.subnet import SubnetCalculatorTool

__all__ = [
    "create_registry",
    "CourseRagTool",
    "DnsLookupTool",
    "LpmLookupTool",
    "SubnetCalculatorTool",
]


def create_registry(rag_service=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(SubnetCalculatorTool())
    registry.register(LpmLookupTool())
    registry.register(DnsLookupTool())
    if rag_service is not None:
        registry.register(CourseRagTool(rag_service))
    return registry
