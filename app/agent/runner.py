"""run_agent / resume_agent：把 create_agent 的 astream 映射为 04 §6.2 事件流。

token 采用按轮缓冲：工具轮的内容作为 thought 一次性下发，最终轮的内容以
token 事件逐个下发——无法在流中提前判断某轮是否为最终轮（tool_calls 只有
轮结束才可知），缓冲是唯一不重不漏的做法（03 §3.2 说明）。

审批中断（03 §3.4）：HumanInTheLoopMiddleware 的 after_model 是独立图节点，
对需审批工具在 model 更新（action 事件已发出）之后、tools 执行之前 interrupt，
astream 正常结束；流末尾查检查点待审批请求，发 interrupt 事件且不发 final，
run 停在 waiting_approval。续跑走 resume_agent：Command(resume=decisions)
重启同一 thread，事件从断点继续（step_no 以 run.steps_count 续接）。
"""

import json
from typing import AsyncIterator

from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from app.config import get_settings
from app.schemas import Event

REJECT_MESSAGE = "用户拒绝执行该操作，请改用其他方式回答，或向用户确认下一步。"


class NoPendingInterruptError(Exception):
    """run 不存在、不在等待审批，或检查点里没有待审批的工具调用。"""


def _content_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content or "")


def _parse_tool_message(tm) -> dict:
    """适配器信封 {status,elapsed_ms,output,structured} → observation 载荷。"""
    try:
        envelope = json.loads(tm.content)
    except (TypeError, ValueError):
        envelope = None
    if isinstance(envelope, dict) and "status" in envelope:
        return {
            "status": envelope.get("status") or "failed",
            "elapsed_ms": int(envelope.get("elapsed_ms") or 0),
            "result": envelope.get("output") or "",
            "structured": envelope.get("structured") or {},
        }
    return {
        "status": getattr(tm, "status", None) or "success",
        "elapsed_ms": 0,
        "result": str(tm.content or ""),
        "structured": {},
    }


def _cfg(run_id: str) -> dict:
    settings = get_settings()
    return {
        "configurable": {"thread_id": run_id},
        "recursion_limit": settings.AGENT_RECURSION_LIMIT,
    }


def _pending_interrupts(snapshot) -> list[dict]:
    """从检查点快照提取待审批请求（HumanInTheLoopMiddleware 的 HITLRequest）。"""
    requests: list[dict] = []
    for task in getattr(snapshot, "tasks", None) or ():
        for intr in getattr(task, "interrupts", None) or ():
            value = getattr(intr, "value", None)
            if isinstance(value, dict) and value.get("action_requests"):
                requests.extend(value["action_requests"])
    return requests


async def get_pending_interrupts(agent, run_id: str) -> list[dict]:
    return _pending_interrupts(await agent.aget_state(_cfg(run_id)))


def _decision(req: dict, decision: str, edited_args: dict | None) -> dict:
    """单条审批决策 → 中间件的 Decision 载荷（与 action_requests 对齐）。"""
    if decision == "approve":
        return {"type": "approve"}
    if decision == "edit":
        return {
            "type": "edit",
            "edited_action": {"name": req.get("name") or "", "args": dict(edited_args or {})},
        }
    return {"type": "reject", "message": REJECT_MESSAGE}


async def _map_stream(
    agen, agent, run_id: str, step_no_start: int = 0
) -> AsyncIterator[Event]:
    """astream → 事件映射（meta/resumed 之前的协议主体），末尾检测审批中断。"""
    cfg = _cfg(run_id)
    step_no = step_no_start
    answer_parts: list[str] = []
    turn_tokens: list[str] = []
    truncated = False

    try:
        async for mode, chunk in agen:
            if mode == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") == "model":
                    text = _content_text(msg)
                    if text:
                        turn_tokens.append(text)
                continue
            if mode != "updates":
                continue

            if "model" in chunk:
                ai = chunk["model"]["messages"][-1]
                content = _content_text(ai)
                tool_calls = list(ai.tool_calls or [])
                if tool_calls:
                    # step_start 只给工具轮：一轮 ReAct = 决策 + 行动 + 观察
                    # （04 §6.2 示例中最终回答轮不发 step_start，steps_count 数工具轮）
                    step_no += 1
                    yield Event(name="step_start", data={"step_no": step_no})
                    if content:
                        yield Event(
                            name="thought", data={"step_no": step_no, "content": content}
                        )
                    for tc in tool_calls:
                        yield Event(
                            name="action",
                            data={
                                "step_no": step_no,
                                "tool": tc.get("name") or "",
                                "args": tc.get("args") or {},
                            },
                        )
                else:
                    streamed = "".join(turn_tokens) or content
                    if streamed:
                        answer_parts.append(streamed)
                        if turn_tokens:
                            for delta in turn_tokens:
                                yield Event(name="token", data={"delta": delta})
                        else:
                            yield Event(name="token", data={"delta": streamed})
                turn_tokens.clear()
            elif "tools" in chunk:
                for tm in chunk["tools"]["messages"]:
                    yield Event(
                        name="observation",
                        data={"step_no": step_no, **_parse_tool_message(tm)},
                    )
    except GraphRecursionError:
        truncated = True

    requests = _pending_interrupts(await agent.aget_state(cfg))
    if requests:
        # 图停在 after_model：该轮 action 已发出，观察缺位，等待人工审批；
        # 正常关闭本流（不发 final），run 由服务层落 waiting_approval
        for req in requests:
            yield Event(
                name="interrupt",
                data={
                    "step_no": step_no,
                    "tool": req.get("name") or "",
                    "args": req.get("args") or {},
                },
            )
        return

    yield Event(
        name="final",
        data={
            "answer": "".join(answer_parts),
            "steps_count": step_no,
            "truncated": truncated,
        },
    )


async def run_agent(
    agent, question: str, run_id: str, session_id: str | None = None
) -> AsyncIterator[Event]:
    cfg = _cfg(run_id)
    meta = {"run_id": run_id}
    if session_id:
        meta["session_id"] = session_id
    yield Event(name="meta", data=meta)
    async for ev in _map_stream(
        agent.astream({"messages": [("user", question)]}, config=cfg, stream_mode=["updates", "messages"]),
        agent,
        run_id,
    ):
        yield ev


async def resume_agent(
    agent,
    run_id: str,
    decision: str,
    edited_args: dict | None = None,
    step_no_start: int = 0,
) -> AsyncIterator[Event]:
    """审批后续跑（04 §6.5）：新 SSE 流，首帧 resumed，事件接续原时间线。"""
    requests = await get_pending_interrupts(agent, run_id)
    if not requests:
        raise NoPendingInterruptError("检查点中没有待审批的工具调用")
    decisions = [_decision(req, decision, edited_args) for req in requests]
    yield Event(name="resumed", data={"run_id": run_id, "decision": decision})
    async for ev in _map_stream(
        agent.astream(
            Command(resume={"decisions": decisions}),
            config=_cfg(run_id),
            stream_mode=["updates", "messages"],
        ),
        agent,
        run_id,
        step_no_start=step_no_start,
    ):
        yield ev
