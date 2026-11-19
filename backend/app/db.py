"""数据层：异步引擎、会话工厂与建表入口。lite 档默认 SQLite，hybrid 档可切 PostgreSQL。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base


def _database_url() -> str:
    if settings.db_backend.lower() == "sqlite":
        return f"sqlite+aiosqlite:///{settings.sqlite_path}"
    dsn = settings.db_postgres_dsn.strip()
    if not dsn:
        raise RuntimeError("DB_BACKEND=postgresql 但未配置 DB_POSTGRES_DSN")
    if dsn.startswith("postgresql://"):
        dsn = "postgresql+asyncpg://" + dsn[len("postgresql://") :]
    elif dsn.startswith("postgres://"):
        dsn = "postgresql+asyncpg://" + dsn[len("postgres://") :]
    return dsn


settings.ensure_runtime()

engine = create_async_engine(
    _database_url(),
    echo=False,
    pool_pre_ping=True,
    connect_args=(
        {"timeout": settings.db_sqlite_busy_timeout_ms / 1000}
        if settings.db_backend.lower() == "sqlite"
        else {}
    ),
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_columns)
    await seed_if_empty()


def _ensure_columns(connection) -> None:
    """轻量迁移：create_all 不会给已有表补列，旧演示库在这里就地补齐。"""
    inspector = inspect(connection)
    if "questions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("questions")}
    if "image_url" not in columns:
        connection.execute(text("ALTER TABLE questions ADD COLUMN image_url VARCHAR(300)"))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """后台任务（Agent 执行）使用的独立事务上下文。"""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def shutdown_db() -> None:
    await engine.dispose()


from app.seed import seed_if_empty  # noqa: E402  (避免 models 与 seed 循环导入)
