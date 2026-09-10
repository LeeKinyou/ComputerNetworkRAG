"""CompoundTaskMiddleware 测试：复合问题至少两轮工具（05 §1.1）。

ScriptedModel 记录每次调用收到的 messages，断言调度提醒只在
"复合问题 + 工具轮数不足"的当轮出现，且不落检查点状态。
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent.builder import build_agent, close_checkpointer, open_checkpointer
from app.agent.middleware import CompoundTaskMiddleware
from app.agent.runner import run_agent
from app.agent.tools import create_registry


class RecordingModel(BaseChatModel):
    responses: list = []
    idx: int = 0
    received: list = []

    @property
    def _llm_type(self):
        return "recording"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.received = self.received + [list(messages)]
        msg = self.responses[min(self.idx, len(self.responses) - 1)]
        self.idx += 1
        if msg.tool_calls:
            msg = AIMessage(
                content=msg.content,
                tool_calls=[
                    {**tc, "id": f"c{self.idx}-{i}"} for i, tc in enumerate(msg.tool_calls)
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=msg)])


COMPOUND_Q = "192.168.10.137/27 属于哪个子网？这个子网的网关一般设哪个地址？为什么？"
SIMPLE_Q = "192.168.10.137/27 的网络地址是什么？"


def tool_call(name, args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "c1"}])


async def make_agent(responses):
    model = RecordingModel(responses=responses)
    agent = build_agent(create_registry(), model=model)
    return agent, model


async def collect(agent, question, run_id="r_ct"):
    return [ev async for ev in run_agent(agent, question, run_id=run_id)]


def _texts(messages: list[BaseMessage]) -> str:
    return "\n".join(str(m.content) for m in messages)


async def test_compound_question_gets_nudge_on_second_call(tmp_path):
    await close_checkpointer()
    await open_checkpointer(str(tmp_path / "langgraph.db"))
    try:
        agent, model = await make_agent(
            [tool_call("subnet_calculator", {"ip_cidr": "192.168.10.137/27"}),
             AIMessage(content="第一版答案")]
        )
        events = await collect(agent, COMPOUND_Q, run_id="r_ct1")
        # 两次模型调用：第二次（工具观察回灌后）必须带调度提醒
        assert len(model.received) == 2
        assert "调度提醒" not in _texts(model.received[0])
        assert "调度提醒" in _texts(model.received[1])
        # 事件流正常收敛：final 是唯一答案，无重复 token 轮
        assert events[-1].name == "final"
        tokens = [e for e in events if e.name == "token"]
        assert len(tokens) == 1
    finally:
        await close_checkpointer()


async def test_simple_question_never_gets_nudge(tmp_path):
    await close_checkpointer()
    await open_checkpointer(str(tmp_path / "langgraph.db"))
    try:
        agent, model = await make_agent(
            [tool_call("subnet_calculator", {"ip_cidr": "192.168.10.137/27"}),
             AIMessage(content="网络地址是 192.168.10.128。")]
        )
        await collect(agent, SIMPLE_Q, run_id="r_ct2")
        assert len(model.received) == 2
        assert all("调度提醒" not in _texts(msgs) for msgs in model.received)
    finally:
        await close_checkpointer()


async def test_nudge_not_persisted_to_checkpointer(tmp_path):
    await close_checkpointer()
    await open_checkpointer(str(tmp_path / "langgraph.db"))
    try:
        agent, model = await make_agent(
            [tool_call("subnet_calculator", {"ip_cidr": "192.168.10.137/27"}),
             AIMessage(content="完整答案。")]
        )
        await collect(agent, COMPOUND_Q, run_id="r_ct3")
        # 第三轮（若继续追问同 thread）不该看到上一轮注入的提醒
        state = await agent.aget_state({"configurable": {"thread_id": "r_ct3"}})
        assert "调度提醒" not in _texts(state.values["messages"])
    finally:
        await close_checkpointer()


def test_compound_detection_rules():
    mw = CompoundTaskMiddleware()
    assert mw.is_compound("A 属于哪个子网？网关设哪个地址？为什么？")
    assert mw.is_compound("10.0.0.1/24 的网络地址是什么？请结合课件说明")
    assert not mw.is_compound("10.0.0.1/24 的网络地址是什么？")
    assert not mw.is_compound("用一句话说明什么是子网掩码")
    assert not mw.is_compound("对比 TCP 和 UDP 的区别")
