"""run_agent：把 create_agent 的 astream 映射为 04 §6.2 事件流。

token 采用按轮缓冲：工具轮的内容作为 thought 一次性下发，最终轮的内容以
token 事件逐个下发——无法在流中提前判断某轮是否为最终轮（tool_calls 只有
轮结束才可知），缓冲是唯一不重不漏的做法（03 §3.2 说明）。
"""

import json
from typing import AsyncIterator

from langgraph.errors import GraphRecursionError

from app.config import get_settings
from app.schemas import Event


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


async def run_agent(agent, question: str, run_id: str) -> AsyncIterator[Event]:
    settings = get_settings()
    cfg = {
        "configurable": {"thread_id": run_id},
        "recursion_limit": settings.AGENT_RECURSION_LIMIT,
    }
    yield Event(name="meta", data={"run_id": run_id})

    step_no = 0
    answer_parts: list[str] = []
    turn_tokens: list[str] = []
    truncated = False

    try:
        async for mode, chunk in agent.astream(
            {"messages": [("user", question)]},
            config=cfg,
            stream_mode=["updates", "messages"],
        ):
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

    yield Event(
        name="final",
        data={
            "answer": "".join(answer_parts),
            "steps_count": step_no,
            "truncated": truncated,
        },
    )
