"""读接口契约：学情聚合、推荐组卷、检索来源与题目下发。

数据全部在内存库中构造；检索接口使用独立 Retriever，避免复用进程内索引。
"""

from __future__ import annotations

import pytest

import app.db  # noqa: F401  先完成 db → seed 的初始化顺序
from app.config import settings
from app.models import (
    Attempt,
    Chapter,
    ChatSession,
    Chunk,
    Concept,
    Course,
    Document,
    Question,
    Run,
    RunStep,
)
from app.retrieval import Retriever
from app.seed import COURSE_ID
from app.util import utcnow
from _support import add_attempt, api_harness, ensure_course, seed_course


@pytest.fixture
def fresh_retriever(monkeypatch):
    retriever = Retriever()
    monkeypatch.setattr("app.api.retriever", retriever)
    return retriever


async def test_health_and_meta_report_real_counts(fresh_retriever):
    async with api_harness() as (client, factory):
        async with factory() as session:
            session.add(Course(id=COURSE_ID, title="计算机网络", description=""))
            session.add(Concept(id="c1", course_id=COURSE_ID, chapter_id="ch1", code="c1", title="OSI"))
            session.add(Document(id="d1", course_id=COURSE_ID, chapter_id="ch1", title="讲义",
                                 filename="a.md", mime="text/markdown", size=10, chunk_count=1))
            session.add(Chunk(id="ch1_1", document_id="d1", ordinal=0, section_path=[], text="正文"))
            await session.commit()

        health = await client.get("/api/v2/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["db_backend"] == settings.db_backend
        assert body["retriever_ready"] is False

        meta = await client.get("/api/v2/meta")
        assert meta.status_code == 200
        body = meta.json()
        assert body["course"] == {"id": COURSE_ID, "title": "计算机网络"}
        assert body["counts"] == {"concepts": 1, "documents": 1, "chunks": 1}
        assert len(body["demo_questions"]) == 4


async def test_recommended_puts_untried_first_then_weak(fresh_retriever):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await add_attempt(factory, attempt_id="a1", question_id="q_arp", chapter_id="ch2", correct=False)
        await add_attempt(factory, attempt_id="a2", question_id="q_arp", chapter_id="ch2", correct=False)
        await add_attempt(factory, attempt_id="a3", question_id="q_tcp", chapter_id="ch2", correct=True)
        await add_attempt(factory, attempt_id="a4", question_id="q_tcp", chapter_id="ch2", correct=True)

        response = await client.get("/api/v2/questions/recommended", params={"limit": 3})
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3

        # 未练过的概念优先（q_dns / q_mac），薄弱概念其次（q_arp），已掌握垫底
        assert {item["id"] for item in items[:2]} == {"q_dns", "q_mac"}
        assert items[2]["id"] == "q_arp"
        assert "正确率 0%" in items[2]["reason"]
        assert "优先巩固" in items[2]["reason"]


async def test_analytics_overview_aggregates_runs_steps_and_citations(fresh_retriever):
    async with api_harness() as (client, factory):
        now = utcnow()
        async with factory() as session:
            session.add(Course(id=COURSE_ID, title="计算机网络", description=""))
            session.add(ChatSession(id="s1", course_id=COURSE_ID, title="会话", user_key="demo_user"))
            session.add_all(
                [
                    Chapter(id="ch1", course_id=COURSE_ID, title="数据链路层", sort_order=1),
                    Chapter(id="ch2", course_id=COURSE_ID, title="网络层", sort_order=2),
                ]
            )
            session.add_all(
                [
                    Document(id="d1", course_id=COURSE_ID, chapter_id="ch1", title="链路层讲义",
                             filename="a.md", mime="text/markdown", size=10, chunk_count=2),
                    Document(id="d2", course_id=COURSE_ID, chapter_id="ch2", title="网络层讲义",
                             filename="b.md", mime="text/markdown", size=10, chunk_count=1),
                ]
            )
            session.add_all(
                [
                    Run(id="r1", session_id="s1", course_id=COURSE_ID, user_key="demo_user", question="ARP 如何工作？",
                        mode="rag", status="completed", citations=[{"title": "链路层讲义", "chunk_id": "a"},
                                                                   {"title": "链路层讲义", "chunk_id": "b"}],
                        created_at=now),
                    Run(id="r2", session_id="s1", course_id=COURSE_ID, user_key="demo_user", question="子网怎么划分？",
                        mode="agent", status="completed", citations=[{"title": "网络层讲义", "chunk_id": "c"}],
                        created_at=now),
                    Run(id="r3", session_id="s1", course_id=COURSE_ID, user_key="demo_user", question="失败的问题",
                        mode="agent", status="failed", created_at=now),
                    Run(id="r4", session_id="s1", course_id=COURSE_ID, user_key="demo_user", question="重建索引",
                        mode="agent", status="waiting_user", citations=[{"title": "链路层讲义", "chunk_id": "d"}],
                        created_at=now),
                ]
            )
            session.add_all(
                [
                    RunStep(id="st1", run_id="r1", seq=1, type="action", payload={}),
                    RunStep(id="st2", run_id="r1", seq=2, type="action", payload={}),
                    RunStep(id="st3", run_id="r2", seq=1, type="final", payload={}),
                ]
            )
            await session.commit()

        response = await client.get("/api/v2/analytics/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["questions"] == 4
        assert body["questions_week"] == 4
        assert body["questions_month"] == 4
        assert body["pending_approvals"] == 1
        assert body["tool_calls"] == 2
        assert body["completion_rate"] == 50
        assert body["mode_split"] == {"rag": 1, "agent": 3}
        assert len(body["daily"]) == 14
        assert body["chapter_focus"] == [
            {"label": "数据链路层", "value": 75},
            {"label": "网络层", "value": 25},
        ]
        assert body["top_documents"] == [
            {"title": "链路层讲义", "count": 3},
            {"title": "网络层讲义", "count": 1},
        ]
        assert body["documents"] == {"count": 2, "chunks": 3}


async def test_analytics_concepts_counts_weak_students(fresh_retriever):
    async with api_harness() as (client, factory):
        async with factory() as session:
            session.add(Course(id=COURSE_ID, title="计算机网络", description=""))
            session.add_all(
                [
                    Concept(id="c1", course_id=COURSE_ID, chapter_id="ch1", code="c1", title="ARP", sort_order=1),
                    Concept(id="c2", course_id=COURSE_ID, chapter_id="ch1", code="c2", title="DNS", sort_order=2),
                    Question(id="q1", course_id=COURSE_ID, chapter_id="ch1", concept_id="c1", type="single",
                             stem="Q1", answer="A", sort_order=1),
                    Question(id="q2", course_id=COURSE_ID, chapter_id="ch1", concept_id="c1", type="single",
                             stem="Q2", answer="A", sort_order=2),
                    Question(id="q3", course_id=COURSE_ID, chapter_id="ch1", concept_id="c2", type="single",
                             stem="Q3", answer="A", sort_order=3),
                ]
            )
            session.add_all(
                [
                    Attempt(id="x1", course_id=COURSE_ID, question_id="q1", user_key="stu_a",
                            chapter_id="ch1", answer="B", is_correct=False),
                    Attempt(id="x2", course_id=COURSE_ID, question_id="q2", user_key="stu_a",
                            chapter_id="ch1", answer="B", is_correct=False),
                    Attempt(id="x3", course_id=COURSE_ID, question_id="q1", user_key="stu_b",
                            chapter_id="ch1", answer="A", is_correct=True),
                    Attempt(id="x4", course_id=COURSE_ID, question_id="q2", user_key="stu_b",
                            chapter_id="ch1", answer="A", is_correct=True),
                    Attempt(id="x5", course_id=COURSE_ID, question_id="q3", user_key="stu_b",
                            chapter_id="ch1", answer="A", is_correct=True),
                ]
            )
            await session.commit()

        response = await client.get("/api/v2/analytics/concepts")
        assert response.status_code == 200
        body = response.json()
        assert body["total_concepts"] == 2
        assert body["covered_concepts"] == 2
        first = body["items"][0]
        assert first["concept_id"] == "c1"
        assert (first["attempts"], first["correct"], first["rate"], first["state"]) == (4, 2, 50, "weak")
        assert (first["students"], first["weak_students"]) == (2, 1)
        second = body["items"][1]
        assert (second["concept_id"], second["rate"], second["state"], second["weak_students"]) == ("c2", 100, "mastered", 0)

        scoped = await client.get("/api/v2/analytics/concepts", params={"user_key": "stu_a"})
        assert scoped.json()["items"][0]["attempts"] == 2
        assert scoped.json()["items"][0]["rate"] == 0
        assert scoped.json()["items"][0]["students"] == 1


async def test_practice_stats_groups_by_chapter_and_wrong_questions(fresh_retriever):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await add_attempt(factory, attempt_id="a1", question_id="q_arp", chapter_id="ch2", correct=False)
        await add_attempt(factory, attempt_id="a2", question_id="q_arp", chapter_id="ch2", correct=False)
        await add_attempt(factory, attempt_id="a3", question_id="q_dns", chapter_id="ch1", correct=True)

        body = (await client.get("/api/v2/practice/stats")).json()
        assert (body["total"], body["correct"], body["rate"]) == (3, 1, 33)
        assert [row["chapter_id"] for row in body["by_chapter"]] == ["ch2", "ch1"]
        assert body["by_chapter"][0]["label"] == "网络层"
        assert body["wrong_questions"] == [
            {"question_id": "q_arp", "stem": "ARP 的作用是什么？", "chapter_id": "ch2", "wrong_count": 2}
        ]


async def test_search_and_source_detail_use_local_index(fresh_retriever):
    async with api_harness() as (client, factory):
        await ensure_course(factory)
        async with factory() as session:
            session.add(Document(id="d1", course_id=COURSE_ID, chapter_id="ch2", title="网络层讲义",
                                 filename="a.md", mime="text/markdown", size=10, status="ready", chunk_count=2))
            session.add_all(
                [
                    Chunk(id="c1", document_id="d1", ordinal=0, section_path=["4.3"], text="IPv4 地址由网络位与主机位组成。"),
                    Chunk(id="c2", document_id="d1", ordinal=1, section_path=["4.4"], text="子网掩码与地址按位与得到网络地址。"),
                ]
            )
            await session.commit()

        search = await client.post("/api/v2/search", json={"query": "网络地址", "top_k": 2})
        assert search.status_code == 200
        items = search.json()["items"]
        assert {item["chunk_id"] for item in items} == {"c1", "c2"}

        detail = await client.get("/api/v2/sources/c2")
        assert detail.status_code == 200
        body = detail.json()
        assert body["chunk_id"] == "c2"
        assert body["locator"] == {"section_path": ["4.4"], "page": None}
        assert [item["chunk_id"] for item in body["neighbors"]] == ["c1", "c2"]

        missing = await client.get("/api/v2/sources/missing")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "NOT_FOUND"


async def test_concept_detail_returns_sources_and_404(fresh_retriever):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        async with factory() as session:
            session.add(Document(id="d1", course_id=COURSE_ID, chapter_id="ch2", title="网络层讲义",
                                 filename="a.md", mime="text/markdown", size=10, status="ready", chunk_count=1))
            session.add(Chunk(id="c1", document_id="d1", ordinal=0, section_path=[], text="ARP 在同一局域网解析 MAC 地址。"))
            await session.commit()

        await client.post("/api/v2/search", json={"query": "ARP", "top_k": 2})
        detail = await client.get("/api/v2/concepts/c_arp")
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == "c_arp"
        assert body["title"] == "ARP"
        assert [edge["source"] for edge in body["edges"]] == ["c_mac"]
        assert len(body["sources"]) <= 2

        missing = await client.get("/api/v2/concepts/c_missing")
        assert missing.status_code == 404


async def test_questions_do_not_leak_answers_and_respect_question_ids(fresh_retriever):
    async with api_harness() as (client, factory):
        await seed_course(factory)

        response = await client.get("/api/v2/questions", params={"limit": 4})
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert "answer" not in item
            assert "explanation" not in item

        scoped = await client.get(
            "/api/v2/questions",
            params={"question_ids": "q_dns,q_arp", "limit": 2, "shuffle": False},
        )
        ids = [item["id"] for item in scoped.json()["items"]]
        assert ids == ["q_dns", "q_arp"], "错题重做按传入顺序组卷"
