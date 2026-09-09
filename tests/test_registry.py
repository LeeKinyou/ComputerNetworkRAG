"""ToolRegistry 适配层测试：openai_schemas 与 to_langchain_tools JSON 信封（03 §4.2）。"""

import json

from app.agent.tools import create_registry


def test_openai_schemas():
    registry = create_registry()
    schemas = registry.openai_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert {"subnet_calculator", "lpm_lookup"} <= names
    for s in schemas:
        assert s["type"] == "function"
        assert s["function"]["parameters"]["type"] == "object"


def test_openai_schemas_enabled_filter():
    registry = create_registry()
    schemas = registry.openai_schemas(enabled=["lpm_lookup"])
    assert [s["function"]["name"] for s in schemas] == ["lpm_lookup"]


async def test_langchain_adapter_envelope():
    registry = create_registry()
    tools = registry.to_langchain_tools()
    subnet = next(t for t in tools if t.name == "subnet_calculator")
    raw = await subnet.coroutine(ip_cidr="192.168.10.137/27")
    envelope = json.loads(raw)
    assert envelope["status"] == "success"
    assert envelope["structured"]["network"] == "192.168.10.128"
    assert envelope["elapsed_ms"] >= 0
    assert set(envelope) == {"status", "output", "structured", "elapsed_ms"}


async def test_langchain_adapter_failed_envelope():
    registry = create_registry()
    tools = registry.to_langchain_tools(enabled=["subnet_calculator"])
    assert [t.name for t in tools] == ["subnet_calculator"]
    raw = await tools[0].coroutine(ip_cidr="bad")
    envelope = json.loads(raw)
    assert envelope["status"] == "failed"
    assert envelope["output"]
