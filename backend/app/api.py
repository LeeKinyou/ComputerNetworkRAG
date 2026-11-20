"""HTTP 接口：课程、图谱、文档、检索、会话与运行事件。前缀 /api/v2。"""

from __future__ import annotations

import asyncio
import json
import random
from collections import Counter
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import TERMINAL, emit, execute_run, start_run
from app.config import settings
from app.db import get_session
from app.ingest import IngestError, ingest_document
from app.models import Attempt, Chapter, ChatSession, Chunk, Concept, ConceptEdge, Course, Document, Message, Question, Run, RunStep
from app.practice import answer_summary
from app.retrieval import retriever
from app.seed import COURSE_ID
from app.tools import get_concept
from app.util import iso, new_id, utcnow

router = APIRouter(prefix="/api/v2")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class RunCreate(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mode: str = "course_qa"
    user_key: str = Field(default="demo_user", max_length=64)


class RunInput(BaseModel):
    input_id: str
    approved: bool


class SessionCreate(BaseModel):
    course_id: str = COURSE_ID
    title: str | None = None
    user_key: str = Field(default="demo_user", max_length=64)


class SearchRequest(BaseModel):
    course_id: str = COURSE_ID
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _owner_of(row) -> str:
    """历史数据没有 user_key，按单用户时代的默认身份兜底。"""
    return getattr(row, "user_key", None) or "demo_user"


def _require_owner(row, user_key: str, message: str) -> None:
    """按 id 读/写的接口统一在这里校验归属：不匹配一律 404，不暴露对象是否存在。"""
    if row is None or _owner_of(row) != user_key:
        raise _fail(404, "NOT_FOUND", message)


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "db_backend": settings.db_backend,
        "llm_ready": settings.llm_ready,
        "retriever_ready": retriever.ready,
        "vector_mode": retriever.vector_mode,
        "embedder": retriever.embedder_label,
    }


@router.get("/meta")
async def meta(session: SessionDep) -> dict:
    course = await session.get(Course, COURSE_ID)
    concept_count = await session.scalar(select(func.count(Concept.id)))
    document_count = await session.scalar(select(func.count(Document.id)))
    chunk_count = await session.scalar(select(func.count(Chunk.id)))
    return {
        "course": {"id": course.id, "title": course.title} if course else None,
        "counts": {
            "concepts": concept_count or 0,
            "documents": document_count or 0,
            "chunks": chunk_count or 0,
        },
        "llm_ready": settings.llm_ready,
        "llm_model": settings.llm_model,
        "demo_questions": [
            "计算 192.168.10.137/27 的网络地址和可用主机数",
            "同一局域网内 ARP 是怎么工作的？",
            "把上面的前缀换成 /28 再算一次",
            "为什么要用 CIDR 做路由聚合？",
        ],
    }


@router.get("/courses")
async def list_courses(session: SessionDep) -> dict:
    courses = (await session.execute(select(Course))).scalars().all()
    return {
        "items": [
            {"id": c.id, "title": c.title, "description": c.description, "status": c.status}
            for c in courses
        ],
        "next_cursor": None,
    }


@router.get("/courses/{course_id}/chapters")
async def list_chapters(course_id: str, session: SessionDep) -> dict:
    chapters = (
        await session.execute(select(Chapter).where(Chapter.course_id == course_id))
    ).scalars().all()
    return {
        "items": [
            {"id": c.id, "parent_id": c.parent_id, "title": c.title, "sort_order": c.sort_order}
            for c in chapters
        ]
    }


@router.get("/courses/{course_id}/concepts")
async def list_concepts(course_id: str, session: SessionDep) -> dict:
    concepts = (
        await session.execute(select(Concept).where(Concept.course_id == course_id))
    ).scalars().all()
    return {
        "items": [
            {
                "id": c.id,
                "chapter_id": c.chapter_id,
                "code": c.code,
                "title": c.title,
                "description": c.description,
            }
            for c in concepts
        ],
        "next_cursor": None,
    }


@router.get("/courses/{course_id}/graph")
async def course_graph(course_id: str, session: SessionDep) -> dict:
    chapters = (
        await session.execute(
            select(Chapter).where(Chapter.course_id == course_id).order_by(Chapter.sort_order)
        )
    ).scalars().all()
    chapter_order = {chapter.id: index for index, chapter in enumerate(chapters)}
    concepts = (
        await session.execute(select(Concept).where(Concept.course_id == course_id))
    ).scalars().all()
    edges = (
        await session.execute(select(ConceptEdge).where(ConceptEdge.course_id == course_id))
    ).scalars().all()
    return {
        "nodes": [
            {
                "id": c.id,
                "name": c.title,
                "category": chapter_order.get(c.chapter_id or "", 0),
                "desc": c.description,
                "chapter_id": c.chapter_id,
            }
            for c in concepts
        ],
        "links": [
            {"source": e.source_id, "target": e.target_id, "kind": e.kind} for e in edges
        ],
        "chapters": [{"id": c.id, "title": c.title} for c in chapters],
    }


@router.get("/concepts/{concept_id}")
async def concept_detail(concept_id: str, session: SessionDep) -> dict:
    result = await get_concept(session, concept_id)
    if result.status != "ok":
        raise _fail(404, "NOT_FOUND", "知识点不存在")
    related = retriever.search(result.data["title"], top_k=2)
    return {**result.data, "sources": related}


@router.get("/courses/{course_id}/documents")
async def list_documents(course_id: str, session: SessionDep) -> dict:
    documents = (
        await session.execute(
            select(Document).where(Document.course_id == course_id).order_by(Document.created_at.desc())
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": d.id,
                "title": d.title,
                "filename": d.filename,
                "mime": d.mime,
                "size": d.size,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "chapter_id": d.chapter_id,
                "created_at": iso(d.created_at),
            }
            for d in documents
        ],
        "next_cursor": None,
    }


@router.post("/courses/{course_id}/documents", status_code=201)
async def upload_document(
    course_id: str,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
    chapter_id: Annotated[str | None, Form()] = None,
) -> dict:
    if course_id != COURSE_ID:
        raise _fail(404, "NOT_FOUND", "课程不存在")
    data = await file.read()
    try:
        document = await ingest_document(
            session,
            course_id=course_id,
            chapter_id=chapter_id or None,
            title=title.strip(),
            filename=file.filename or "upload.txt",
            data=data,
            max_bytes=settings.max_upload_bytes,
        )
    except IngestError as exc:
        raise _fail(422, exc.code, exc.message) from exc
    await retriever.refresh(session)
    return {
        "id": document.id,
        "title": document.title,
        "status": document.status,
        "chunk_count": document.chunk_count,
    }


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, session: SessionDep) -> Response:
    document = await session.get(Document, document_id)
    if document is None or document.id.startswith("doc_seed"):
        raise _fail(403, "FORBIDDEN", "预置文档不可删除")
    await session.delete(document)
    await session.commit()
    await retriever.refresh(session)
    return Response(status_code=204)


@router.get("/documents/{document_id}/chunks")
async def document_chunks(document_id: str, session: SessionDep, limit: int = Query(default=20, le=100)) -> dict:
    chunks = (
        await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal).limit(limit)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "chunk_id": c.id,
                "section_path": c.section_path,
                "page": c.page,
                "text": c.text,
            }
            for c in chunks
        ]
    }


@router.post("/search")
async def search(payload: SearchRequest, session: SessionDep) -> dict:
    if not retriever.ready:
        await retriever.refresh(session)
    results = retriever.search(payload.query, top_k=payload.top_k)
    return {"items": results, "total": len(results)}


@router.get("/sources/{chunk_id}")
async def source_detail(chunk_id: str) -> dict:
    detail = retriever.read_source(chunk_id, neighbor_count=1)
    if detail is None:
        raise _fail(404, "NOT_FOUND", "片段不存在或索引未就绪")
    return detail


@router.post("/chat-sessions", status_code=201)
async def create_session(payload: SessionCreate, session: SessionDep) -> dict:
    chat = ChatSession(
        id=new_id(),
        course_id=payload.course_id,
        title=payload.title or "新会话",
        user_key=payload.user_key,
    )
    session.add(chat)
    await session.commit()
    return {"id": chat.id, "course_id": chat.course_id, "title": chat.title}


@router.get("/chat-sessions")
async def list_sessions(
    session: SessionDep,
    course_id: str | None = None,
    user_key: str = Query(..., min_length=1),
) -> dict:
    query = select(ChatSession).order_by(ChatSession.created_at.desc())
    if course_id:
        query = query.where(ChatSession.course_id == course_id)
    query = query.where(ChatSession.user_key == user_key)
    sessions = (await session.execute(query)).scalars().all()
    items = []
    for item in sessions:
        last_run = await session.scalar(
            select(Run).where(Run.session_id == item.id).order_by(Run.created_at.desc()).limit(1)
        )
        items.append(
            {
                "id": item.id,
                "course_id": item.course_id,
                "title": item.title,
                "last_run": {
                    "run_id": last_run.id,
                    "question": last_run.question,
                    "status": last_run.status,
                    "mode": last_run.mode,
                    "created_at": iso(last_run.created_at),
                }
                if last_run
                else None,
            }
        )
    return {"items": items}


@router.get("/chat-sessions/{session_id}/messages")
async def list_messages(
    session_id: str,
    session: SessionDep,
    user_key: str = Query(..., min_length=1),
) -> dict:
    chat = await session.get(ChatSession, session_id)
    _require_owner(chat, user_key, "会话不存在")
    messages = (
        await session.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
        )
    ).scalars().all()
    return {
        "items": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": iso(m.created_at)}
            for m in messages
        ]
    }


@router.post("/chat-sessions/{session_id}/runs", status_code=202)
async def create_run(session_id: str, payload: RunCreate, session: SessionDep) -> dict:
    chat = await session.get(ChatSession, session_id)
    if chat is None or _owner_of(chat) != payload.user_key:
        raise _fail(404, "NOT_FOUND", "会话不存在")
    run = Run(
        id=new_id(),
        session_id=session_id,
        course_id=chat.course_id,
        mode=payload.mode,
        user_key=chat.user_key or payload.user_key,
        question=payload.message,
        status="queued",
    )
    if chat.title in ("新会话", ""):
        chat.title = payload.message[:24]
    session.add(run)
    session.add(Message(id=new_id(), session_id=session_id, role="user", content=payload.message))
    await session.commit()

    await emit(run.id, "run.queued", {"status": "queued"})
    await start_run(run.id)
    return {
        "run_id": run.id,
        "session_id": session_id,
        "status": "queued",
        "events_url": f"/api/v2/runs/{run.id}/events",
    }


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    session: SessionDep,
    user_key: str = Query(..., min_length=1),
) -> dict:
    run = await session.get(Run, run_id)
    _require_owner(run, user_key, "运行不存在")
    return {
        "run_id": run.id,
        "session_id": run.session_id,
        "status": run.status,
        "question": run.question,
        "answer_markdown": run.answer_markdown,
        "citations": run.citations or [],
        "cards": run.cards or [],
        "pending_input": run.pending_input,
        "error_code": run.error_code,
        "latest_seq": run.latest_seq,
        "created_at": iso(run.created_at),
    }


@router.get("/runs/{run_id}/steps")
async def run_steps(
    run_id: str,
    session: SessionDep,
    user_key: str = Query(..., min_length=1),
) -> dict:
    run = await session.get(Run, run_id)
    _require_owner(run, user_key, "运行不存在")
    steps = (
        await session.execute(
            select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.seq)
        )
    ).scalars().all()
    return {
        "items": [{"seq": step.seq, "type": step.type, "payload": step.payload} for step in steps]
    }


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    session: SessionDep,
    after_seq: int = 0,
    user_key: str = Query(..., min_length=1),
) -> StreamingResponse:
    run = await session.get(Run, run_id)
    _require_owner(run, user_key, "运行不存在")

    async def stream():
        cursor = after_seq
        idle_ticks = 0
        while True:
            rows = []
            terminal = False
            async with AsyncSessionLocal() as session:
                run = await session.get(Run, run_id)
                if run is None or _owner_of(run) != user_key:
                    yield "event: error\ndata: {\"code\":\"NOT_FOUND\"}\n\n"
                    return
                rows = (
                    await session.execute(
                        select(RunStep)
                        .where(RunStep.run_id == run_id, RunStep.seq > cursor)
                        .order_by(RunStep.seq)
                        .limit(200)
                    )
                ).scalars().all()
                terminal = run.status in TERMINAL
            if rows:
                idle_ticks = 0
                for step in rows:
                    cursor = step.seq
                    yield (
                        f"id: {step.seq}\n"
                        f"event: {step.type}\n"
                        f"data: {json.dumps(step.payload, ensure_ascii=False)}\n\n"
                    )
                continue
            if terminal:
                idle_ticks += 1
                if idle_ticks > 4:
                    return
            if idle_ticks % 100 == 0 and idle_ticks:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.15)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/inputs", status_code=202)
async def submit_input(
    run_id: str,
    payload: RunInput,
    session: SessionDep,
    user_key: str = Query(..., min_length=1),
) -> dict:
    run = await session.get(Run, run_id)
    _require_owner(run, user_key, "运行不存在")
    pending = run.pending_input or {}
    if run.status != "waiting_user" or pending.get("input_id") != payload.input_id:
        raise _fail(409, "RUN_NOT_WAITING", "当前运行不在等待审批状态")
    run.status = "running"
    await session.commit()
    await execute_run(run_id, resume={"approved": payload.approved})
    return {"run_id": run_id, "status": "running"}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    session: SessionDep,
    user_key: str = Query(..., min_length=1),
) -> dict:
    run = await session.get(Run, run_id)
    _require_owner(run, user_key, "运行不存在")
    if run.status in TERMINAL:
        return {"run_id": run.id, "status": run.status, "cancel_requested": False}
    run.status = "cancelled"
    run.pending_input = None
    await session.commit()
    await emit(run_id, "run.cancelled", {"status": "cancelled"})
    return {"run_id": run.id, "status": "cancelled", "cancel_requested": True}


@router.get("/analytics/overview")
async def analytics_overview(session: SessionDep, course_id: str = COURSE_ID) -> dict:
    """课程使用统计：真实 run 记录聚合，供学习报告与教师学情页使用。"""
    runs = (await session.execute(select(Run).where(Run.course_id == course_id))).scalars().all()
    run_ids = [run.id for run in runs]
    tool_calls = 0
    if run_ids:
        tool_calls = int(
            await session.scalar(
                select(func.count())
                .select_from(RunStep)
                .where(RunStep.run_id.in_(run_ids), RunStep.type == "action")
            )
            or 0
        )
    today = utcnow().date()
    week = [run for run in runs if run.created_at and (today - run.created_at.date()).days < 7]
    month = [run for run in runs if run.created_at and (today - run.created_at.date()).days < 30]

    daily = [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "count": sum(
                1 for run in runs if run.created_at and run.created_at.date() == today - timedelta(days=offset)
            ),
        }
        for offset in range(13, -1, -1)
    ]

    question_counts = Counter(run.question.strip() for run in runs if run.question.strip())
    hot_questions = [
        {"question": text, "count": count} for text, count in question_counts.most_common(6)
    ]

    chapters = (
        await session.execute(
            select(Chapter).where(Chapter.course_id == course_id).order_by(Chapter.sort_order)
        )
    ).scalars().all()
    documents = (
        await session.execute(select(Document).where(Document.course_id == course_id))
    ).scalars().all()
    chapter_of_doc = {doc.title: doc.chapter_id for doc in documents}
    chapter_hits: Counter[str] = Counter()
    doc_hits: Counter[str] = Counter()
    for run in runs:
        for citation in run.citations or []:
            title = str(citation.get("title") or "")
            doc_hits[title] += 1
            chapter_id = chapter_of_doc.get(title)
            if chapter_id:
                chapter_hits[chapter_id] += 1
    total_hits = sum(chapter_hits.values()) or 1
    chapter_focus = [
        {"label": chapter.title, "value": round(chapter_hits[chapter.id] * 100 / total_hits)}
        for chapter in chapters
    ]

    return {
        "questions": len(runs),
        "questions_week": len(week),
        "questions_month": len(month),
        "pending_approvals": sum(1 for run in runs if run.status == "waiting_user"),
        "tool_calls": tool_calls,
        "completion_rate": (
            round(sum(1 for run in runs if run.status == "completed") * 100 / len(runs)) if runs else 0
        ),
        "mode_split": {
            "rag": sum(1 for run in runs if run.mode == "rag"),
            "agent": sum(1 for run in runs if run.mode != "rag"),
        },
        "daily": daily,
        "hot_questions": hot_questions,
        "chapter_focus": chapter_focus,
        "top_documents": [
            {"title": title, "count": count} for title, count in doc_hits.most_common(4)
        ],
        "documents": {
            "count": len(documents),
            "chunks": sum(doc.chunk_count for doc in documents),
        },
    }


class AttemptIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=36)
    answer: str = Field(default="", max_length=8)
    user_key: str = Field(default="demo_user", max_length=64)


def _question_public(question: Question, chapter_title: str = "") -> dict:
    """题目对外结构：不下发答案与解析，提交后再返回。"""
    return {
        "id": question.id,
        "chapter_id": question.chapter_id,
        "chapter_title": chapter_title,
        "concept_id": question.concept_id,
        "type": question.type,
        "stem": question.stem,
        "options": question.options,
        "difficulty": question.difficulty,
        "image_url": question.image_url,
    }


@router.get("/questions")
async def list_questions(
    session: SessionDep,
    course_id: str = COURSE_ID,
    chapter_id: str | None = None,
    concept_id: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    shuffle: bool = True,
) -> dict:
    stmt = select(Question).where(Question.course_id == course_id)
    if chapter_id:
        stmt = stmt.where(Question.chapter_id == chapter_id)
    if concept_id:
        stmt = stmt.where(Question.concept_id == concept_id)
    questions = (await session.execute(stmt.order_by(Question.sort_order))).scalars().all()
    if shuffle and len(questions) > limit:
        questions = random.sample(questions, limit)
    else:
        questions = questions[:limit]
    chapters = (
        await session.execute(select(Chapter).where(Chapter.course_id == course_id))
    ).scalars().all()
    titles = {chapter.id: chapter.title for chapter in chapters}
    return {
        "course_id": course_id,
        "total": len(questions),
        "items": [_question_public(question, titles.get(question.chapter_id, "")) for question in questions],
    }


@router.get("/questions/recommended")
async def recommended_questions(
    session: SessionDep,
    course_id: str = COURSE_ID,
    user_key: str = "demo_user",
    limit: int = Query(10, ge=1, le=30),
) -> dict:
    """按掌握度组卷：未练过的知识点优先，其次正确率偏低的概念，并给出推荐理由。"""
    questions = (
        await session.execute(select(Question).where(Question.course_id == course_id))
    ).scalars().all()
    attempts = (
        await session.execute(
            select(Attempt).where(Attempt.course_id == course_id, Attempt.user_key == user_key)
        )
    ).scalars().all()
    concepts = (await session.execute(select(Concept).where(Concept.course_id == course_id))).scalars().all()
    chapters = (await session.execute(select(Chapter).where(Chapter.course_id == course_id))).scalars().all()
    concept_titles = {concept.id: concept.title for concept in concepts}
    chapter_titles = {chapter.id: chapter.title for chapter in chapters}

    concept_stats: dict[str, dict[str, int]] = {}
    answered: set[str] = set()
    by_id = {question.id: question for question in questions}
    for attempt in attempts:
        answered.add(attempt.question_id)
        concept_id = by_id[attempt.question_id].concept_id if attempt.question_id in by_id else None
        if not concept_id:
            continue
        bucket = concept_stats.setdefault(concept_id, {"total": 0, "correct": 0})
        bucket["total"] += 1
        if attempt.is_correct:
            bucket["correct"] += 1

    def rank(question: Question) -> tuple[int, int, float]:
        stat = concept_stats.get(question.concept_id) if question.concept_id else None
        if not stat:
            priority = 0
        else:
            rate = stat["correct"] / stat["total"]
            priority = 1 if rate < 0.6 else 2 if rate < 0.8 else 3
        return (priority, 0 if question.id not in answered else 1, random.random())

    items: list[dict] = []
    for question in sorted(questions, key=rank)[:limit]:
        stat = concept_stats.get(question.concept_id) if question.concept_id else None
        title = concept_titles.get(question.concept_id or "", question.concept_id or "相关知识点")
        if not stat:
            reason = f"还没练过「{title}」" if question.concept_id else "换个章节的题试试"
        else:
            rate = round(stat["correct"] / stat["total"] * 100)
            if rate < 60:
                reason = f"「{title}」正确率 {rate}%，优先巩固"
            elif rate < 80:
                reason = f"「{title}」正确率 {rate}%，再练一轮"
            else:
                reason = f"「{title}」已掌握，换个角度检验"
        payload = _question_public(question, chapter_titles.get(question.chapter_id, ""))
        payload["reason"] = reason
        items.append(payload)
    return {"course_id": course_id, "total": len(items), "items": items}


@router.get("/analytics/concepts")
async def analytics_concepts(
    session: SessionDep,
    course_id: str = COURSE_ID,
    user_key: str | None = None,
) -> dict:
    """概念粒度学情：教师端看全班掌握分布，学生端可只看自己。"""
    concepts = (await session.execute(select(Concept).where(Concept.course_id == course_id))).scalars().all()
    questions = (
        await session.execute(select(Question).where(Question.course_id == course_id))
    ).scalars().all()
    stmt = select(Attempt).where(Attempt.course_id == course_id)
    if user_key:
        stmt = stmt.where(Attempt.user_key == user_key)
    attempts = (await session.execute(stmt)).scalars().all()
    by_id = {question.id: question for question in questions}

    buckets: dict[str, dict[str, object]] = {}
    for attempt in attempts:
        question = by_id.get(attempt.question_id)
        concept_id = question.concept_id if question else None
        if not concept_id:
            continue
        bucket = buckets.setdefault(concept_id, {"total": 0, "correct": 0, "students": set(), "weak": set()})
        bucket["total"] = int(bucket["total"]) + 1  # type: ignore[arg-type]
        if attempt.is_correct:
            bucket["correct"] = int(bucket["correct"]) + 1  # type: ignore[arg-type]
        students = bucket["students"]
        if isinstance(students, set):
            students.add(attempt.user_key)

    # 同一学生同一概念的正确率，用来判断“薄弱学生”人数
    per_student: dict[tuple[str, str], list[int]] = {}
    for attempt in attempts:
        question = by_id.get(attempt.question_id)
        if not question or not question.concept_id:
            continue
        key = (attempt.user_key, question.concept_id)
        pair = per_student.setdefault(key, [0, 0])
        pair[0] += 1
        if attempt.is_correct:
            pair[1] += 1

    items = []
    for concept in concepts:
        bucket = buckets.get(concept.id, {"total": 0, "correct": 0, "students": set()})
        total = int(bucket["total"])  # type: ignore[arg-type]
        correct = int(bucket["correct"])  # type: ignore[arg-type]
        students = bucket["students"]
        weak_students = sum(
            1
            for (owner, concept_id), (attempts_count, correct_count) in per_student.items()
            if concept_id == concept.id and attempts_count and correct_count / attempts_count < 0.6
        )
        rate = round(correct / total * 100) if total else 0
        if not total:
            state = "no_data"
        elif rate < 60:
            state = "weak"
        elif rate < 80:
            state = "normal"
        else:
            state = "mastered"
        items.append(
            {
                "concept_id": concept.id,
                "title": concept.title,
                "chapter_id": concept.chapter_id,
                "attempts": total,
                "correct": correct,
                "rate": rate,
                "students": len(students) if isinstance(students, set) else 0,
                "weak_students": weak_students,
                "state": state,
            }
        )
    items.sort(key=lambda item: (-item["attempts"], item["concept_id"]))
    return {
        "course_id": course_id,
        "total_concepts": len(items),
        "covered_concepts": sum(1 for item in items if item["attempts"]),
        "items": items,
    }


async def _attempt_stats(session: AsyncSession, user_key: str, course_id: str) -> dict:
    attempts = (
        await session.execute(
            select(Attempt).where(Attempt.course_id == course_id, Attempt.user_key == user_key)
        )
    ).scalars().all()
    total = len(attempts)
    correct = sum(1 for attempt in attempts if attempt.is_correct)
    return {
        "total": total,
        "correct": correct,
        "rate": round(correct * 100 / total) if total else 0,
    }


@router.post("/practice/attempts", status_code=201)
async def create_attempt(payload: AttemptIn, session: SessionDep) -> dict:
    question = await session.get(Question, payload.question_id)
    if question is None or question.course_id != COURSE_ID:
        raise _fail(404, "QUESTION_NOT_FOUND", "题目不存在")
    summary = answer_summary(question.type, payload.answer, question.answer)
    attempt = Attempt(
        course_id=COURSE_ID,
        question_id=question.id,
        user_key=payload.user_key,
        chapter_id=question.chapter_id,
        answer=summary["answer"] or "",
        is_correct=summary["correct"],
    )
    session.add(attempt)
    await session.commit()
    stats = await _attempt_stats(session, payload.user_key, COURSE_ID)
    return {
        "attempt_id": attempt.id,
        "correct": summary["correct"],
        "given": summary["answer"],
        "expected": summary["expected"],
        "explanation": question.explanation,
        "source": question.source,
        "stats": stats,
    }


@router.get("/practice/attempts")
async def list_attempts(
    session: SessionDep,
    user_key: str = "demo_user",
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    rows = (
        await session.execute(
            select(Attempt)
            .where(Attempt.user_key == user_key)
            .order_by(Attempt.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    questions = {question.id: question for question in (await session.execute(select(Question))).scalars().all()}
    items = []
    for row in rows:
        question = questions.get(row.question_id)
        items.append(
            {
                "attempt_id": row.id,
                "question_id": row.question_id,
                "stem": question.stem if question else "题目已移除",
                "type": question.type if question else "single",
                "chapter_id": row.chapter_id,
                "answer": row.answer,
                "expected": question.answer if question else "",
                "correct": row.is_correct,
                "created_at": iso(row.created_at),
            }
        )
    return {"items": items}


@router.get("/practice/stats")
async def practice_stats(
    session: SessionDep,
    course_id: str = COURSE_ID,
    user_key: str = "demo_user",
) -> dict:
    attempts = (
        await session.execute(
            select(Attempt).where(Attempt.course_id == course_id, Attempt.user_key == user_key)
        )
    ).scalars().all()
    questions = {question.id: question for question in (await session.execute(select(Question))).scalars().all()}
    chapters = (
        await session.execute(select(Chapter).where(Chapter.course_id == course_id))
    ).scalars().all()
    titles = {chapter.id: chapter.title for chapter in chapters}

    total = len(attempts)
    correct = sum(1 for attempt in attempts if attempt.is_correct)

    chapter_rows: dict[str, dict] = {}
    wrong_rows: dict[str, dict] = {}
    for attempt in attempts:
        bucket = chapter_rows.setdefault(
            attempt.chapter_id,
            {"chapter_id": attempt.chapter_id, "label": titles.get(attempt.chapter_id, "未挂章节"), "attempts": 0, "correct": 0},
        )
        bucket["attempts"] += 1
        if attempt.is_correct:
            bucket["correct"] += 1
        else:
            question = questions.get(attempt.question_id)
            row = wrong_rows.setdefault(
                attempt.question_id,
                {
                    "question_id": attempt.question_id,
                    "stem": question.stem if question else "题目已移除",
                    "chapter_id": attempt.chapter_id,
                    "wrong_count": 0,
                },
            )
            row["wrong_count"] += 1

    by_chapter = [
        {**row, "rate": round(row["correct"] * 100 / row["attempts"]) if row["attempts"] else 0}
        for row in chapter_rows.values()
    ]
    by_chapter.sort(key=lambda item: item["rate"])

    return {
        "total": total,
        "correct": correct,
        "rate": round(correct * 100 / total) if total else 0,
        "by_chapter": by_chapter,
        "wrong_questions": sorted(wrong_rows.values(), key=lambda item: item["wrong_count"], reverse=True)[:8],
    }


@router.get("/practice/wrongbook")
async def practice_wrongbook(
    session: SessionDep,
    course_id: str = COURSE_ID,
    user_key: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    """错题本：只保留「最近一次作答仍是错」的题，重做对了自动移出。"""
    attempts = (
        await session.execute(
            select(Attempt)
            .where(Attempt.course_id == course_id, Attempt.user_key == user_key)
            .order_by(Attempt.created_at)
        )
    ).scalars().all()
    questions = {
        question.id: question
        for question in (await session.execute(select(Question).where(Question.course_id == course_id))).scalars().all()
    }
    concepts = {
        concept.id: concept
        for concept in (await session.execute(select(Concept).where(Concept.course_id == course_id))).scalars().all()
    }
    chapters = {
        chapter.id: chapter
        for chapter in (await session.execute(select(Chapter).where(Chapter.course_id == course_id))).scalars().all()
    }

    latest: dict[str, Attempt] = {}
    wrong_count: dict[str, int] = {}
    total_count: dict[str, int] = {}
    for attempt in attempts:
        latest[attempt.question_id] = attempt
        total_count[attempt.question_id] = total_count.get(attempt.question_id, 0) + 1
        if not attempt.is_correct:
            wrong_count[attempt.question_id] = wrong_count.get(attempt.question_id, 0) + 1

    items = []
    for question_id, attempt in latest.items():
        if attempt.is_correct:
            continue
        question = questions.get(question_id)
        if question is None:
            continue
        concept = concepts.get(question.concept_id or "")
        chapter = chapters.get(question.chapter_id)
        items.append(
            {
                "question_id": question.id,
                "stem": question.stem,
                "type": question.type,
                "image_url": question.image_url,
                "concept_id": question.concept_id,
                "concept_title": concept.title if concept else "未挂知识点",
                "chapter_id": question.chapter_id,
                "chapter_title": chapter.title if chapter else "未挂章节",
                "wrong": wrong_count.get(question_id, 0),
                "attempts": total_count.get(question_id, 0),
                "last_wrong_at": iso(attempt.created_at),
            }
        )
    items.sort(key=lambda item: (-item["wrong"], item["last_wrong_at"]))

    groups: dict[str, dict] = {}
    for item in items:
        bucket = groups.setdefault(
            item["concept_id"] or "",
            {
                "concept_id": item["concept_id"],
                "title": item["concept_title"],
                "chapter_title": item["chapter_title"],
                "wrong": 0,
                "items": [],
            },
        )
        bucket["wrong"] = int(bucket["wrong"]) + 1
        bucket["items"].append(item)

    solved = sum(
        1
        for question_id, attempt in latest.items()
        if attempt.is_correct and wrong_count.get(question_id)
    )
    ordered_groups = sorted(groups.values(), key=lambda group: (-int(group["wrong"]), group["title"]))
    return {
        "user_key": user_key,
        "unresolved": len(items),
        "solved": solved,
        "concepts_affected": len(ordered_groups),
        "groups": ordered_groups,
        "items": items[:limit],
    }


from app.db import SessionFactory as AsyncSessionLocal  # noqa: E402
