"""测试共用支撑：内存 SQLite、API 客户端与最小课程骨架。

约定与现有测试一致：每个用例一套独立内存库，通过 dependency_overrides
替换 `get_session`，不读写 runtime/app.db。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import enable_sqlite_foreign_keys, get_session
from app.main import app
from app.models import Base, Chapter, Concept, ConceptEdge, Course, Question
from app.seed import COURSE_ID

Factory = async_sessionmaker[AsyncSession]


def _new_engine(*, foreign_keys: bool = False):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    if foreign_keys:
        # 与生产连接一致：外键约束开启，级联删除才能真正生效
        enable_sqlite_foreign_keys(engine)
    return engine


@asynccontextmanager
async def memory_db(*, foreign_keys: bool = False) -> AsyncIterator[Factory]:
    """建好全量表的内存库，退出时释放连接。"""
    engine = _new_engine(foreign_keys=foreign_keys)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


@asynccontextmanager
async def api_harness(*, foreign_keys: bool = False) -> AsyncIterator[tuple[AsyncClient, Factory]]:
    """内存库 + ASGI 客户端，接口读到的是临时库。"""
    engine = _new_engine(foreign_keys=foreign_keys)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, factory
    finally:
        app.dependency_overrides.pop(get_session, None)
        await engine.dispose()


async def ensure_course(factory: Factory, *, course_id: str = COURSE_ID) -> None:
    """外键开启时，插入文档/章节前先保证课程存在。"""
    async with factory() as session:
        if await session.get(Course, course_id) is None:
            session.add(Course(id=course_id, title="计算机网络", description=""))
            await session.commit()


async def seed_course(factory: Factory, *, course_id: str = COURSE_ID) -> None:
    """最小课程骨架：两章四概念，mac → arp 是先修关系。"""
    async with factory() as session:
        session.add(Course(id=course_id, title="计算机网络", description=""))
        await session.flush()  # 外键开启时先落课程，章节与概念才能引用
        session.add_all(
            [
                Chapter(id="ch1", course_id=course_id, title="数据链路层", sort_order=1),
                Chapter(id="ch2", course_id=course_id, title="网络层", sort_order=2),
            ]
        )
        session.add_all(
            [
                Concept(id="c_mac", course_id=course_id, chapter_id="ch1", code="mac", title="MAC 地址", sort_order=1),
                Concept(id="c_dns", course_id=course_id, chapter_id="ch1", code="dns", title="DNS", sort_order=2),
                Concept(id="c_arp", course_id=course_id, chapter_id="ch2", code="arp", title="ARP", sort_order=1),
                Concept(id="c_tcp", course_id=course_id, chapter_id="ch2", code="tcp", title="TCP", sort_order=2),
            ]
        )
        await session.flush()  # 概念先落库，先修边才能引用
        session.add(
            ConceptEdge(
                id="e1", course_id=course_id, source_id="c_mac", target_id="c_arp", kind="prerequisite"
            )
        )
        session.add_all(
            [
                Question(id="q_arp", course_id=course_id, chapter_id="ch2", concept_id="c_arp",
                         type="single", stem="ARP 的作用是什么？", options=["A", "B", "C"], answer="B",
                         explanation="ARP 负责地址解析。"),
                Question(id="q_tcp", course_id=course_id, chapter_id="ch2", concept_id="c_tcp",
                         type="single", stem="三次握手的第二个报文是什么？", options=["A", "B"], answer="A"),
                Question(id="q_dns", course_id=course_id, chapter_id="ch1", concept_id="c_dns",
                         type="single", stem="DNS 默认使用哪个端口？", options=["A", "B", "C"], answer="C"),
                Question(id="q_mac", course_id=course_id, chapter_id="ch1", concept_id="c_mac",
                         type="judge", stem="MAC 地址是 48 位。", answer="T"),
            ]
        )
        await session.commit()


async def add_attempt(
    factory: Factory,
    *,
    attempt_id: str,
    question_id: str,
    chapter_id: str,
    correct: bool,
    user_key: str = "demo_user",
    course_id: str = COURSE_ID,
) -> None:
    from app.models import Attempt

    async with factory() as session:
        session.add(
            Attempt(
                id=attempt_id,
                course_id=course_id,
                question_id=question_id,
                user_key=user_key,
                chapter_id=chapter_id,
                answer="A",
                is_correct=correct,
            )
        )
        await session.commit()
