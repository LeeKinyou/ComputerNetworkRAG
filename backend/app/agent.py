"""辅导 Agent：LangGraph 状态图 + 工具调用 + 人工审批中断。

设计取舍：
- 用 StateGraph 承载固定阶段（分析 → 检索 → 计算 → 审批 → 组织 → 落库），
  每个阶段都可单独观测，演示时轨迹稳定；
- 审批用 `interrupt()`，恢复用 `Command(resume=...)`，thread_id 即 run_id；
- 未配置 LLM Key 时用确定性模板组织答案，配置后由模型润色，链路不变。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.config import settings
from app.db import session_scope
from app.models import ChatSession, Message, Run, RunStep
from app.retrieval import retriever
from app.tools import subnet
from app.util import new_id

IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})(?:\s*/\s*(\d{1,2}))?")
WRITE_INTENT_RE = re.compile(r"(重建.{0,8}索引|重新索引|导入文档|发布索引|批量导入|删除文档|覆盖索引)")

TERMINAL = {"completed", "failed", "cancelled", "partial"}


class TutorState(TypedDict, total=False):
    run_id: str
    session_id: str
    course_id: str
    question: str
    mode: str
    needs_approval: bool
    plan: list[dict]
    evidence: list[dict]
    cards: list[dict]
    answer: str
    status: str
    approval: str


async def emit(run_id: str, event_type: str, payload: dict) -> int:
    """写入一条持久事件并推进 run.latest_seq，SSE 连接靠轮询补齐。"""
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return 0
        seq = (run.latest_seq or 0) + 1
        run.latest_seq = seq
        session.add(
            RunStep(
                id=new_id(),
                run_id=run_id,
                seq=seq,
                type=event_type,
                payload={**payload, "run_id": run_id, "seq": seq},
            )
        )
        return seq


async def _set_status(run_id: str, status: str, **fields: Any) -> None:
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.status = status
        for key, value in fields.items():
            setattr(run, key, value)


def _plan(question: str, needs_approval: bool, mode: str = "agent") -> list[dict]:
    steps = [
        {"key": "understand", "goal": "理解问题并确定需要的课程范围"},
        {"key": "retrieve", "goal": "检索课程文档中的相关片段"},
    ]
    if mode != "rag":
        if IP_RE.search(question):
            steps.append({"key": "calculate", "goal": "按前缀计算网络地址、广播地址与可用主机数"})
        if needs_approval:
            steps.append({"key": "approval", "goal": "写操作需要人工确认后执行"})
    steps.append({"key": "compose", "goal": "组织回答并标注引用来源"})
    return steps


async def analyze_node(state: TutorState) -> dict:
    question = state["question"]
    mode = "rag" if str(state.get("mode") or "") == "rag" else "agent"
    needs_approval = bool(WRITE_INTENT_RE.search(question))
    plan = _plan(question, needs_approval, mode)
    await emit(
        state["run_id"],
        "step_start",
        {
            "step": "analyze",
            "title": "理解问题",
            "detail": (
                f"检索增强模式：{len(plan)} 个步骤"
                if mode == "rag"
                else f"智能体模式：识别到 {len(plan)} 个步骤"
                + ("，包含写操作" if needs_approval else "")
            ),
        },
    )
    await emit(
        state["run_id"],
        "plan",
        {"items": [{"id": item["key"], "goal": item["goal"], "status": "pending"} for item in plan]},
    )
    return {"needs_approval": needs_approval, "plan": plan}


async def retrieve_node(state: TutorState) -> dict:
    started = time.perf_counter()
    await emit(
        state["run_id"],
        "action",
        {"tool": "search_course", "input": {"query": state["question"], "top_k": 4}},
    )
    if not retriever.ready:
        async with session_scope() as session:
            await retriever.refresh(session)
    evidence = retriever.search(state["question"], top_k=4)
    elapsed = int((time.perf_counter() - started) * 1000)
    await emit(
        state["run_id"],
        "observation",
        {
            "tool": "search_course",
            "status": "ok" if evidence else "empty",
            "elapsed_ms": elapsed,
            "count": len(evidence),
            "summary": f"命中 {len(evidence)} 个课程片段" if evidence else "没有命中课程片段",
        },
    )
    return {"evidence": evidence}


async def calculate_node(state: TutorState) -> dict:
    match = IP_RE.search(state["question"])
    if not match:
        return {"cards": []}
    ip, prefix_text = match.group(1), match.group(2)
    prefix = int(prefix_text) if prefix_text else 24
    await emit(
        state["run_id"],
        "action",
        {"tool": "subnet", "input": {"ip": ip, "prefix": prefix, "address_policy": "traditional_lan"}},
    )
    result = subnet(ip, prefix, "traditional_lan")
    elapsed = result.elapsed_ms
    if result.status != "ok":
        await emit(
            state["run_id"],
            "observation",
            {"tool": "subnet", "status": result.status, "elapsed_ms": elapsed, "error_code": result.error_code},
        )
        return {"cards": []}
    data = result.data
    await emit(
        state["run_id"],
        "observation",
        {
            "tool": "subnet",
            "status": "ok",
            "elapsed_ms": elapsed,
            "summary": f"网络 {data['network_address']}，可用 {data['usable_host_count']} 个主机",
        },
    )
    cards = [
        {
            "type": "calculation",
            "tool": "subnet",
            "title": f"/{prefix} 子网计算",
            "data": data,
        }
    ]
    return {"cards": cards}


async def approval_node(state: TutorState) -> dict:
    if not state.get("needs_approval"):
        return {}
    run_id = state["run_id"]
    input_id = f"apv_{hashlib.sha1(run_id.encode()).hexdigest()[:10]}"
    prompt = "该请求会修改课程索引，需要你确认后执行。"
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        first_time = run is not None and run.pending_input is None
    if first_time:
        pending = {
            "input_id": input_id,
            "kind": "approval",
            "prompt": prompt,
            "tool_call_id": "reindex_course",
            "args_hash": hashlib.sha1(json.dumps({"course_id": state["course_id"]}, sort_keys=True).encode()).hexdigest()[:16],
        }
        await _set_status(run_id, "waiting_user", pending_input=pending)
        await emit(run_id, "input.required", {"pending_input": pending})

    decision = interrupt(
        {
            "input_id": input_id,
            "kind": "approval",
            "prompt": prompt,
            "approve_label": "批准并继续",
            "reject_label": "取消操作",
        }
    )
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else False
    await emit(
        run_id,
        "resumed",
        {"input_id": input_id, "approved": approved},
    )
    if not approved:
        return {"status": "cancelled", "answer": "已按你的选择取消这次索引修改，课程内容保持不变。"}
    return {"approval": "approved"}


async def compose_node(state: TutorState) -> dict:
    if state.get("status") == "cancelled":
        return {}
    question = state["question"]
    evidence = state.get("evidence", [])
    cards = state.get("cards", [])

    parts: list[str] = []
    if cards:
        data = cards[0]["data"]
        parts.append(
            f"**{question.strip()}**\n\n"
            f"- 网络地址：`{data['network_address']}`\n"
            f"- 广播地址：`{data['broadcast_address']}`\n"
            f"- 可用主机范围：`{data['first_host']}` – `{data['last_host']}`\n"
            f"- 可用主机数：**{data['usable_host_count']}**（块大小 {data['block_size']}）\n"
            f"- 掩码：`{data['mask']}`，地址约定：{data['address_policy']}"
        )
        if data["warnings"]:
            parts.append("注意：" + "；".join(data["warnings"]))
    if evidence:
        excerpts = "\n".join(
            f"> {item['excerpt'].strip()[:180]}\n>\n> — {item['title']} · {' / '.join(item['locator']['section_path']) or '正文'}"
            for item in evidence[:2]
        )
        parts.append(f"课程原文：\n\n{excerpts}")
    if not parts:
        parts.append(
            "这个问题暂时没有命中课程原文。可以换个说法，或先把相关章节文档加入知识库；"
            "我也可以按计算机网络的一般定义回答，但不会标注课程引用。"
        )
    answer = "\n\n".join(parts)
    approval = state.get("approval")
    if approval == "approved":
        answer = (
            "已按你的确认执行索引重建（演示环境只记录审批结果，不实际改写课程索引）。\n\n" + answer
        )
    if settings.llm_ready:
        answer = await _polish_with_model(question, evidence, answer)
    return {"answer": answer}


async def _polish_with_model(question: str, evidence: list[dict], fallback: str) -> str:
    """有 Key 时用模型改写；失败不阻塞主流程。"""
    try:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0.2,
            timeout=30,
        )
        context = "\n".join(item["excerpt"] for item in evidence[:3])
        prompt = (
            "你是计算机网络课程助教。基于给定课程片段回答问题，保持中文、简洁、不要编造引用。\n"
            f"问题：{question}\n课程片段：\n{context}\n\n已有草稿（可改写）：\n{fallback}"
        )
        response = await model.ainvoke(prompt)
        text = response.content if isinstance(response.content, str) else fallback
        return text.strip() or fallback
    except Exception:
        return fallback


async def finalize_node(state: TutorState) -> dict:
    run_id = state["run_id"]
    status = state.get("status", "completed")
    answer = state.get("answer", "")
    cards = state.get("cards", [])
    citations = state.get("evidence", [])
    if status != "cancelled":
        for index in range(0, len(answer), 24):
            await emit(run_id, "token", {"text": answer[index : index + 24]})
            await asyncio.sleep(0.02)
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return {}
        run.answer_markdown = answer
        run.cards = cards
        run.citations = citations
        run.status = status
        run.pending_input = None
        session.add(
            Message(
                id=new_id(),
                session_id=run.session_id,
                role="assistant",
                content=answer,
            )
        )
    await emit(
        run_id,
        "final",
        {"status": status, "answer_markdown": answer, "cards": cards, "citations": citations},
    )
    return {}


def build_graph(checkpointer: Any | None = None):
    builder = StateGraph(TutorState)
    builder.add_node("analyze", analyze_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("calculate", calculate_node)
    builder.add_node("approval", approval_node)
    builder.add_node("compose", compose_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        lambda state: "compose" if str(state.get("mode") or "") == "rag" else "calculate",
        {"calculate": "calculate", "compose": "compose"},
    )
    builder.add_edge("calculate", "approval")
    builder.add_edge("approval", "compose")
    builder.add_edge("compose", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


agent_graph = build_graph()


def bind_checkpointer(checkpointer: Any) -> None:
    """由应用 lifespan 注入持久化检查点，替代进程内存储。"""
    global agent_graph
    agent_graph = build_graph(checkpointer)


async def execute_run(run_id: str, resume: dict | None = None) -> None:
    """执行或恢复一次 run。所有异常收敛为 run.failed，不向 SSE 抛堆栈。"""
    try:
        async with session_scope() as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            if run.status in TERMINAL:
                return
            run.status = "running"

        config = {"configurable": {"thread_id": run_id}}
        if resume is not None:
            await emit(run_id, "resumed", {"decision": resume})
            await agent_graph.ainvoke(Command(resume=resume), config=config)
        else:
            async with session_scope() as session:
                run = await session.get(Run, run_id)
                if run is None:
                    return
                payload: dict[str, Any] = {
                    "run_id": run.id,
                    "session_id": run.session_id,
                    "course_id": run.course_id,
                    "question": run.question,
                    "mode": run.mode,
                }
            await agent_graph.ainvoke(payload, config=config)
    except Exception as exc:  # noqa: BLE001 - 对外只暴露安全错误码
        await emit(run_id, "run.failed", {"error_code": "AGENT_FAILED", "message": "运行失败，请重试"})
        await _set_status(
            run_id,
            "failed",
            error_code="AGENT_FAILED",
            error_message=str(exc)[:200],
            pending_input=None,
        )


async def start_run(run_id: str) -> None:
    asyncio.create_task(execute_run(run_id))
