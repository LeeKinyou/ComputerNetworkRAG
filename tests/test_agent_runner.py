"""run_agent 事件映射测试：脚本化假模型驱动真实 create_agent 图（03 §3.2）。

checkpointer 是模块级 aiosqlite 连接：aiosqlite 的连接与事件循环绑定，
pytest-asyncio 每个测试用新循环，故用 fixture 保证同一循环内 open/close，
避免跨循环 close 死锁。
"""

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent.builder import build_agent, close_checkpointer, open_checkpointer
from app.agent.runner import run_agent
from app.agent.tools import create_registry


class ScriptedModel(BaseChatModel):
    responses: list = []
    idx: int = 0

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self.responses[min(self.idx, len(self.responses) - 1)]
        self.idx += 1
        if msg.tool_calls:
            # 每轮生成唯一 tool_call id：重复 id 会让 langgraph 分支/checkpointer 状态错乱
            msg = AIMessage(
                content=msg.content,
                tool_calls=[
                    {**tc, "id": f"c{self.idx}-{i}"} for i, tc in enumerate(msg.tool_calls)
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=msg)])


@pytest.fixture
async def agent_env(tmp_path):
    await close_checkpointer()
    await open_checkpointer(str(tmp_path / "langgraph.db"))
    yield tmp_path
    await close_checkpointer()


def tool_call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


async def make_agent(responses):
    return build_agent(create_registry(), model=ScriptedModel(responses=responses))


async def collect(agent, question, run_id="r_test"):
    return [ev async for ev in run_agent(agent, question, run_id=run_id)]


async def test_meta_includes_session_id(agent_env):
    agent = await make_agent([AIMessage(content="直接回答。")])
    events = [
        ev async for ev in run_agent(agent, "你好", run_id="r_m1", session_id="s_m1")
    ]
    assert events[0].name == "meta"
    assert events[0].data == {"run_id": "r_m1", "session_id": "s_m1"}


async def test_single_tool_flow(agent_env):
    agent = await make_agent(
        [
            tool_call("subnet_calculator", {"ip_cidr": "192.168.10.137/27"}),
            AIMessage(content="该地址属于 192.168.10.128/27 网段。"),
        ]
    )
    events = await collect(agent, "192.168.10.137/27 属于哪个子网？")
    names = [e.name for e in events]
    # 最终回答轮不发 step_start：step_start 只给工具轮（04 §6.2 示例）
    assert names == ["meta", "step_start", "action", "observation", "token", "final"]

    action = events[2].data
    assert action["tool"] == "subnet_calculator"
    assert action["args"] == {"ip_cidr": "192.168.10.137/27"}

    obs = events[3].data
    assert obs["step_no"] == 1
    assert obs["status"] == "success"
    assert obs["structured"]["network"] == "192.168.10.128"
    assert "192.168.10.128" in obs["result"]

    final = events[-1].data
    assert final["answer"] == "该地址属于 192.168.10.128/27 网段。"
    assert final["steps_count"] == 1
    assert final["truncated"] is False


async def test_thought_emitted_when_content_present(agent_env):
    agent = await make_agent(
        [
            AIMessage(
                content="这是子网计算题，先调用计算器。",
                tool_calls=[{"name": "subnet_calculator", "args": {"ip_cidr": "10.0.5.9/16"}, "id": "c1"}],
            ),
            AIMessage(content="答案。"),
        ]
    )
    events = await collect(agent, "问题")
    thought = next(e for e in events if e.name == "thought")
    assert thought.data == {"step_no": 1, "content": "这是子网计算题，先调用计算器。"}


async def test_two_tools_sequence(agent_env):
    agent = await make_agent(
        [
            AIMessage(
                content="先算子网。",
                tool_calls=[{"name": "subnet_calculator", "args": {"ip_cidr": "192.168.10.137/27"}, "id": "c1"}],
            ),
            AIMessage(
                content="再查路由。",
                tool_calls=[{"name": "lpm_lookup", "args": {"destination_ip": "10.2.3.4"}, "id": "c2"}],
            ),
            AIMessage(content="结论：网关用 192.168.10.129，目的地址走 R3。"),
        ]
    )
    events = await collect(agent, "复合问题")
    actions = [e.data for e in events if e.name == "action"]
    assert [a["tool"] for a in actions] == ["subnet_calculator", "lpm_lookup"]
    assert [a["step_no"] for a in actions] == [1, 2]
    observations = [e.data for e in events if e.name == "observation"]
    assert len(observations) == 2
    assert observations[1]["structured"]["selected"]["next_hop"] == "R4"
    final = events[-1].data
    assert final["steps_count"] == 2
    assert "R3" in final["answer"]


async def test_tool_failure_becomes_failed_observation(agent_env):
    agent = await make_agent(
        [
            tool_call("subnet_calculator", {"ip_cidr": "bad-input"}),
            AIMessage(content="输入格式有误，请提供形如 a.b.c.d/n 的 CIDR。"),
        ]
    )
    events = await collect(agent, "问题")
    obs = next(e for e in events if e.name == "observation")
    assert obs.data["status"] == "failed"
    assert obs.data["result"]
    final = events[-1]
    assert final.name == "final"


async def test_recursion_limit_marks_truncated(agent_env):
    agent = await make_agent(
        [tool_call("subnet_calculator", {"ip_cidr": "10.0.0.1/24"})]
    )
    events = await collect(agent, "问题")
    final = events[-1].data
    assert final["truncated"] is True
    assert final["steps_count"] >= 1


async def test_checkpointer_db_created(agent_env):
    db_path = agent_env / "langgraph.db"
    agent = await make_agent([AIMessage(content="直接回答")])
    events = await collect(agent, "问题")
    assert events[-1].name == "final"
    assert db_path.exists()
