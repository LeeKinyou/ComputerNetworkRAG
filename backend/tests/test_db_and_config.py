"""数据层与配置契约：DSN 拼装、轻量迁移、归属同步与事务上下文。

迁移用例直接在临时内存库上执行旧结构 DDL，不触碰 runtime/app.db。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import db
from app.cleanup_orphans import delete_orphan_chunks, find_orphan_chunk_ids
from app.config import PROJECT_DIR, settings
from app.models import Base, ChatSession, Chunk, Course, Document, Run


LEGACY_DDL = [
    """
    CREATE TABLE questions (
        id VARCHAR(36) PRIMARY KEY,
        course_id VARCHAR(36),
        chapter_id VARCHAR(36),
        concept_id VARCHAR(36),
        type VARCHAR(16),
        stem TEXT,
        options JSON,
        answer VARCHAR(8),
        explanation TEXT,
        source VARCHAR(200),
        difficulty VARCHAR(16),
        sort_order INTEGER
    )
    """,
    """
    CREATE TABLE runs (
        id VARCHAR(36) PRIMARY KEY,
        session_id VARCHAR(36),
        course_id VARCHAR(36),
        mode VARCHAR(24),
        question TEXT,
        status VARCHAR(16),
        answer_markdown TEXT,
        citations JSON,
        cards JSON,
        pending_input JSON,
        error_code VARCHAR(64),
        error_message TEXT,
        latest_seq INTEGER,
        created_at DATETIME,
        updated_at DATETIME
    )
    """,
    """
    CREATE TABLE chat_sessions (
        id VARCHAR(36) PRIMARY KEY,
        course_id VARCHAR(36),
        title VARCHAR(200),
        created_at DATETIME
    )
    """,
]


@asynccontextmanager
async def db_engine(*, foreign_keys: bool = False) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    if foreign_keys:
        db.enable_sqlite_foreign_keys(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


def test_sqlite_url_uses_resolved_path(monkeypatch):
    monkeypatch.setattr(settings, "db_backend", "sqlite")
    monkeypatch.setattr(settings, "db_sqlite_path", "./runtime/app.db")
    assert db._database_url() == f"sqlite+aiosqlite:///{settings.sqlite_path}"


@pytest.mark.parametrize(
    "dsn, expected",
    [
        ("postgresql://u:p@h:5432/cnrag", "postgresql+asyncpg://u:p@h:5432/cnrag"),
        ("postgres://u:p@h/cnrag", "postgresql+asyncpg://u:p@h/cnrag"),
        ("postgresql+asyncpg://u:p@h/cnrag", "postgresql+asyncpg://u:p@h/cnrag"),
    ],
)
def test_postgres_dsn_normalization(monkeypatch, dsn: str, expected: str):
    monkeypatch.setattr(settings, "db_backend", "postgresql")
    monkeypatch.setattr(settings, "db_postgres_dsn", dsn)
    assert db._database_url() == expected


def test_postgres_backend_without_dsn_fails_fast(monkeypatch):
    monkeypatch.setattr(settings, "db_backend", "postgresql")
    monkeypatch.setattr(settings, "db_postgres_dsn", "   ")
    with pytest.raises(RuntimeError, match="DB_POSTGRES_DSN"):
        db._database_url()


def test_resolve_path_is_anchored_to_project_root():
    assert settings.resolve_path("./runtime/x.db") == PROJECT_DIR / "runtime" / "x.db"
    absolute = PROJECT_DIR / "runtime" / "x.db"
    assert settings.resolve_path(str(absolute)) == absolute


@pytest.mark.parametrize("key, ready", [("", False), ("   ", False), ("sk-test", True)])
def test_llm_ready_only_depends_on_trimmed_key(monkeypatch, key: str, ready: bool):
    monkeypatch.setattr(settings, "llm_api_key", key)
    assert settings.llm_ready is ready


async def test_ensure_columns_backfills_legacy_schema_once():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    try:
        async with engine.begin() as conn:
            for ddl in LEGACY_DDL:
                await conn.execute(text(ddl))

            def columns_of(connection) -> dict[str, set[str]]:
                inspector = inspect(connection)
                return {
                    table: {column["name"] for column in inspector.get_columns(table)}
                    for table in ("questions", "runs", "chat_sessions")
                }

            before = await conn.run_sync(columns_of)
            assert before["questions"] == {
                "id", "course_id", "chapter_id", "concept_id", "type", "stem", "options",
                "answer", "explanation", "source", "difficulty", "sort_order",
            }
            assert "user_key" not in before["runs"]
            assert "user_key" not in before["chat_sessions"]

            await conn.run_sync(db._ensure_columns)
            await conn.run_sync(db._ensure_columns)  # 二次执行必须幂等
            after = await conn.run_sync(columns_of)
    finally:
        await engine.dispose()

    assert "image_url" in after["questions"]
    assert "user_key" in after["runs"]
    assert "user_key" in after["chat_sessions"]


async def test_sync_run_owner_aligns_mismatch_and_keeps_orphans():
    async with db_engine() as (engine, factory):
        async with factory() as session:
            session.add(ChatSession(id="s1", course_id="course_cn", title="会话", user_key="owner1"))
            session.add_all(
                [
                    Run(id="r1", session_id="s1", course_id="course_cn", question="q1", user_key="stale"),
                    Run(id="r2", session_id="s_missing", course_id="course_cn", question="q2", user_key="someone"),
                    Run(id="r3", session_id="s1", course_id="course_cn", question="q3", user_key="owner1"),
                ]
            )
            await session.commit()

        async with engine.begin() as conn:
            await conn.run_sync(db._sync_run_owner)

        async with factory() as session:
            owners = {
                run.id: run.user_key for run in (await session.execute(select(Run))).scalars().all()
            }
        assert owners == {"r1": "owner1", "r2": "someone", "r3": "owner1"}

        # 幂等：再跑一次不改变任何归属
        async with engine.begin() as conn:
            await conn.run_sync(db._sync_run_owner)
        async with factory() as session:
            owners_again = {
                run.id: run.user_key for run in (await session.execute(select(Run))).scalars().all()
            }
        assert owners_again == owners


async def test_session_scope_commits_and_rolls_back(monkeypatch):
    async with db_engine() as (_, factory):
        monkeypatch.setattr(db, "SessionFactory", factory)

        async with db.session_scope() as session:
            session.add(Course(id="course_cn", title="计算机网络", description=""))
        async with factory() as session:
            assert await session.scalar(select(func.count(Course.id))) == 1

        with pytest.raises(RuntimeError, match="boom"):
            async with db.session_scope() as session:
                session.add(Course(id="course_extra", title="额外课程", description=""))
                raise RuntimeError("boom")
        async with factory() as session:
            assert await session.scalar(select(func.count(Course.id))) == 1


async def test_sqlite_foreign_keys_pragma_is_enabled():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    db.enable_sqlite_foreign_keys(engine)
    try:
        async with engine.connect() as conn:
            assert await conn.scalar(text("PRAGMA foreign_keys")) == 1
    finally:
        await engine.dispose()


async def test_foreign_keys_cascade_chunks_on_document_delete():
    async with db_engine(foreign_keys=True) as (_, factory):
        async with factory() as session:
            session.add(Course(id="course_cn", title="计算机网络", description=""))
            await session.flush()
            session.add(Document(id="d1", course_id="course_cn", title="讲义", filename="a.md",
                                 mime="text/markdown", size=10, chunk_count=2))
            await session.flush()
            session.add_all(
                [
                    Chunk(id="c1", document_id="d1", ordinal=0, section_path=[], text="正文一"),
                    Chunk(id="c2", document_id="d1", ordinal=1, section_path=[], text="正文二"),
                ]
            )
            await session.commit()

        async with factory() as session:
            document = await session.get(Document, "d1")
            await session.delete(document)
            await session.commit()

        async with factory() as session:
            assert await session.scalar(select(func.count(Chunk.id))) == 0


async def test_cleanup_orphan_chunks_counts_then_deletes():
    async with db_engine() as (_, factory):
        async with factory() as session:
            session.add(Course(id="course_cn", title="计算机网络", description=""))
            session.add(Document(id="d1", course_id="course_cn", title="讲义", filename="a.md",
                                 mime="text/markdown", size=10, chunk_count=1))
            session.add_all(
                [
                    Chunk(id="c_ok", document_id="d1", ordinal=0, section_path=[], text="有效分块"),
                    Chunk(id="c_orphan", document_id="d_missing", ordinal=0, section_path=[], text="孤儿分块"),
                ]
            )
            await session.commit()

        async with factory() as session:
            assert await find_orphan_chunk_ids(session) == ["c_orphan"]
            assert await delete_orphan_chunks(session) == 1
            await session.commit()
            assert await find_orphan_chunk_ids(session) == []
            assert await session.scalar(select(func.count(Chunk.id))) == 1

