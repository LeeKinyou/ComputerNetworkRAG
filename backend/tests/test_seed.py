"""初始化种子契约：外键开启时仍能按依赖顺序灌入完整演示数据，且可重复执行。"""

from __future__ import annotations

import app.db  # noqa: F401  先完成 db → seed 的初始化顺序
from sqlalchemy import func, select

from app.models import Chapter, Chunk, Concept, ConceptEdge, Course, Document, Question
from app.seed import COURSE_ID, CONCEPTS, CHAPTERS, EDGES, QUESTIONS, SEED_DOCUMENTS, seed_if_empty
from _support import memory_db


async def test_seed_if_empty_builds_dataset_with_foreign_keys(monkeypatch):
    async with memory_db(foreign_keys=True) as factory:
        monkeypatch.setattr("app.seed.SessionFactory", factory)
        await seed_if_empty()

        async with factory() as session:
            assert await session.scalar(select(func.count(Course.id))) == 1
            assert await session.scalar(select(func.count(Chapter.id))) == len(CHAPTERS)
            assert await session.scalar(select(func.count(Concept.id))) == len(CONCEPTS)
            assert await session.scalar(select(func.count(ConceptEdge.id))) == len(EDGES)
            assert await session.scalar(select(func.count(Document.id))) == len(SEED_DOCUMENTS)
            expected_chunks = sum(len(item["chunks"]) for item in SEED_DOCUMENTS)
            assert await session.scalar(select(func.count(Chunk.id))) == expected_chunks
            assert await session.scalar(select(func.count(Question.id))) == len(QUESTIONS)

            course = await session.get(Course, COURSE_ID)
            assert course is not None


async def test_seed_if_empty_is_idempotent(monkeypatch):
    async with memory_db(foreign_keys=True) as factory:
        monkeypatch.setattr("app.seed.SessionFactory", factory)
        await seed_if_empty()

        async with factory() as session:
            first = (
                await session.scalar(select(func.count(Document.id))),
                await session.scalar(select(func.count(Chunk.id))),
                await session.scalar(select(func.count(Question.id))),
            )

        await seed_if_empty()

        async with factory() as session:
            second = (
                await session.scalar(select(func.count(Document.id))),
                await session.scalar(select(func.count(Chunk.id))),
                await session.scalar(select(func.count(Question.id))),
            )
        assert second == first
