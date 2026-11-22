"""加固回归用例：覆盖 2026-11-21 验证报告里剩余的可修风险项。

- 上传按上限 +1 读取，不整包进内存；
- /search 对未知课程显式 404，不再静默跨课程召回；
- 章节归因优先 document_id，同名文档不串章节；
- 错题同错次时最近错的排前面；
- 新建 run 默认 rag，与统计口径一致；
- 取消优先：finalize 不得把 cancelled 覆盖成 completed。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta

from sqlalchemy import select

import app.agent as agent_mod
from app.api import RunCreate
from app.models import Attempt, ChatSession, Document, Message, Run
from app.seed import COURSE_ID
from app.util import utcnow
from _support import api_harness, memory_db, seed_course


async def test_upload_rejects_oversize_before_reading_all(monkeypatch):
    from app.api import settings

    async with api_harness() as (client, factory):
        await seed_course(factory)
        monkeypatch.setattr(settings, "max_upload_bytes", 10)
        response = await client.post(
            f"/api/v2/courses/{COURSE_ID}/documents",
            files={"file": ("big.txt", b"0123456789A", "text/plain")},
            data={"title": "超限文件"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_search_rejects_unknown_course():
    async with api_harness() as (client, factory):
        await seed_course(factory)

        ok = await client.post("/api/v2/search", json={"query": "ARP", "course_id": COURSE_ID})
        assert ok.status_code == 200

        bad = await client.post("/api/v2/search", json={"query": "ARP", "course_id": "course_other"})
        assert bad.status_code == 404
        assert bad.json()["error"]["code"] == "NOT_FOUND"


async def test_chapter_focus_uses_document_id_not_title():
    async with api_harness() as (client, factory):
        await seed_course(factory)
        async with factory() as session:
            session.add_all(
                [
                    Document(id="d1", course_id=COURSE_ID, chapter_id="ch1", title="同名讲义",
                             filename="a.md", mime="text/markdown", size=10, chunk_count=1),
                    Document(id="d2", course_id=COURSE_ID, chapter_id="ch2", title="同名讲义",
                             filename="b.md", mime="text/markdown", size=10, chunk_count=1),
                    ChatSession(id="s1", course_id=COURSE_ID, title="问答", user_key="demo_user"),
                    Run(id="r1", session_id="s1", course_id=COURSE_ID, user_key="demo_user",
                        question="子网怎么划？", mode="rag", status="completed",
                        citations=[{"chunk_id": "c2", "document_id": "d2", "title": "同名讲义", "score": 0.8}]),
                ]
            )
            await session.commit()

        response = await client.get("/api/v2/analytics/overview")
        assert response.status_code == 200
        focus = {item["label"]: item["value"] for item in response.json()["chapter_focus"]}
        # 标题相同，但 citation 指向 d2 → 只能记到第二章
        assert focus["网络层"] == 100
        assert focus["数据链路层"] == 0


async def test_wrongbook_same_wrong_count_prefers_most_recent():
    async with api_harness() as (client, factory):
        await seed_course(factory)
        now = utcnow()
        async with factory() as session:
            session.add_all(
                [
                    # q_dns 两错，但错得早
                    Attempt(id="w1", course_id=COURSE_ID, question_id="q_dns", user_key="demo_user",
                            chapter_id="ch1", answer="A", is_correct=False, created_at=now - timedelta(days=3)),
                    Attempt(id="w2", course_id=COURSE_ID, question_id="q_dns", user_key="demo_user",
                            chapter_id="ch1", answer="A", is_correct=False, created_at=now - timedelta(days=2)),
                    # q_arp 同样两错，最近一次在今天
                    Attempt(id="w3", course_id=COURSE_ID, question_id="q_arp", user_key="demo_user",
                            chapter_id="ch2", answer="A", is_correct=False, created_at=now - timedelta(days=2)),
                    Attempt(id="w4", course_id=COURSE_ID, question_id="q_arp", user_key="demo_user",
                            chapter_id="ch2", answer="A", is_correct=False, created_at=now - timedelta(hours=1)),
                ]
            )
            await session.commit()

        response = await client.get("/api/v2/practice/wrongbook", params={"user_key": "demo_user"})
        assert response.status_code == 200
        assert [item["question_id"] for item in response.json()["items"]] == ["q_arp", "q_dns"]


async def test_run_defaults_to_rag_mode():
    assert RunCreate(message="ARP 是什么？").mode == "rag"

    async with memory_db() as factory:
        async with factory() as session:
            session.add(ChatSession(id="s1", course_id=COURSE_ID, title="默认模式", user_key="demo_user"))
            session.add(Run(id="r1", session_id="s1", course_id=COURSE_ID, question="q"))
            await session.commit()
        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.mode == "rag"


async def test_finalize_does_not_override_cancelled(monkeypatch):
    async with memory_db() as factory:
        async with factory() as session:
            session.add(ChatSession(id="s1", course_id=COURSE_ID, title="取消竞态", user_key="demo_user"))
            session.add(Run(id="r1", session_id="s1", course_id=COURSE_ID, question="q", status="cancelled"))
            await session.commit()

        @asynccontextmanager
        async def _scope():
            async with factory() as session:
                yield session
                await session.commit()

        async def _noop_emit(*_args, **_kwargs):
            return None

        monkeypatch.setattr(agent_mod, "session_scope", _scope)
        monkeypatch.setattr(agent_mod, "emit", _noop_emit)

        await agent_mod.finalize_node(
            {"run_id": "r1", "status": "completed", "answer": "这是答案", "cards": [], "evidence": []}
        )

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "cancelled"
            assert not run.answer_markdown
            messages = (await session.execute(select(Message))).scalars().all()
            assert messages == []
