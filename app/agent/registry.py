"""工具注册表：统一参数校验、计时、异常捕获与 LangChain 适配（03 §4.2）。"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class ToolResult(BaseModel):
    status: Literal["success", "failed"]
    output: str
    structured: dict = {}
    elapsed_ms: int = 0


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    args_schema: dict = {}
    requires_approval: bool = False
    timeout_s: float | None = None

    @abstractmethod
    async def _run(self, **kwargs) -> ToolResult: ...


def _check_type(value: Any, expected: str) -> bool:
    py_type = _JSON_TYPES.get(expected)
    if py_type is None:
        return True
    if isinstance(value, bool) and expected in ("integer", "number"):
        return False
    return isinstance(value, py_type)


def _validate_args(args: dict, schema: dict) -> str | None:
    """校验 OpenAI JSON Schema 的常用子集：required / type / enum / array.items。"""
    props = schema.get("properties") or {}
    for req in schema.get("required") or []:
        if req not in args:
            return f"缺少必填参数：{req}"
    for key, value in args.items():
        spec = props.get(key)
        if spec is None:
            continue
        expected = spec.get("type")
        if expected and not _check_type(value, expected):
            return f"参数 {key} 的类型应为 {expected}"
        if "enum" in spec and value not in spec["enum"]:
            allowed = "/".join(str(v) for v in spec["enum"])
            return f"参数 {key} 仅允许：{allowed}"
        if expected == "array" and isinstance(value, list):
            item_spec = spec.get("items") or {}
            item_props = item_spec.get("properties") or {}
            for i, item in enumerate(value):
                if not _check_type(item, item_spec.get("type", "object")):
                    return f"参数 {key} 第 {i + 1} 项类型非法"
                for req in item_spec.get("required") or []:
                    if not isinstance(item, dict) or req not in item:
                        return f"参数 {key} 第 {i + 1} 项缺少必填字段：{req}"
                for item_key, item_value in item.items():
                    item_type = (item_props.get(item_key) or {}).get("type")
                    if item_type and not _check_type(item_value, item_type):
                        return f"参数 {key} 第 {i + 1} 项的字段 {item_key} 类型应为 {item_type}"
    return None


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("工具缺少 name")
        if tool.name in self._tools:
            raise ValueError(f"工具重复注册：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def openai_schemas(self, enabled: list[str] | None = None) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.args_schema,
                },
            }
            for t in self._tools.values()
            if enabled is None or t.name in enabled
        ]

    async def run(self, name: str, args: dict | None = None) -> ToolResult:
        """统一入口：校验 → 计时 → 异常吞掉转 failed（不向上抛）。"""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(status="failed", output=f"未知工具：{name}")
        args = args if isinstance(args, dict) else {}
        error = _validate_args(args, tool.args_schema)
        if error:
            return ToolResult(status="failed", output=error)

        start = time.perf_counter()
        try:
            coro = tool._run(**args)
            if tool.timeout_s is not None:
                result = await asyncio.wait_for(coro, timeout=tool.timeout_s)
            else:
                result = await coro
        except asyncio.TimeoutError:
            elapsed = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                status="failed",
                output=f"工具执行超时（超过 {tool.timeout_s:g} 秒）",
                elapsed_ms=elapsed,
            )
        except Exception as exc:  # noqa: BLE001 — 工具异常不回灌堆栈，只进日志
            logger.warning("工具 %s 执行异常：%s", name, exc, exc_info=True)
            elapsed = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                status="failed", output="工具执行出错，请稍后重试", elapsed_ms=elapsed
            )
        result.elapsed_ms = int((time.perf_counter() - start) * 1000)
        return result

    def to_langchain_tools(self, enabled: list[str] | None = None) -> list:
        """把 BaseTool 适配为 LangChain 工具：ToolMessage 为统一 JSON 信封，
        runner 据此还原 observation 事件。业务工具代码不 import LangChain。"""
        from langchain_core.tools import StructuredTool

        def _make(tool: BaseTool) -> StructuredTool:
            async def _call(**kwargs) -> str:
                result = await self.run(tool.name, kwargs)
                return json.dumps(result.model_dump(), ensure_ascii=False)

            return StructuredTool(
                name=tool.name,
                description=tool.description,
                args_schema=tool.args_schema,
                coroutine=_call,
            )

        return [
            _make(t)
            for t in self._tools.values()
            if enabled is None or t.name in enabled
        ]
