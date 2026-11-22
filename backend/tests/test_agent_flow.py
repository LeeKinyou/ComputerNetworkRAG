"""Agent 执行链契约：事件落库、审批中断与恢复、失败收敛。

用内存库替换 `session_scope`，并用桩检索器隔离全局索引；强制关闭 LLM，
保证用例只验证确定性模板链路。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import agent
from app.models import Base, ChatSession, Message, Run, RunStep


class StubRetriever:
    ready = True
    vector_mode = "hash"
    embedder_label = "hash/256d"

    def search(self, query: str, top_k: int = 5, chapter_id: str | None = None,
               pool: int = 20, boost_chapters: set[str] | None = None) -> list[dict]:
        return [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "title": "网络层讲义",
                "locator": {"section_path": ["4.3 IPv4"], "page": None},
                "excerpt": "IPv4 地址由网络位与主机位组成，掩码决定边界。",
                "channels": ["bm25", "vector"],
                "score": 0.5,
            }
        ]

    async def refresh(self, session: AsyncSession) -> None:
        return None


@asynccontextmanager
async def agent_harness(
    monkeypatch: pytest.MonkeyPatch,
    runs: list[tuple[str, str, str]],
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    @asynccontextmanager
    async def session_scope():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(agent, "session_scope", session_scope)
    monkeypatch.setattr(agent, "retriever", StubRetriever())
    monkeypatch.setattr(agent, "agent_graph", agent.build_graph())
    monkeypatch.setattr(agent.settings, "llm_api_key", "")

    async with factory() as session:
        session.add(ChatSession(id="s1", course_id="course_cn", title="测试会话", user_key="u1"))
        for run_id, question, mode in runs:
            session.add(
                Run(id=run_id, session_id="s1", course_id="course_cn", user_key="u1",
                    question=question, mode=mode, status="queued")
            )
        await session.commit()

    try:
        yield factory
    finally:
        await engine.dispose()


async def steps_of(factory, run_id: str) -> list[RunStep]:
    async with factory() as session:
        return list(
            (
                await session.execute(
                    select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.seq)
                )
            ).scalars().all()
        )


async def test_emit_advances_sequence_and_persists_payload(monkeypatch):
    async with agent_harness(monkeypatch, [("r1", "问题", "agent")]) as factory:
        seq = await agent.emit("r1", "step_start", {"step": "analyze"})
        assert seq == 1

        steps = await steps_of(factory, "r1")
        assert len(steps) == 1
        assert steps[0].type == "step_start"
        assert steps[0].payload == {"step": "analyze", "run_id": "r1", "seq": 1}

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.latest_seq == 1


async def test_emit_ignores_unknown_run(monkeypatch):
    async with agent_harness(monkeypatch, []) as factory:
        assert await agent.emit("missing", "token", {"text": "x"}) == 0
        assert await steps_of(factory, "missing") == []


async def test_plain_run_completes_with_citations_and_history(monkeypatch):
    async with agent_harness(monkeypatch, [("r1", "ARP 是怎么工作的？", "agent")]) as factory:
        await agent.execute_run("r1")

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "completed"
            assert run.error_code is None
            assert "课程原文" in run.answer_markdown
            assert "IPv4 地址由网络位与主机位组成" in run.answer_markdown
            assert [item["chunk_id"] for item in run.citations] == ["c1"]
            assert run.cards == []
            assert run.pending_input is None

            messages = (await session.execute(select(Message))).scalars().all()
            assert [(m.role, bool(m.content)) for m in messages] == [("assistant", True)]

        steps = await steps_of(factory, "r1")
        types = [step.type for step in steps]
        assert types[0] == "step_start"
        assert "plan" in types
        assert "action" in types
        assert "observation" in types
        assert "token" in types
        assert types[-1] == "final"
        assert [step.seq for step in steps] == list(range(1, len(steps) + 1))


async def test_approval_run_waits_then_resume_completes(monkeypatch):
    async with agent_harness(monkeypatch, [("r1", "重建第 4 章索引", "agent")]) as factory:
        await agent.execute_run("r1")

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "waiting_user"
            pending = run.pending_input
            assert pending["kind"] == "approval"
            assert pending["input_id"].startswith("apv_")
            assert pending["tool_call_id"] == "reindex_course"
            assert len(pending["args_hash"]) == 16
            assert run.answer_markdown == ""

        types = [step.type for step in await steps_of(factory, "r1")]
        assert "input.required" in types
        assert "final" not in types

        await agent.execute_run("r1", resume={"approved": True})

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "completed"
            assert run.pending_input is None
            assert run.answer_markdown.startswith("已按你的确认执行索引重建")

        types = [step.type for step in await steps_of(factory, "r1")]
        assert types[-1] == "final"
        assert types.count("input.required") == 1


async def test_rejected_approval_cancels_without_token_stream(monkeypatch):
    async with agent_harness(monkeypatch, [("r1", "删除文档并重建索引", "agent")]) as factory:
        await agent.execute_run("r1")
        await agent.execute_run("r1", resume={"approved": False})

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "cancelled"
            assert run.pending_input is None
            assert "取消" in run.answer_markdown

        types = [step.type for step in await steps_of(factory, "r1")]
        assert "token" not in types
        assert types[-1] == "final"


async def test_cidr_question_produces_calculation_card(monkeypatch):
    async with agent_harness(monkeypatch, [("r1", "计算 192.168.10.137/27 的网络地址和可用主机数", "agent")]) as factory:
        await agent.execute_run("r1")

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "completed"
            assert len(run.cards) == 1
            card = run.cards[0]
            assert card["type"] == "calculation"
            assert card["data"]["network_address"] == "192.168.10.128"
            assert card["data"]["broadcast_address"] == "192.168.10.159"
            assert card["data"]["usable_host_count"] == 30
            assert card["data"]["block_size"] == 32
            assert any("主机位" in item for item in card["data"]["warnings"])
            assert "可用主机数：**30**" in run.answer_markdown

        types = [step.type for step in await steps_of(factory, "r1")]
        assert types.count("action") == 2  # 检索 + 子网计算
        assert types.count("observation") == 2


async def test_rag_mode_skips_tools_but_keeps_approval_flag_out(monkeypatch):
    async with agent_harness(monkeypatch, [("r1", "重建第 4 章索引并计算 10.0.0.0/26", "rag")]) as factory:
        await agent.execute_run("r1")

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "completed"
            assert run.cards == []
            assert run.pending_input is None

        types = [step.type for step in await steps_of(factory, "r1")]
        assert "input.required" not in types
        assert types.count("action") == 1  # 只检索，不计算


async def test_terminal_run_is_not_executed_again(monkeypatch):
    async with agent_harness(monkeypatch, [("r1", "已完成的问题", "agent")]) as factory:
        async with factory() as session:
            run = await session.get(Run, "r1")
            run.status = "completed"
            await session.commit()

        await agent.execute_run("r1")

        assert await steps_of(factory, "r1") == []


async def test_missing_run_is_a_noop(monkeypatch):
    async with agent_harness(monkeypatch, []) as factory:
        await agent.execute_run("missing")
        assert await steps_of(factory, "missing") == []


async def test_graph_exception_is_converted_to_failed_run(monkeypatch):
    class BrokenGraph:
        async def ainvoke(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("boom-detail")

    async with agent_harness(monkeypatch, [("r1", "随便问问", "agent")]) as factory:
        monkeypatch.setattr(agent, "agent_graph", BrokenGraph())
        await agent.execute_run("r1")

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "failed"
            assert run.error_code == "AGENT_FAILED"
            assert run.error_message == "boom-detail"
            assert run.pending_input is None

        steps = await steps_of(factory, "r1")
        assert steps[-1].type == "run.failed"
        assert steps[-1].payload["error_code"] == "AGENT_FAILED"
