"""人工审批（HITL，P1）测试：interrupt 中断、持久化状态、resume 三种决策。

用真实 create_agent + HumanInTheLoopMiddleware + 脚本化模型驱动完整图，
GateTool(ping_host) 记录真实调用次数，验证 approve 执行 / edit 换参 /
reject 不执行；service 层验证 waiting_approval 落库与 resume 续跑。
"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from test_agent_runner import ScriptedModel, tool_call

from app.agent.builder import build_agent, close_checkpointer, open_checkpointer
from app.agent.registry import BaseTool, ToolRegistry, ToolResult
from app.agent.runner import (
    NoPendingInterruptError,
    get_pending_interrupts,
    resume_agent,
    run_agent,
)
from app.agent.tools import create_registry
from app.agent.tools.subnet import SubnetCalculatorTool
from app.api.approval import agent_resume
from app.config import get_settings
from app.schemas import ApprovalRequest
from app.services.agent_service import get_agent_service, init_agent_service
from app.storage.sqlite_repo import init_repo


class GateTool(BaseTool):
    name = "ping_host"
    description = "测试审批工具：记录调用参数"
    args_schema = {
        "type": "object",
        "properties": {"host": {"type": "string"}},
        "required": ["host"],
    }
    requires_approval = True

    def __init__(self):
        self.calls = []

    async def _run(self, host="", **kwargs) -> ToolResult:
        self.calls.append(host)
        return ToolResult(status="success", output=f"pong {host}", structured={"host": host})


@pytest.fixture
async def agent_env(tmp_path):
    await close_checkpointer()
    await open_checkpointer(str(tmp_path / "langgraph.db"))
    yield tmp_path
    await close_checkpointer()


@pytest.fixture
def hitl_env(monkeypatch):
    monkeypatch.setenv("HITL_ENABLED", "true")
    monkeypatch.setenv("APPROVAL_TOOLS", "ping_host")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_hitl_env(monkeypatch):
    monkeypatch.setenv("HITL_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def repo(tmp_path):
    r = init_repo(tmp_path / "test.db")
    await r.init()
    yield r
    await r.close()


def make_hitl_agent(responses, gate):
    registry = ToolRegistry()
    registry.register(SubnetCalculatorTool())
    registry.register(gate)
    return build_agent(registry, model=ScriptedModel(responses=responses))


async def interrupt_a_run(agent, run_id):
    """跑到审批中断并返回首轮事件。"""
    return [ev async for ev in run_agent(agent, "帮我探测 www.example.com", run_id=run_id)]


async def test_interrupt_pauses_before_tool(agent_env, hitl_env):
    gate = GateTool()
    agent = make_hitl_agent(
        [tool_call("ping_host", {"host": "www.example.com"}), AIMessage(content="已批准。")],
        gate,
    )
    events = await interrupt_a_run(agent, "r_ap1")

    names = [e.name for e in events]
    # 中断发生在 tools 执行前：action 事件已发出，随后 interrupt，无 final
    assert names == ["meta", "step_start", "action", "interrupt"]
    assert events[-1].data == {
        "step_no": 1,
        "tool": "ping_host",
        "args": {"host": "www.example.com"},
    }
    assert gate.calls == []
    # 持久化状态：检查点里留有待审批的工具调用，可跨请求恢复
    pending = await get_pending_interrupts(agent, "r_ap1")
    assert len(pending) == 1
    assert pending[0]["name"] == "ping_host"
    assert pending[0]["args"] == {"host": "www.example.com"}


async def test_resume_approve_executes_tool(agent_env, hitl_env):
    gate = GateTool()
    agent = make_hitl_agent(
        [tool_call("ping_host", {"host": "www.example.com"}), AIMessage(content="已批准并完成。")],
        gate,
    )
    await interrupt_a_run(agent, "r_ap2")

    events = [
        ev
        async for ev in resume_agent(agent, "r_ap2", "approve", None, step_no_start=1)
    ]
    names = [e.name for e in events]
    assert names == ["resumed", "observation", "token", "final"]
    assert events[0].data == {"run_id": "r_ap2", "decision": "approve"}

    obs = events[1].data
    assert obs["step_no"] == 1
    assert obs["status"] == "success"
    assert "www.example.com" in obs["result"]

    final = events[-1].data
    assert final["answer"] == "已批准并完成。"
    assert final["steps_count"] == 1
    assert gate.calls == ["www.example.com"]


async def test_resume_edit_uses_edited_args(agent_env, hitl_env):
    gate = GateTool()
    agent = make_hitl_agent(
        [tool_call("ping_host", {"host": "www.example.com"}), AIMessage(content="已改参执行。")],
        gate,
    )
    await interrupt_a_run(agent, "r_ap3")

    events = [
        ev
        async for ev in resume_agent(agent, "r_ap3", "edit", {"host": "www.qq.com"}, step_no_start=1)
    ]
    assert events[0].name == "resumed"
    assert events[0].data["decision"] == "edit"
    assert gate.calls == ["www.qq.com"]
    assert events[-1].name == "final"


async def test_resume_reject_skips_tool(agent_env, hitl_env):
    gate = GateTool()
    agent = make_hitl_agent(
        [tool_call("ping_host", {"host": "www.example.com"}), AIMessage(content="好的，不探测了。")],
        gate,
    )
    await interrupt_a_run(agent, "r_ap4")

    events = [
        ev
        async for ev in resume_agent(agent, "r_ap4", "reject", None, step_no_start=1)
    ]
    names = [e.name for e in events]
    # 拒绝后不产生 observation，直接进入最终回答
    assert names == ["resumed", "token", "final"]
    assert events[-1].data["answer"] == "好的，不探测了。"
    assert gate.calls == []


async def test_resume_without_pending_interrupt_raises(agent_env, hitl_env):
    gate = GateTool()
    agent = make_hitl_agent([AIMessage(content="直接回答。")], gate)
    with pytest.raises(NoPendingInterruptError):
        [ev async for ev in resume_agent(agent, "r_none", "approve", None)]


async def test_build_agent_wires_hitl_middleware(agent_env, hitl_env):
    agent = build_agent(create_registry(), model=ScriptedModel(responses=[AIMessage(content="x")]))
    assert any("after_model" in name for name in agent.nodes)


async def test_build_agent_no_middleware_when_hitl_disabled(agent_env, no_hitl_env):
    agent = build_agent(create_registry(), model=ScriptedModel(responses=[AIMessage(content="x")]))
    assert not any("after_model" in name for name in agent.nodes)


# ----- service 层：waiting_approval 落库与 resume 续跑 -----


async def test_run_waits_approval_in_db(agent_env, hitl_env, repo):
    gate = GateTool()
    agent = make_hitl_agent(
        [tool_call("ping_host", {"host": "www.example.com"}), AIMessage(content="已批准。")],
        gate,
    )
    service = init_agent_service(repo, agent)
    events = []
    async for ev in service.stream_chat("帮我探测 www.example.com"):
        events.append(ev)

    assert [e.name for e in events][-1] == "interrupt"
    run_id = events[0].data["run_id"]
    run = await repo.get_run(run_id)
    assert run.status == "waiting_approval"
    assert run.final_answer is None
    assert run.steps_count == 1
    steps = await repo.get_run_steps(run_id)
    assert [s.kind for s in steps] == ["action"]
    messages = await repo.list_messages(events[0].data["session_id"])
    assert [m.role for m in messages] == ["user"]  # 尚无 assistant 消息

    resumed = []
    async for ev in service.stream_resume(run_id, "approve", None):
        resumed.append(ev)
    assert resumed[0].name == "resumed"
    assert resumed[0].data == {"run_id": run_id, "decision": "approve"}
    assert resumed[-1].name == "final"

    run = await repo.get_run(run_id)
    assert run.status == "success"
    assert run.final_answer == "已批准。"
    steps = await repo.get_run_steps(run_id)
    assert [s.kind for s in steps] == ["action", "observation"]
    messages = await repo.list_messages(events[0].data["session_id"])
    assert [m.role for m in messages] == ["user", "assistant"]


async def test_service_resume_rejects_non_waiting_run(repo):
    from test_agent_service import FakeAgent  # noqa: PLC0415 — 复用现成假代理

    service = init_agent_service(repo, FakeAgent([]))
    with pytest.raises(NoPendingInterruptError):
        async for _ in service.stream_resume("r_missing", "approve", None):
            pass


async def test_service_resume_requires_edit_args(repo):
    from test_agent_service import FakeAgent  # noqa: PLC0415

    service = init_agent_service(repo, FakeAgent([]))
    with pytest.raises(ValueError):
        ApprovalRequest(decision="edit", edited_args=None)


# ----- API 层：HITL 关闭 400 / 无中断 409 -----


async def test_resume_endpoint_disabled_returns_400(repo, monkeypatch):
    monkeypatch.setenv("HITL_ENABLED", "false")
    get_settings.cache_clear()
    try:
        init_agent_service(repo, SimpleNamespace(astream=None))
        resp = await agent_resume("r_x", ApprovalRequest(decision="approve"))
        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert body["error_code"] == "HITL_DISABLED"
    finally:
        get_settings.cache_clear()


async def test_resume_endpoint_unknown_run_returns_409(repo, hitl_env):
    from test_agent_service import FakeAgent  # noqa: PLC0415

    init_agent_service(repo, FakeAgent([]))
    resp = await agent_resume("r_missing", ApprovalRequest(decision="approve"))
    assert resp.status_code == 409
    body = json.loads(resp.body)
    assert body["error_code"] == "NO_PENDING_INTERRUPT"


async def test_resume_endpoint_ping_tool_registered():
    registry = create_registry()
    tool = registry.get("ping_host")
    assert tool is not None
    assert tool.requires_approval is True
