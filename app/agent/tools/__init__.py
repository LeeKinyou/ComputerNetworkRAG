"""P0 工具注册：新增工具 = 实现 BaseTool 后在此一行注册（03 §4.2）。"""

from app.agent.registry import ToolRegistry
from app.agent.tools.lpm import LpmLookupTool
from app.agent.tools.subnet import SubnetCalculatorTool

__all__ = ["create_registry", "LpmLookupTool", "SubnetCalculatorTool"]


def create_registry(rag_service=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(SubnetCalculatorTool())
    registry.register(LpmLookupTool())
    return registry
