"""AgentService 测试：run 生命周期、trace 落库、异常/客户端断开处理（03 §3.2）。

用 FakeAgent 直接驱动 run_agent（不经 create_agent），聚焦 service 层的
落库逻辑；事件映射本身已在 test_agent_runner.py 覆盖。repo 用真实
SqliteRepository（tmp_path），保证 SQL/JSON 序列化路径真实可信。
"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.api.sessions import get_session_run
from app.services.agent_service import get_agent_service, init_agent_service
from app.storage.sqlite_repo import init_repo


def envelope(status="success", elapsed_ms=12, output="网络地址 192.168.10.128/27", **structured):
    return json.dumps(
        {"status": status, "elapsed_ms": elapsed_ms, "output": output, "structured": structured},
        ensure_ascii=False,
    )


def tool_call_msg():
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "subnet_calculator", "args": {"ip_cidr": "192.168.10.137/27"}, "id": "c1"}
        ],
    )


class FakeAgent:
    """按脚本回放 (mode, chunk) 序列；脚本耗尽后可抛异常模拟模型/框架故障。"""

    def __init__(self, chunks, exc=None):
        self._chunks = chunks
        self._exc = exc

    def astream(self, inp, config=None, stream_mode=None):
        async def gen():
            for chunk in self._chunks:
                yield chunk
            if self._exc is not None:
                raise self._exc

        return gen()

    async def aget_state(self, config):
        # run_agent 流结束后统一查一次检查点中断；假代理永远没有中断
        return SimpleNamespace(tasks=[])


@pytest.fixture
async def repo(tmp_path):
    r = init_repo(tmp_path / "test.db")
    await r.init()
    yield r
    await r.close()


@pytest.fixture
def tool_chunks():
    return [
        ("updates", {"model": {"messages": [AIMessage(content="先算子网。", tool_calls=[
            {"name": "subnet_calculator", "args": {"ip_cidr": "192.168.10.137/27"}, "id": "c1"}
        ])]}}),
        ("updates", {"tools": {"messages": [
            ToolMessage(content=envelope(network="192.168.10.128"), tool_call_id="c1")
        ]}}),
        ("updates", {"model": {"messages": [AIMessage(content="该地址属于 192.168.10.128/27。")]}}),
    ]


async def collect(service, question, session_id=None):
    events = []
    async for ev in service.stream_chat(question, session_id):
        events.append(ev)
    return events


async def test_happy_path_lifecycle(repo, tool_chunks):
    service = init_agent_service(repo, FakeAgent(tool_chunks))
    events = await collect(service, "192.168.10.137/27 属于哪个子网？")

    assert [e.name for e in events] == [
        "meta", "step_start", "thought", "action", "observation", "token", "final",
    ]
    assert events[0].data["run_id"]
    assert events[0].data["session_id"]
    answer = "该地址属于 192.168.10.128/27。"
    assert events[-1].data["answer"] == answer
    assert events[-1].data["steps_count"] == 1
    assert events[-1].data["truncated"] is False

    run = await repo.get_run(events[0].data["run_id"])
    assert run.status == "success"
    assert run.final_answer == answer
    assert run.steps_count == 1
    assert run.finished_at

    steps = await repo.get_run_steps(run.run_id)
    assert [(s.kind, s.step_no) for s in steps] == [
        ("thought", 1), ("action", 1), ("observation", 1),
    ]
    assert steps[0].content == "先算子网。"
    assert steps[1].tool_name == "subnet_calculator"
    assert steps[1].tool_args == {"ip_cidr": "192.168.10.137/27"}
    assert steps[2].status == "success"
    assert steps[2].elapsed_ms == 12
    assert steps[2].content == "网络地址 192.168.10.128/27"
    assert steps[2].structured == {"network": "192.168.10.128"}

    messages = await repo.list_messages(events[0].data["session_id"])
    assert [(m.role, m.content) for m in messages] == [
        ("user", "192.168.10.137/27 属于哪个子网？"),
        ("assistant", answer),
    ]
    assert all(m.run_id == run.run_id for m in messages)


async def test_session_reuse(repo, tool_chunks):
    service = init_agent_service(repo, FakeAgent(tool_chunks))
    session_id = await repo.create_session("agent", "已有会话")
    events = await collect(service, "10.0.0.1/8 的网络地址？", session_id)
    assert events[0].data["session_id"] == session_id
    assert len(await repo.list_sessions()) == 1
    assert len(await repo.list_messages(session_id)) == 2


async def test_exception_marks_failed_and_emits_error(repo):
    service = init_agent_service(
        repo, FakeAgent([("updates", {"model": {"messages": [tool_call_msg()]}})],
                        exc=RuntimeError("boom"))
    )
    events = await collect(service, "会出错的提问")

    assert [e.name for e in events] == ["meta", "step_start", "action", "error"]
    assert events[-1].data["message"] == "模型服务异常，请稍后重试"

    run = await repo.get_run(events[0].data["run_id"])
    assert run.status == "failed"
    assert run.steps_count == 1
    steps = await repo.get_run_steps(run.run_id)
    assert steps[-1].kind == "error"
    assert steps[-1].content == "模型服务异常，请稍后重试"
    # 失败时不落 assistant 消息
    assert [m.role for m in await repo.list_messages(events[0].data["session_id"])] == ["user"]


async def test_client_disconnect_marks_failed(repo, tool_chunks):
    service = init_agent_service(repo, FakeAgent(tool_chunks))
    # 在观察事件处停止消费，模拟客户端读到一半断开
    agen = service.stream_chat("中途断开的提问")
    names = []
    async for ev in agen:
        names.append(ev.name)
        if ev.name == "observation":
            break
    assert names == ["meta", "step_start", "thought", "action", "observation"]

    await agen.aclose()  # 模拟客户端断开：GeneratorExit 注入挂起点

    # 通过 session 反查 run：stream_chat 已创建会话
    sessions = await repo.list_sessions()
    assert len(sessions) == 1
    messages = await repo.list_messages(sessions[0].session_id)
    run_id = messages[0].run_id
    run = await repo.get_run(run_id)
    assert run.status == "failed"
    assert run.finished_at
    # 中途断开：步骤已落库，无 assistant 消息
    assert len(await repo.get_run_steps(run_id)) == 3
    assert [m.role for m in messages] == ["user"]


async def test_agent_not_ready(repo):
    service = init_agent_service(repo, None)
    with pytest.raises(RuntimeError):
        await collect(service, "任意问题")


async def test_replay_endpoint(repo, tool_chunks):
    init_agent_service(repo, FakeAgent(tool_chunks))
    events = await collect(get_agent_service(), "192.168.10.137/27 属于哪个子网？")
    session_id = events[0].data["session_id"]
    run_id = events[0].data["run_id"]

    resp = await get_session_run(session_id, run_id)
    assert resp["run"]["run_id"] == run_id
    assert resp["run"]["status"] == "success"
    assert resp["run"]["steps_count"] == 1
    assert resp["run"]["final_answer"].startswith("该地址属于")
    assert [s["kind"] for s in resp["steps"]] == ["thought", "action", "observation"]
    assert resp["steps"][1]["tool_name"] == "subnet_calculator"

    not_found = await get_session_run(session_id, "r_missing")
    assert not_found.status_code == 404
    # run 归属其他会话时同样 404，防止跨会话读取
    other = await get_session_run("s_other", run_id)
    assert other.status_code == 404
