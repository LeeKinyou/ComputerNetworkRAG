"""只读接口的契约测试：学习计划、错题本、待审批、文档引用命中。

每个用例都在独立的内存库里跑，不碰 runtime/app.db：
- 表结构用 SQLAlchemy metadata 建，数据由用例自行构造；
- 通过 dependency_overrides 替换 get_session，接口读到的是临时库。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Base, Attempt, Chapter, ChatSession, Concept, ConceptEdge, Course, Document, Question, Run
from app.seed import COURSE_ID
from app.util import utcnow


@pytest.fixture
async def api():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory

    app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


async def seed_course(factory):
    """建一个课程骨架：两章四概念，mac → arp 是先修关系。"""
    async with factory() as session:
        session.add(Course(id=COURSE_ID, title="计算机网络", description=""))
        session.add_all(
            [
                Chapter(id="ch1", course_id=COURSE_ID, title="数据链路层", sort_order=1),
                Chapter(id="ch2", course_id=COURSE_ID, title="网络层", sort_order=2),
            ]
        )
        session.add_all(
            [
                Concept(id="c_mac", course_id=COURSE_ID, chapter_id="ch1", code="mac", title="MAC 地址", sort_order=1),
                Concept(id="c_dns", course_id=COURSE_ID, chapter_id="ch1", code="dns", title="DNS", sort_order=2),
                Concept(id="c_arp", course_id=COURSE_ID, chapter_id="ch2", code="arp", title="ARP", sort_order=1),
                Concept(id="c_tcp", course_id=COURSE_ID, chapter_id="ch2", code="tcp", title="TCP", sort_order=2),
            ]
        )
        session.add(
            ConceptEdge(id="e1", course_id=COURSE_ID, source_id="c_mac", target_id="c_arp", kind="prerequisite")
        )
        session.add_all(
            [
                Question(id="q_arp", course_id=COURSE_ID, chapter_id="ch2", concept_id="c_arp", type="single",
                         stem="ARP 的作用是什么？", answer="B"),
                Question(id="q_tcp", course_id=COURSE_ID, chapter_id="ch2", concept_id="c_tcp", type="single",
                         stem="三次握手的第二个报文是什么？", answer="A"),
                Question(id="q_dns", course_id=COURSE_ID, chapter_id="ch1", concept_id="c_dns", type="single",
                         stem="DNS 默认使用哪个端口？", answer="C"),
            ]
        )
        await session.commit()


T0 = utcnow() - timedelta(days=2)


async def seed_attempt(factory, *, attempt_id, question_id, correct, offset_minutes):
    async with factory() as session:
        session.add(
            Attempt(
                id=attempt_id,
                course_id=COURSE_ID,
                question_id=question_id,
                user_key="demo_user",
                chapter_id="ch2",
                answer="A",
                is_correct=correct,
                created_at=T0 + timedelta(minutes=offset_minutes),
            )
        )
        await session.commit()


async def test_learning_next_puts_prerequisite_first_within_limit(api):
    client, factory = api
    await seed_course(factory)
    # ARP 三题全错（weak），TCP 一题对一题错（normal），DNS 一题对（mastered），MAC 没练过（no_data）
    for index in range(3):
        await seed_attempt(factory, attempt_id=f"a_arp_{index}", question_id="q_arp", correct=False, offset_minutes=index * 5)
    await seed_attempt(factory, attempt_id="a_tcp_ok", question_id="q_tcp", correct=True, offset_minutes=20)
    await seed_attempt(factory, attempt_id="a_tcp_bad", question_id="q_tcp", correct=False, offset_minutes=25)
    await seed_attempt(factory, attempt_id="a_dns_ok", question_id="q_dns", correct=True, offset_minutes=30)

    response = await client.get("/api/v2/learning/next", params={"user_key": "demo_user", "limit": 2})
    assert response.status_code == 200
    data = response.json()

    # 总数按全量明细统计，不是画像注入上限
    assert data["summary"] == {
        "weak": 2,
        "untried": 1,
        "mastered": 1,
        "covered": 3,
        "accuracy": 33,
        "total": 4,
    }
    # 先修没掌握时排在 ARP 前面；limit=2 时必须严格收口，不能溢出成 3 条
    assert [task["concept_id"] for task in data["tasks"]] == ["c_mac", "c_arp"]
    assert data["tasks"][0]["state"] == "no_data"
    assert data["tasks"][0]["action"] == "learn"
    assert "先修" in data["tasks"][0]["reason"]
    assert data["tasks"][1]["action"] == "review"
    assert data["recent_attempts"] == 6


async def test_wrongbook_keeps_only_questions_still_wrong(api):
    client, factory = api
    await seed_course(factory)
    # q_arp 先错后对（已纠正），q_tcp 连错两次（仍待复习）
    await seed_attempt(factory, attempt_id="a1", question_id="q_arp", correct=False, offset_minutes=0)
    await seed_attempt(factory, attempt_id="a2", question_id="q_arp", correct=True, offset_minutes=10)
    await seed_attempt(factory, attempt_id="a3", question_id="q_tcp", correct=False, offset_minutes=20)
    await seed_attempt(factory, attempt_id="a4", question_id="q_tcp", correct=False, offset_minutes=30)

    response = await client.get("/api/v2/practice/wrongbook", params={"user_key": "demo_user"})
    assert response.status_code == 200
    data = response.json()

    assert data["unresolved"] == 1
    assert data["solved"] == 1
    assert data["concepts_affected"] == 1
    assert [item["question_id"] for item in data["items"]] == ["q_tcp"]
    assert data["items"][0]["wrong"] == 2
    assert data["items"][0]["attempts"] == 2
    assert data["groups"][0]["title"] == "TCP"


async def test_runs_pending_route_is_not_swallowed_by_run_id(api):
    client, factory = api
    async with factory() as session:
        session.add_all(
            [
                ChatSession(id="s_demo", course_id=COURSE_ID, title="冒烟会话", user_key="demo_user"),
                ChatSession(id="s_lin", course_id=COURSE_ID, title="林晓的会话", user_key="stu_lin"),
            ]
        )
        session.add_all(
            [
                Run(id="r_new", session_id="s_demo", course_id=COURSE_ID, user_key="demo_user", question="重建第 5 章索引",
                    status="waiting_user", pending_input={"input_id": "apv_1", "kind": "approval"}, created_at=utcnow()),
                Run(id="r_old", session_id="s_demo", course_id=COURSE_ID, user_key="demo_user", question="重建第 6 章索引",
                    status="waiting_user", pending_input={"input_id": "apv_2", "kind": "approval"},
                    created_at=utcnow() - timedelta(minutes=30)),
                Run(id="r_lin", session_id="s_lin", course_id=COURSE_ID, user_key="stu_lin", question="别人的审批",
                    status="waiting_user", pending_input={"input_id": "apv_3"}, created_at=utcnow()),
                Run(id="r_done", session_id="s_demo", course_id=COURSE_ID, user_key="demo_user", question="已完成",
                    status="completed", created_at=utcnow()),
            ]
        )
        await session.commit()

    response = await client.get("/api/v2/runs/pending", params={"user_key": "demo_user"})
    assert response.status_code == 200
    data = response.json()

    # 路由顺序回归：如果 /runs/{run_id} 先注册，这里会变成 404
    assert data["total"] == 2
    assert [item["run_id"] for item in data["items"]] == ["r_new", "r_old"]
    assert data["items"][0]["session_title"] == "冒烟会话"
    assert data["items"][0]["pending_input"]["input_id"] == "apv_1"


async def test_document_citations_count_runs_chunks_and_dedupe_questions(api):
    client, factory = api
    now = utcnow()
    async with factory() as session:
        session.add(ChatSession(id="s1", course_id=COURSE_ID, title="问答", user_key="demo_user"))
        session.add(Document(id="d1", course_id=COURSE_ID, chapter_id="ch2", title="网络层讲义",
                             filename="net.md", mime="text/markdown", size=1200, chunk_count=2))
        citations_a = [
            {"chunk_id": "ch_a", "document_id": "d1", "title": "网络层讲义", "score": 0.9},
            {"chunk_id": "ch_b", "document_id": "d1", "title": "网络层讲义", "score": 0.4},
        ]
        session.add_all(
            [
                Run(id="r1", session_id="s1", course_id=COURSE_ID, user_key="demo_user",
                    question="ARP 如何工作？", status="completed", citations=citations_a,
                    created_at=now - timedelta(hours=3)),
                Run(id="r2", session_id="s1", course_id=COURSE_ID, user_key="demo_user",
                    question="子网如何划分？", status="completed",
                    citations=[{"chunk_id": "ch_a", "document_id": "d1", "title": "网络层讲义", "score": 0.8}],
                    created_at=now - timedelta(hours=2)),
                # 同一问题又问了一次：计入 run_total，但展示列表里去重
                Run(id="r3", session_id="s1", course_id=COURSE_ID, user_key="demo_user",
                    question="ARP 如何工作？", status="completed",
                    citations=[{"chunk_id": "ch_a", "document_id": "d1", "title": "网络层讲义", "score": 0.7}],
                    created_at=now - timedelta(hours=1)),
                # 失败运行不算被引用
                Run(id="r4", session_id="s1", course_id=COURSE_ID, user_key="demo_user",
                    question="失败的问题", status="failed",
                    citations=[{"chunk_id": "ch_a", "document_id": "d1", "title": "网络层讲义", "score": 0.1}],
                    created_at=now),
            ]
        )
        await session.commit()

    response = await client.get("/api/v2/documents/d1/citations", params={"limit": 3})
    assert response.status_code == 200
    data = response.json()

    assert data["run_total"] == 3
    assert data["chunk_total"] == 2
    assert data["chunk_counts"] == {"ch_a": 3, "ch_b": 1}
    assert [item["question"] for item in data["items"]] == ["ARP 如何工作？", "子网如何划分？"]
    assert data["items"][0]["hit_chunks"] == 1

    # 列表接口与详情同一口径：三个成功运行的提问
    listing = await client.get("/api/v2/courses/course_cn/documents")
    assert listing.status_code == 200
    doc = listing.json()["items"][0]
    assert doc["id"] == "d1"
    assert doc["citation_count"] == 3


async def test_questions_can_be_scoped_to_given_ids(api):
    client, factory = api
    await seed_course(factory)

    response = await client.get(
        "/api/v2/questions",
        params={"question_ids": "q_arp,q_dns", "limit": 3, "shuffle": False},
    )
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {"q_arp", "q_dns"}

    # 不存在的 id 会被库里过滤掉，只剩真实题目
    response = await client.get("/api/v2/questions", params={"question_ids": "q_arp,missing", "limit": 3})
    assert [item["id"] for item in response.json()["items"]] == ["q_arp"]


async def test_analytics_students_aggregates_per_user(api):
    client, factory = api
    await seed_course(factory)
    now = utcnow()
    async with factory() as session:
        session.add_all(
            [
                # demo：同一题做两次（题数去重后 1），一对一错
                Attempt(id="s1", course_id=COURSE_ID, question_id="q_arp", user_key="demo_user",
                        chapter_id="ch2", answer="A", is_correct=True, created_at=now - timedelta(hours=1)),
                Attempt(id="s2", course_id=COURSE_ID, question_id="q_arp", user_key="demo_user",
                        chapter_id="ch2", answer="A", is_correct=False, created_at=now - timedelta(hours=2)),
                # lin：三题全错
                Attempt(id="s3", course_id=COURSE_ID, question_id="q_tcp", user_key="stu_lin",
                        chapter_id="ch2", answer="A", is_correct=False, created_at=now - timedelta(hours=3)),
                Attempt(id="s4", course_id=COURSE_ID, question_id="q_dns", user_key="stu_lin",
                        chapter_id="ch1", answer="A", is_correct=False, created_at=now - timedelta(hours=4)),
                Attempt(id="s5", course_id=COURSE_ID, question_id="q_arp", user_key="stu_lin",
                        chapter_id="ch2", answer="A", is_correct=False, created_at=now - timedelta(hours=5)),
            ]
        )
        await session.commit()

    response = await client.get("/api/v2/analytics/students", params={"course_id": COURSE_ID})
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert [item["user_key"] for item in data["items"]] == ["stu_lin", "demo_user"]
    assert data["items"][0]["attempts"] == 3
    assert data["items"][0]["rate"] == 0
    assert data["items"][0]["questions"] == 3
    assert data["items"][1]["attempts"] == 2
    assert data["items"][1]["rate"] == 50
    assert data["items"][1]["questions"] == 1


async def test_learning_trend_splits_this_week_and_last_week(api):
    client, factory = api
    await seed_course(factory)
    now = utcnow()
    async with factory() as session:
        session.add_all(
            [
                # 本周（近 7 天）：一对一错 → 50%
                Attempt(id="t1", course_id=COURSE_ID, question_id="q_arp", user_key="demo_user",
                        chapter_id="ch2", answer="A", is_correct=True, created_at=now - timedelta(days=2)),
                Attempt(id="t2", course_id=COURSE_ID, question_id="q_tcp", user_key="demo_user",
                        chapter_id="ch2", answer="A", is_correct=False, created_at=now - timedelta(days=3)),
                # 上周（7~13 天前）：两题全对 → 100%
                Attempt(id="t3", course_id=COURSE_ID, question_id="q_dns", user_key="demo_user",
                        chapter_id="ch1", answer="A", is_correct=True, created_at=now - timedelta(days=8)),
                Attempt(id="t4", course_id=COURSE_ID, question_id="q_arp", user_key="demo_user",
                        chapter_id="ch2", answer="A", is_correct=True, created_at=now - timedelta(days=11)),
                # 超出 14 天窗口，不应计入
                Attempt(id="t5", course_id=COURSE_ID, question_id="q_tcp", user_key="demo_user",
                        chapter_id="ch2", answer="A", is_correct=True, created_at=now - timedelta(days=20)),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v2/learning/trend", params={"user_key": "demo_user", "course_id": COURSE_ID, "days": 14}
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 14
    assert data["this_week"] == {"attempts": 2, "correct": 1, "rate": 50, "days": 2}
    assert data["last_week"] == {"attempts": 2, "correct": 2, "rate": 100, "days": 2}
    assert data["rate_delta"] == -50
    assert data["attempt_delta"] == 0
    assert data["items"][-1]["date"] == now.date().isoformat()
