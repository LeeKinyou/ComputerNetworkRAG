"""HTTP 接口：课程、图谱、文档、检索、会话与运行事件。前缀 /api/v2。"""

from __future__ import annotations

import asyncio
import json
import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import TERMINAL, emit, execute_run, start_run
from app.auth import (
    authenticate,
    clear_session_cookie,
    current_account,
    ensure_owner,
    require_teacher,
    scoped_user_key,
    set_session_cookie,
)
from app.config import settings
from app.db import get_session
from app.ingest import IngestError, ingest_document
from app.assignment_import import AssignmentImportError, parse_assignment_text
from app.grader import grade_item, rule_grade
from app.models import (
    Assignment,
    AssignmentItem,
    Attempt,
    Chapter,
    ChatSession,
    Chunk,
    Concept,
    ConceptEdge,
    Course,
    Document,
    Message,
    Question,
    Run,
    RunStep,
    Submission,
    SubmissionItem,
)
from app.practice import answer_summary
from app.profile import build_profile
from app.retrieval import retriever
from app.seed import COURSE_ID
from app.tools import get_concept
from app.util import iso, new_id, utcnow

router = APIRouter(prefix="/api/v2")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class RunCreate(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mode: str = "rag"
    user_key: str | None = Field(default=None, max_length=64)


class RunInput(BaseModel):
    input_id: str
    approved: bool


class SessionCreate(BaseModel):
    course_id: str = COURSE_ID
    title: str | None = None
    user_key: str | None = Field(default=None, max_length=64)


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
        "auth_enabled": settings.auth_enabled,
        "llm_ready": settings.llm_ready,
        "retriever_ready": retriever.ready,
        "vector_mode": retriever.vector_mode,
        "embedder": retriever.embedder_label,
    }


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


@router.post("/auth/login")
async def login(payload: LoginIn, response: Response) -> dict:
    account = authenticate(payload.username, payload.password)
    if account is None:
        raise _fail(401, "INVALID_CREDENTIALS", "用户名或密码错误")
    set_session_cookie(response, account)
    return {"authenticated": True, "user": account.as_dict()}


@router.get("/auth/me")
async def auth_me(request: Request) -> dict:
    account = current_account(request)
    return {
        "authenticated": bool(account),
        "auth_enabled": settings.auth_enabled,
        "user": account.as_dict() if account else None,
    }


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"authenticated": False}


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
    # 引用命中：按问答 citations 统计每份文档被多少个提问引用过（同一提问多片段只计一次），
    # 与文档详情的「被这些提问引用」保持同一口径。
    runs = (
        await session.execute(
            select(Run).where(Run.course_id == course_id, Run.status == "completed")
        )
    ).scalars().all()
    doc_hits: Counter[str] = Counter()
    for run in runs:
        doc_ids = {
            str(citation.get("document_id") or "") for citation in (run.citations or [])
        }
        for doc_id in doc_ids - {""}:
            doc_hits[doc_id] += 1
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
                "citation_count": doc_hits.get(d.id, 0),
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
    # 先按上限 +1 字节读，避免超大文件在校验前就整包进内存
    limit = settings.max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise _fail(413, "FILE_TOO_LARGE", f"文件超过 {limit} 字节上限")
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
    if document is None:
        raise _fail(404, "NOT_FOUND", "文档不存在")
    if document.id.startswith("doc_seed"):
        raise _fail(403, "FORBIDDEN", "预置文档不可删除")
    # 显式清理分块：历史 SQLite 库可能未开启外键，不能只依赖 ON DELETE CASCADE
    await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await session.delete(document)
    await session.commit()
    await retriever.refresh(session)
    return Response(status_code=204)


@router.get("/documents/{document_id}/chunks")
async def document_chunks(
    document_id: str,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    document = await session.get(Document, document_id)
    if document is None:
        raise _fail(404, "NOT_FOUND", "文档不存在")
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


@router.get("/documents/{document_id}/citations")
async def document_citations(
    document_id: str, session: SessionDep, limit: int = Query(default=4, ge=1, le=20)
) -> dict:
    """这份材料被哪些提问引用过：按分块统计命中次数，并列出最近被引用的提问。"""
    document = await session.get(Document, document_id)
    if document is None:
        raise _fail(404, "NOT_FOUND", "文档不存在")

    runs = (
        await session.execute(
            select(Run)
            .where(Run.course_id == COURSE_ID, Run.status == "completed")
            .order_by(Run.created_at.desc())
        )
    ).scalars().all()

    chunk_hits: Counter[str] = Counter()
    run_total = 0
    seen_questions: set[str] = set()
    items: list[dict] = []
    for run in runs:
        hits = [
            citation
            for citation in (run.citations or [])
            if str(citation.get("document_id") or "") == document_id
        ]
        if not hits:
            continue
        run_total += 1
        for citation in hits:
            chunk_id = str(citation.get("chunk_id") or "")
            if chunk_id:
                chunk_hits[chunk_id] += 1
        if len(items) < limit:
            question = (run.question or "").strip()
            if question in seen_questions:
                continue
            seen_questions.add(question)
            best = max(hits, key=lambda citation: float(citation.get("score") or 0))
            items.append(
                {
                    "run_id": run.id,
                    "session_id": run.session_id,
                    "question": run.question,
                    "created_at": iso(run.created_at),
                    "chunk_id": best.get("chunk_id"),
                    "locator": best.get("locator"),
                    "excerpt": best.get("excerpt"),
                    "score": best.get("score"),
                    "hit_chunks": len({str(citation.get("chunk_id") or "") for citation in hits}),
                }
            )

    return {
        "document_id": document.id,
        "title": document.title,
        "run_total": run_total,
        "chunk_total": len(chunk_hits),
        "chunk_counts": dict(chunk_hits),
        "items": items,
    }


@router.post("/search")
async def search(payload: SearchRequest, session: SessionDep) -> dict:
    # 当前只加载一门课程：显式校验，避免接收后忽略导致多课程时跨课召回
    if payload.course_id != COURSE_ID:
        raise _fail(404, "NOT_FOUND", "课程不存在")
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
async def create_session(payload: SessionCreate, request: Request, session: SessionDep) -> dict:
    user_key = ensure_owner(current_account(request), payload.user_key)
    chat = ChatSession(
        id=new_id(),
        course_id=payload.course_id,
        title=payload.title or "新会话",
        user_key=user_key,
    )
    session.add(chat)
    await session.commit()
    return {"id": chat.id, "course_id": chat.course_id, "title": chat.title}


@router.get("/chat-sessions")
async def list_sessions(
    session: SessionDep,
    course_id: str | None = None,
    user_key: str = Depends(scoped_user_key),
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
    user_key: str = Depends(scoped_user_key),
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
async def create_run(session_id: str, payload: RunCreate, request: Request, session: SessionDep) -> dict:
    user_key = ensure_owner(current_account(request), payload.user_key)
    chat = await session.get(ChatSession, session_id)
    if chat is None or _owner_of(chat) != user_key:
        raise _fail(404, "NOT_FOUND", "会话不存在")
    run = Run(
        id=new_id(),
        session_id=session_id,
        course_id=chat.course_id,
        mode=payload.mode,
        user_key=chat.user_key or user_key,
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


@router.get("/runs/pending")
async def pending_runs(
    session: SessionDep,
    course_id: str = COURSE_ID,
    user_key: str = Depends(scoped_user_key),
) -> dict:
    """等待当前用户审批的运行，工作台可直接批准/拒绝，不必跳到问答页。

    注意：本路由必须定义在 `/runs/{run_id}` 之前，否则 "pending" 会被当成 run_id。
    """
    runs = (
        await session.execute(
            select(Run)
            .where(
                Run.course_id == course_id,
                Run.user_key == user_key,
                Run.status == "waiting_user",
            )
            .order_by(Run.created_at.desc())
        )
    ).scalars().all()
    session_rows = (
        await session.execute(select(ChatSession).where(ChatSession.course_id == course_id))
    ).scalars().all()
    titles = {row.id: row.title for row in session_rows}
    items = [
        {
            "run_id": run.id,
            "session_id": run.session_id,
            "session_title": titles.get(run.session_id, ""),
            "question": run.question,
            "pending_input": run.pending_input,
            "created_at": iso(run.created_at),
        }
        for run in runs
    ]
    return {"user_key": user_key, "total": len(items), "items": items}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    session: SessionDep,
    user_key: str = Depends(scoped_user_key),
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
    user_key: str = Depends(scoped_user_key),
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
    user_key: str = Depends(scoped_user_key),
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
    user_key: str = Depends(scoped_user_key),
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
    user_key: str = Depends(scoped_user_key),
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
async def analytics_overview(
    request: Request, session: SessionDep, course_id: str = COURSE_ID
) -> dict:
    """课程使用统计：教师看全班，学生只看自己的 run 记录。"""
    account = current_account(request)
    stmt = select(Run).where(Run.course_id == course_id)
    if account is not None and account.role != "teacher":
        stmt = stmt.where(Run.user_key == account.user_key)
    runs = (await session.execute(stmt)).scalars().all()
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
    # 章节归因优先按 document_id 映射；标题只在旧引用缺 id 时兜底，避免同名文档串章节
    chapter_of_doc = {doc.id: doc.chapter_id for doc in documents}
    chapter_of_title = {doc.title: doc.chapter_id for doc in documents}
    chapter_hits: Counter[str] = Counter()
    doc_hits: Counter[str] = Counter()
    for run in runs:
        for citation in run.citations or []:
            title = str(citation.get("title") or "")
            doc_hits[title] += 1
            document_id = str(citation.get("document_id") or "")
            chapter_id = chapter_of_doc.get(document_id) or chapter_of_title.get(title)
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
    user_key: str | None = Field(default=None, max_length=64)


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
    concept_ids: str | None = None,
    question_ids: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    shuffle: bool = True,
) -> dict:
    stmt = select(Question).where(Question.course_id == course_id)
    ordered_ids: list[str] | None = None
    if question_ids:
        # 错题重做：按指定题目组卷，排序以传入顺序为准，更符合复习预期
        ids = [item.strip() for item in question_ids.split(",") if item.strip()][:30]
        if ids:
            stmt = stmt.where(Question.id.in_(ids))
            ordered_ids = ids
            shuffle = False
    if chapter_id:
        stmt = stmt.where(Question.chapter_id == chapter_id)
    if concept_id:
        stmt = stmt.where(Question.concept_id == concept_id)
    if concept_ids:
        ids = [item.strip() for item in concept_ids.split(",") if item.strip()]
        if ids:
            stmt = stmt.where(Question.concept_id.in_(ids))
    questions = (await session.execute(stmt.order_by(Question.sort_order))).scalars().all()
    if ordered_ids is not None:
        rank = {question_id: index for index, question_id in enumerate(ordered_ids)}
        questions = sorted(questions, key=lambda question: rank.get(question.id, len(rank)))
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


@router.get("/analytics/students")
async def analytics_students(request: Request, session: SessionDep, course_id: str = COURSE_ID) -> dict:
    """教师端学生名单：从作答记录聚合作答量、正确率与最近活跃时间。"""
    require_teacher(current_account(request))
    attempts = (
        await session.execute(select(Attempt).where(Attempt.course_id == course_id))
    ).scalars().all()
    buckets: dict[str, dict[str, object]] = {}
    for attempt in attempts:
        bucket = buckets.setdefault(
            attempt.user_key,
            {"attempts": 0, "correct": 0, "questions": set(), "last_at": None},
        )
        bucket["attempts"] = int(bucket["attempts"]) + 1  # type: ignore[arg-type]
        if attempt.is_correct:
            bucket["correct"] = int(bucket["correct"]) + 1  # type: ignore[arg-type]
        questions = bucket["questions"]
        if isinstance(questions, set):
            questions.add(attempt.question_id)
        last_at = bucket["last_at"]
        if attempt.created_at and (last_at is None or attempt.created_at > last_at):
            bucket["last_at"] = attempt.created_at

    items = [
        {
            "user_key": user_key,
            "attempts": int(bucket["attempts"]),  # type: ignore[arg-type]
            "correct": int(bucket["correct"]),  # type: ignore[arg-type]
            "rate": round(int(bucket["correct"]) * 100 / int(bucket["attempts"]))
            if int(bucket["attempts"])
            else 0,
            "questions": len(bucket["questions"]) if isinstance(bucket["questions"], set) else 0,
            "last_at": iso(bucket["last_at"]) if bucket["last_at"] else None,
        }
        for user_key, bucket in buckets.items()
    ]
    items.sort(key=lambda item: (-item["attempts"], item["user_key"]))
    return {"course_id": course_id, "total": len(items), "items": items}


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
async def create_attempt(payload: AttemptIn, request: Request, session: SessionDep) -> dict:
    user_key = ensure_owner(current_account(request), payload.user_key)
    question = await session.get(Question, payload.question_id)
    if question is None or question.course_id != COURSE_ID:
        raise _fail(404, "QUESTION_NOT_FOUND", "题目不存在")
    summary = answer_summary(question.type, payload.answer, question.answer)
    attempt = Attempt(
        course_id=COURSE_ID,
        question_id=question.id,
        user_key=user_key,
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
    user_key: str = Depends(scoped_user_key),
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
    # 错得多的优先；同次数时最近错的排前面（此前是升序，实际把最早错的顶上来）
    items.sort(key=lambda item: (item["wrong"], item["last_wrong_at"] or ""), reverse=True)

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


@router.get("/learning/trend")
async def learning_trend(
    session: SessionDep,
    user_key: str = Depends(scoped_user_key),
    course_id: str = COURSE_ID,
    days: int = Query(14, ge=7, le=60),
) -> dict:
    """按天统计作答与正确率，并给出本周 / 上周对比；学习报告的趋势线用这份数据。"""
    attempts = (
        await session.execute(
            select(Attempt).where(Attempt.course_id == course_id, Attempt.user_key == user_key)
        )
    ).scalars().all()
    today = utcnow().date()
    by_day: dict[str, dict[str, int]] = {}
    for attempt in attempts:
        if not attempt.created_at:
            continue
        day = attempt.created_at.date().isoformat()
        bucket = by_day.setdefault(day, {"attempts": 0, "correct": 0})
        bucket["attempts"] += 1
        if attempt.is_correct:
            bucket["correct"] += 1

    items = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        bucket = by_day.get(day, {"attempts": 0, "correct": 0})
        items.append(
            {
                "date": day,
                "attempts": bucket["attempts"],
                "correct": bucket["correct"],
                "rate": round(bucket["correct"] * 100 / bucket["attempts"]) if bucket["attempts"] else 0,
            }
        )

    def summarize(rows: list[dict]) -> dict:
        total = sum(row["attempts"] for row in rows)
        correct = sum(row["correct"] for row in rows)
        return {
            "attempts": total,
            "correct": correct,
            "rate": round(correct * 100 / total) if total else 0,
            "days": sum(1 for row in rows if row["attempts"]),
        }

    this_week = summarize(items[-7:])
    last_week = summarize(items[:-7])
    return {
        "user_key": user_key,
        "days": days,
        "items": items,
        "this_week": this_week,
        "last_week": last_week,
        "rate_delta": this_week["rate"] - last_week["rate"],
        "attempt_delta": this_week["attempts"] - last_week["attempts"],
    }


@router.get("/learning/next")
async def learning_next(
    session: SessionDep,
    course_id: str = COURSE_ID,
    user_key: str = Depends(scoped_user_key),
    limit: int = Query(3, ge=1, le=6),
) -> dict:
    """按掌握度与先修关系给出「下一步做什么」；只做建议，不改任何数据。"""
    profile = await build_profile(session, user_key, course_id)
    chapters = {
        chapter.id: chapter
        for chapter in (await session.execute(select(Chapter).where(Chapter.course_id == course_id))).scalars().all()
    }
    edges = (
        await session.execute(
            select(ConceptEdge).where(
                ConceptEdge.course_id == course_id, ConceptEdge.kind == "prerequisite"
            )
        )
    ).scalars().all()
    prereq = {edge.target_id: edge.source_id for edge in edges}
    concepts = {item["concept_id"]: item for item in profile["concepts"]}

    def make_task(item: dict, reason: str, action: str | None = None) -> dict:
        chapter = chapters.get(item["chapter_id"] or "")
        return {
            "concept_id": item["concept_id"],
            "title": item["title"],
            "chapter_id": item["chapter_id"],
            "chapter_title": chapter.title if chapter else "未挂章节",
            "state": item["state"],
            "rate": item["rate"],
            "attempts": item["attempts"],
            "action": action
            or {"weak": "review", "no_data": "learn", "normal": "practice"}[item["state"]],
            "reason": reason,
            "minutes": {"weak": 15, "no_data": 12, "normal": 10}[item["state"]],
        }

    def reason_for(item: dict) -> str:
        if item["state"] == "weak":
            return f"正确率 {item['rate']}%"
        if item["state"] == "no_data":
            return "还没练过"
        return f"正确率 {item['rate']}%"

    # 作业节点：未提交的按截止时间排最前，已批低分的转成概念补练
    now = utcnow()
    assignments = (
        await session.execute(select(Assignment).where(Assignment.course_id == course_id))
    ).scalars().all()
    items_by_assignment: dict[str, list[AssignmentItem]] = {}
    if assignments:
        for row in (
            await session.execute(
                select(AssignmentItem).where(
                    AssignmentItem.assignment_id.in_([assignment.id for assignment in assignments])
                )
            )
        ).scalars().all():
            items_by_assignment.setdefault(row.assignment_id, []).append(row)

    subs = (
        await session.execute(
            select(Submission).where(Submission.course_id == course_id, Submission.user_key == user_key)
        )
    ).scalars().all()
    subs_by_assignment = {sub.assignment_id: sub for sub in subs}
    sub_rows_by_submission: dict[str, list[SubmissionItem]] = {}
    if subs:
        for row in (
            await session.execute(
                select(SubmissionItem).where(
                    SubmissionItem.submission_id.in_([sub.id for sub in subs])
                )
            )
        ).scalars().all():
            sub_rows_by_submission.setdefault(row.submission_id, []).append(row)

    assignment_tasks: list[dict] = []
    for assignment in assignments:
        if assignment.status != "published":
            continue
        item_rows = items_by_assignment.get(assignment.id, [])
        mine = subs_by_assignment.get(assignment.id)

        if mine is None:
            overdue = bool(assignment.due_at and assignment.due_at < now)
            soon = bool(assignment.due_at and assignment.due_at - now <= timedelta(days=7))
            if not (overdue or soon):
                continue
            if not assignment.due_at:
                reason = "未提交"
            elif overdue:
                reason = "已逾期 · 未提交"
            else:
                # 按本地日期算"今天/明天"，避免 UTC 存储导致文案差一天
                local_due = assignment.due_at.replace(tzinfo=UTC).astimezone()
                days_left = (local_due.date() - datetime.now(UTC).astimezone().date()).days
                if days_left <= 0:
                    reason = "今天截止 · 未提交"
                elif days_left == 1:
                    reason = "明天截止 · 未提交"
                else:
                    reason = f"{local_due.month} 月 {local_due.day} 日截止 · 未提交"
            assignment_tasks.append(
                {
                    "kind": "assignment",
                    "assignment_id": assignment.id,
                    "concept_id": None,
                    "title": assignment.title,
                    "chapter_id": assignment.chapter_id,
                    "chapter_title": chapters.get(assignment.chapter_id or "").title
                    if chapters.get(assignment.chapter_id or "")
                    else "作业",
                    "state": "todo",
                    "rate": 0,
                    "attempts": 0,
                    "action": "submit",
                    "reason": reason,
                    "minutes": min(30, max(10, len(item_rows) * 5)),
                    "due_at": iso(assignment.due_at),
                    "priority": 0,
                    "overdue": overdue,
                }
            )
            continue

        if mine.status != "graded" or not mine.max_score:
            continue
        rate = round(mine.score * 100 / mine.max_score)
        if rate >= 60:
            continue

        items_map = {row.id: row for row in item_rows}
        weak_concepts: list[str] = []
        for sub_row in sub_rows_by_submission.get(mine.id, []):
            item = items_map.get(sub_row.item_id)
            if not item or not item.concept_id:
                continue
            if sub_row.max_score and sub_row.score * 100 / sub_row.max_score < 60:
                weak_concepts.append(item.concept_id)
        for concept_id in list(dict.fromkeys(weak_concepts))[:2]:
            concept = concepts.get(concept_id)
            if concept is None:
                continue
            assignment_tasks.append(
                {
                    "kind": "concept",
                    "assignment_id": assignment.id,
                    "concept_id": concept_id,
                    "title": concept["title"],
                    "chapter_id": concept.get("chapter_id"),
                    "chapter_title": chapters.get(concept.get("chapter_id") or "").title
                    if chapters.get(concept.get("chapter_id") or "")
                    else "作业",
                    "state": concept["state"],
                    "rate": concept["rate"],
                    "attempts": concept["attempts"],
                    "action": "practice",
                    "reason": f"《{assignment.title}》得分率 {rate}% · 补练",
                    "minutes": 15,
                    "due_at": None,
                    "priority": 1,
                    "overdue": False,
                }
            )

    order = {"weak": 0, "no_data": 1, "normal": 2}
    candidates = sorted(
        (item for item in profile["concepts"] if item["state"] in order),
        key=lambda item: (order[item["state"]], item["rate"], -item["attempts"]),
    )

    tasks: list[dict] = []
    picked: set[str] = set()

    def push(entry: dict, reason: str, action: str | None = None) -> bool:
        """按 limit 收口：先修与后继共用一个额度，不允许溢出。"""
        if len(tasks) >= limit:
            return False
        tasks.append(make_task(entry, reason, action))
        picked.add(entry["concept_id"])
        return True

    for item in candidates:
        if len(tasks) >= limit:
            break
        if item["concept_id"] in picked:
            continue
        # 先修没掌握时，把它排到前面：否则直接补后继概念会很吃力
        source_id = prereq.get(item["concept_id"])
        source = concepts.get(source_id or "")
        if source and source["state"] in ("weak", "no_data") and source["concept_id"] not in picked:
            if not push(
                source,
                f"「{item['title']}」的先修",
                action="review" if source["state"] == "weak" else "learn",
            ):
                break
        if not push(item, reason_for(item)):
            break

    recent = (
        await session.execute(
            select(func.count(Attempt.id)).where(
                Attempt.course_id == course_id,
                Attempt.user_key == user_key,
                Attempt.created_at >= utcnow() - timedelta(days=7),
            )
        )
    ).scalar_one()

    chapter_rows = []
    for chapter in chapters.values():
        own = [item for item in profile["concepts"] if item["chapter_id"] == chapter.id]
        attempts = sum(item["attempts"] for item in own)
        correct = sum(item["correct"] for item in own)
        chapter_rows.append(
            {
                "chapter_id": chapter.id,
                "title": chapter.title,
                "concepts": len(own),
                "covered": sum(1 for item in own if item["attempts"]),
                "attempts": attempts,
                "rate": round(correct * 100 / attempts) if attempts else 0,
            }
        )
    chapter_rows.sort(key=lambda row: row["chapter_id"])

    all_items = profile["concepts"]
    for task in tasks:
        task.setdefault("kind", "concept")
        task.setdefault("priority", {"weak": 2, "no_data": 3, "normal": 4}.get(task["state"], 4))
        task.setdefault("due_at", None)
        task.setdefault("assignment_id", None)
        task.setdefault("overdue", False)

    # 概念任务保留原有生成顺序（其中已含先修优先与 state 优先），作业任务整体排在前面
    assignment_tasks.sort(key=lambda task: (task["priority"], task.get("due_at") or "9999"))
    ordered = assignment_tasks + tasks

    week: list[dict] = []
    minutes = 0
    rest_index = len(ordered)
    for index, task in enumerate(ordered):
        if len(week) >= 4:
            rest_index = index
            break
        if week and minutes + task["minutes"] > 90:
            rest_index = index
            break
        week.append(task)
        minutes += task["minutes"]
    rest = ordered[rest_index : rest_index + 4]

    if week and week[0]["kind"] == "assignment":
        goal = f"先把《{week[0]['title']}》交掉"
        if len(week) > 1:
            goal += f"，再补{week[1]['title']}"
    elif week:
        goal = f"先补{week[0]['title']}"
    else:
        goal = "暂无待办"

    return {
        "user_key": user_key,
        "summary": {
            # 注意：profile 里的 weak/untried/strong 已按注入上限截断，这里要按全量明细统计
            "weak": sum(1 for item in all_items if item["state"] == "weak"),
            "untried": sum(1 for item in all_items if not item["attempts"]),
            "mastered": sum(1 for item in all_items if item["state"] == "mastered"),
            "covered": profile["covered"],
            "accuracy": profile["accuracy"],
            "total": len(all_items),
        },
        "recent_attempts": int(recent),
        "tasks": week,
        "stages": [
            {
                "key": "this_week",
                "title": "本周",
                "goal": goal[:48],
                "minutes": minutes,
                "tasks": week,
            },
            {
                "key": "next",
                "title": "接下来",
                "goal": "",
                "minutes": sum(task["minutes"] for task in rest),
                "tasks": rest,
            },
        ],
        "chapters": chapter_rows,
    }


class AssignmentItemIn(BaseModel):
    type: str = "short"
    stem: str = Field(min_length=1, max_length=4000)
    reference: str = Field(default="", max_length=4000)
    rubric: list[dict] = Field(default_factory=list)
    score: int = Field(default=10, ge=1, le=100)
    concept_id: str | None = Field(default=None, max_length=36)
    difficulty: str = "medium"


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    chapter_id: str | None = Field(default=None, max_length=36)
    due_at: datetime | None = None
    status: str = "published"
    items: list[AssignmentItemIn]


class SubmissionCreate(BaseModel):
    items: list[dict] = Field(default_factory=list)


class SubmissionItemPatch(BaseModel):
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str | None = Field(default=None, max_length=200)


def _is_teacher(request: Request) -> bool:
    """AUTH_ENABLED=false 的本地演示按教师权限处理，便于单机走通全流程。"""
    account = current_account(request)
    return account is None or account.role == "teacher"


def _require_teacher_request(request: Request) -> None:
    if not _is_teacher(request):
        raise _fail(403, "FORBIDDEN", "仅教师可操作作业")


def _parse_due(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _fail(400, "INVALID_DUE_AT", "截止时间格式应为 ISO 8601") from exc
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _validate_items(items: list[AssignmentItemIn]) -> list[dict]:
    if not items:
        raise _fail(400, "EMPTY_ASSIGNMENT", "作业至少需要一道题")
    validated: list[dict] = []
    for index, item in enumerate(items, start=1):
        if item.type not in ("short", "calc"):
            raise _fail(400, "INVALID_ITEM_TYPE", f"第 {index} 题类型只能是 short 或 calc")
        rubric = [
            {"text": str(entry.get("text", "")).strip(), "score": int(entry.get("score", 0))}
            for entry in item.rubric
            if isinstance(entry, dict)
        ]
        rubric = [entry for entry in rubric if entry["text"] and entry["score"] > 0]
        if not rubric:
            rubric = [{"text": item.reference.strip() or "完整作答", "score": item.score}]
        if sum(entry["score"] for entry in rubric) != item.score:
            raise _fail(400, "INVALID_RUBRIC", f"第 {index} 题评分要点合计应等于 {item.score} 分")
        validated.append(
            {
                "ordinal": index,
                "type": item.type,
                "stem": item.stem.strip(),
                "reference": item.reference.strip(),
                "rubric": rubric,
                "score": item.score,
                "concept_id": item.concept_id,
                "difficulty": item.difficulty,
            }
        )
    return validated


def _item_payload(row: AssignmentItem, teacher: bool) -> dict:
    payload = {
        "id": row.id,
        "ordinal": row.ordinal,
        "type": row.type,
        "stem": row.stem,
        "score": row.score,
        "concept_id": row.concept_id,
        "difficulty": row.difficulty,
    }
    if teacher:
        payload["reference"] = row.reference
        payload["rubric"] = row.rubric or []
    return payload


async def _load_assignment(session: AsyncSession, assignment_id: str) -> tuple[Assignment, list[AssignmentItem]]:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise _fail(404, "ASSIGNMENT_NOT_FOUND", "作业不存在")
    items = (
        await session.execute(
            select(AssignmentItem)
            .where(AssignmentItem.assignment_id == assignment_id)
            .order_by(AssignmentItem.ordinal)
        )
    ).scalars().all()
    return assignment, list(items)


def _summarize_source(sources: list[str]) -> str:
    unique = set(sources)
    if not unique:
        return "rule"
    if "teacher" in unique:
        return "teacher"
    if unique == {"llm"}:
        return "llm"
    if unique == {"rule"}:
        return "rule"
    return "mixed"


def _overall_comment(score: int, max_score: int, review_count: int, total: int) -> str:
    rate = round(score * 100 / max_score) if max_score else 0
    text = f"得分 {score}/{max_score}（{rate}%）"
    if review_count:
        text += f"，{review_count}/{total} 题待复核"
    return text[:80]


async def _persist_grade(
    session: AsyncSession,
    submission: Submission,
    items: list[AssignmentItem],
    answers: dict[str, str],
    results: list[dict],
) -> None:
    await session.execute(delete(SubmissionItem).where(SubmissionItem.submission_id == submission.id))
    for item, result in zip(items, results):
        session.add(
            SubmissionItem(
                id=new_id(),
                submission_id=submission.id,
                item_id=item.id,
                answer_text=answers.get(item.id, ""),
                score=result["score"],
                max_score=item.score,
                verdict=result["verdict"],
                feedback=result.get("feedback", ""),
                points=result.get("points", []),
                source=result.get("source", "rule"),
                needs_review=bool(result.get("needs_review")),
            )
        )
    submission.score = sum(int(result["score"]) for result in results)
    submission.max_score = sum(item.score for item in items)
    submission.source = _summarize_source([result.get("source", "rule") for result in results])
    submission.status = "graded"
    submission.graded_at = utcnow()
    submission.overall_comment = _overall_comment(
        submission.score,
        submission.max_score,
        sum(1 for result in results if result.get("needs_review")),
        len(results),
    )


async def _grade_all(items: list[AssignmentItem], answers: dict[str, str]) -> list[dict]:
    """单份作业内按 3 路并发批改；单题异常退规则，不影响其他题。"""
    semaphore = asyncio.Semaphore(3)

    async def one(item: AssignmentItem) -> dict:
        data = {
            "type": item.type,
            "stem": item.stem,
            "reference": item.reference,
            "rubric": item.rubric or [],
            "score": item.score,
        }
        async with semaphore:
            try:
                return await asyncio.wait_for(grade_item(data, answers.get(item.id, "")), timeout=40)
            except Exception:  # noqa: BLE001
                fallback = rule_grade(data, answers.get(item.id, ""))
                fallback["fallback"] = True
                return fallback

    return list(await asyncio.gather(*(one(item) for item in items)))


async def _submission_payload(session: AsyncSession, submission: Submission) -> dict:
    rows = (
        await session.execute(
            select(SubmissionItem).where(SubmissionItem.submission_id == submission.id)
        )
    ).scalars().all()
    item_rows = {
        row.id: row
        for row in (
            await session.execute(
                select(AssignmentItem).where(AssignmentItem.assignment_id == submission.assignment_id)
            )
        ).scalars().all()
    }
    ordered = sorted(rows, key=lambda row: item_rows.get(row.item_id).ordinal if row.item_id in item_rows else 0)
    return {
        "submission_id": submission.id,
        "assignment_id": submission.assignment_id,
        "user_key": submission.user_key,
        "status": submission.status,
        "score": submission.score,
        "max_score": submission.max_score,
        "source": submission.source,
        "overall_comment": submission.overall_comment,
        "error_code": submission.error_code,
        "submitted_at": iso(submission.submitted_at),
        "graded_at": iso(submission.graded_at),
        "items": [
            {
                "item_id": row.item_id,
                "ordinal": item_rows[row.item_id].ordinal if row.item_id in item_rows else 0,
                "type": item_rows[row.item_id].type if row.item_id in item_rows else "",
                "stem": item_rows[row.item_id].stem if row.item_id in item_rows else "",
                "answer": row.answer_text,
                "score": row.score,
                "max_score": row.max_score,
                "verdict": row.verdict,
                "feedback": row.feedback,
                "points": row.points or [],
                "source": row.source,
                "needs_review": row.needs_review,
            }
            for row in ordered
        ],
    }


async def _create_assignment(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    chapter_id: str | None,
    due_at: datetime | None,
    status: str,
    items: list[dict],
    created_by: str,
    source_filename: str = "",
) -> Assignment:
    if status not in ("draft", "published", "closed"):
        raise _fail(400, "INVALID_STATUS", "作业状态只能是 draft / published / closed")
    assignment = Assignment(
        id=new_id(),
        course_id=COURSE_ID,
        chapter_id=chapter_id,
        title=title.strip(),
        description=description.strip(),
        due_at=due_at,
        total_score=sum(item["score"] for item in items),
        status=status,
        created_by=created_by,
        source_filename=source_filename,
    )
    session.add(assignment)
    await session.flush()
    for item in items:
        session.add(
            AssignmentItem(
                id=new_id(),
                assignment_id=assignment.id,
                ordinal=item["ordinal"],
                type=item["type"],
                stem=item["stem"],
                reference=item["reference"],
                rubric=item["rubric"],
                score=item["score"],
                concept_id=item.get("concept_id"),
                difficulty=item.get("difficulty", "medium"),
            )
        )
    return assignment


@router.get("/assignments")
async def list_assignments(
    session: SessionDep,
    request: Request,
    course_id: str = COURSE_ID,
    user_key: str = Depends(scoped_user_key),
) -> dict:
    teacher = _is_teacher(request)
    assignments = (
        await session.execute(
            select(Assignment).where(Assignment.course_id == course_id).order_by(Assignment.created_at.desc())
        )
    ).scalars().all()
    if not assignments:
        return {"items": [], "pending": 0}

    chapters = {
        row.id: row.title
        for row in (await session.execute(select(Chapter).where(Chapter.course_id == course_id))).scalars().all()
    }
    item_counts: dict[str, int] = {}
    for assignment_id, count in (
        await session.execute(
            select(AssignmentItem.assignment_id, func.count(AssignmentItem.id))
            .where(AssignmentItem.assignment_id.in_([row.id for row in assignments]))
            .group_by(AssignmentItem.assignment_id)
        )
    ).all():
        item_counts[assignment_id] = int(count)

    submissions = (
        await session.execute(select(Submission).where(Submission.course_id == course_id))
    ).scalars().all()

    rows: list[dict] = []
    pending = 0
    for assignment in assignments:
        row = {
            "id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "chapter_id": assignment.chapter_id,
            "chapter_title": chapters.get(assignment.chapter_id or "", ""),
            "due_at": iso(assignment.due_at),
            "status": assignment.status,
            "item_count": item_counts.get(assignment.id, 0),
            "total_score": assignment.total_score,
            "source_filename": assignment.source_filename,
        }
        if teacher:
            own = [sub for sub in submissions if sub.assignment_id == assignment.id]
            graded = [sub for sub in own if sub.status == "graded"]
            row.update(
                {
                    "submitted_count": len(own),
                    "graded_count": len(graded),
                    "ungraded_count": sum(1 for sub in own if sub.status != "graded"),
                    "avg_score": round(sum(sub.score for sub in graded) / len(graded)) if graded else None,
                }
            )
        else:
            mine = next((sub for sub in submissions if sub.assignment_id == assignment.id and sub.user_key == user_key), None)
            row.update(
                {
                    "my_status": mine.status if mine else "todo",
                    "my_score": mine.score if mine and mine.status == "graded" else None,
                    "submission_id": mine.id if mine else None,
                }
            )
            if mine is None and assignment.status == "published":
                pending += 1
        rows.append(row)
    return {"items": rows, "pending": pending}


@router.post("/assignments", status_code=201)
async def create_assignment(
    payload: AssignmentCreate,
    session: SessionDep,
    request: Request,
) -> dict:
    _require_teacher_request(request)
    items = _validate_items(payload.items)
    account = current_account(request)
    assignment = await _create_assignment(
        session,
        title=payload.title,
        description=payload.description,
        chapter_id=payload.chapter_id,
        due_at=payload.due_at,
        status=payload.status,
        items=items,
        created_by=account.user_key if account else "teacher",
    )
    await session.commit()
    return {"id": assignment.id, "item_count": len(items), "total_score": assignment.total_score}


@router.post("/assignments/import", status_code=201)
async def import_assignment(
    session: SessionDep,
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    due_at: str | None = Form(default=None),
    status: str = Form(default="published"),
) -> dict:
    _require_teacher_request(request)
    filename = (file.filename or "").lower()
    if not filename.endswith((".md", ".txt")):
        raise _fail(400, "UNSUPPORTED_FILE", "只支持 .md 或 .txt")
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise _fail(413, "FILE_TOO_LARGE", "作业文件不能超过 2 MB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _fail(400, "INVALID_ENCODING", "文件需要 UTF-8 编码") from exc

    try:
        parsed = parse_assignment_text(text)
    except AssignmentImportError as exc:
        raise _fail(400, "IMPORT_PARSE_FAILED", f"第 {exc.line} 行：{exc.message}") from exc

    validated = _validate_items([AssignmentItemIn(**item) for item in parsed["items"]])
    account = current_account(request)
    assignment = await _create_assignment(
        session,
        title=(title or parsed["title"]),
        description="",
        chapter_id=None,
        due_at=_parse_due(due_at),
        status=status,
        items=validated,
        created_by=account.user_key if account else "teacher",
        source_filename=file.filename or "",
    )
    await session.commit()
    return {
        "id": assignment.id,
        "title": assignment.title,
        "item_count": len(validated),
        "total_score": assignment.total_score,
        "warnings": parsed["warnings"],
    }


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: str,
    session: SessionDep,
    request: Request,
    user_key: str = Depends(scoped_user_key),
) -> dict:
    teacher = _is_teacher(request)
    assignment, items = await _load_assignment(session, assignment_id)
    payload = {
        "id": assignment.id,
        "title": assignment.title,
        "description": assignment.description,
        "chapter_id": assignment.chapter_id,
        "due_at": iso(assignment.due_at),
        "status": assignment.status,
        "total_score": assignment.total_score,
        "item_count": len(items),
        "items": [_item_payload(item, teacher) for item in items],
    }
    if teacher:
        subs = (
            await session.execute(select(Submission).where(Submission.assignment_id == assignment.id))
        ).scalars().all()
        graded = [sub for sub in subs if sub.status == "graded"]
        payload["stats"] = {
            "submitted": len(subs),
            "graded": len(graded),
            "ungraded": len(subs) - len(graded),
            "avg_score": round(sum(sub.score for sub in graded) / len(graded)) if graded else None,
        }
    else:
        mine = (
            await session.execute(
                select(Submission).where(
                    Submission.assignment_id == assignment.id, Submission.user_key == user_key
                )
            )
        ).scalars().first()
        payload["my_submission"] = (await _submission_payload(session, mine)) if mine else None
    return payload


@router.post("/assignments/{assignment_id}/submissions", status_code=201)
async def submit_assignment(
    assignment_id: str,
    payload: SubmissionCreate,
    session: SessionDep,
    request: Request,
    user_key: str = Depends(scoped_user_key),
) -> dict:
    assignment, items = await _load_assignment(session, assignment_id)
    if assignment.status == "closed":
        raise _fail(400, "ASSIGNMENT_CLOSED", "作业已关闭，不能再提交")

    answers = {
        str(entry.get("item_id")): str(entry.get("answer") or "")[:4000]
        for entry in payload.items
        if isinstance(entry, dict) and entry.get("item_id")
    }

    existing = (
        await session.execute(
            select(Submission).where(
                Submission.assignment_id == assignment.id, Submission.user_key == user_key
            )
        )
    ).scalars().first()
    submission = existing or Submission(
        id=new_id(),
        assignment_id=assignment.id,
        course_id=assignment.course_id,
        user_key=user_key,
    )
    submission.status = "grading"
    submission.submitted_at = utcnow()
    submission.error_code = None
    session.add(submission)
    await session.flush()

    try:
        results = await asyncio.wait_for(_grade_all(items, answers), timeout=55)
    except asyncio.TimeoutError:
        results = [
            rule_grade(
                {"type": item.type, "stem": item.stem, "reference": item.reference, "rubric": item.rubric or [], "score": item.score},
                answers.get(item.id, ""),
            )
            for item in items
        ]
        for result in results:
            result["fallback"] = True

    await _persist_grade(session, submission, items, answers, results)
    await session.commit()
    return await _submission_payload(session, submission)


@router.get("/assignments/{assignment_id}/submissions")
async def list_submissions(
    assignment_id: str,
    session: SessionDep,
    request: Request,
) -> dict:
    _require_teacher_request(request)
    assignment, items = await _load_assignment(session, assignment_id)
    subs = (
        await session.execute(
            select(Submission)
            .where(Submission.assignment_id == assignment.id)
            .order_by(Submission.submitted_at.desc())
        )
    ).scalars().all()
    review_counts: dict[str, int] = {}
    for submission_id, count in (
        await session.execute(
            select(SubmissionItem.submission_id, func.count(SubmissionItem.id))
            .where(
                SubmissionItem.submission_id.in_([sub.id for sub in subs]),
                SubmissionItem.needs_review.is_(True),
            )
            .group_by(SubmissionItem.submission_id)
        )
    ).all():
        review_counts[submission_id] = int(count)
    return {
        "assignment": {
            "id": assignment.id,
            "title": assignment.title,
            "total_score": assignment.total_score,
            "item_count": len(items),
        },
        "items": [
            {
                "submission_id": sub.id,
                "user_key": sub.user_key,
                "status": sub.status,
                "score": sub.score,
                "max_score": sub.max_score,
                "source": sub.source,
                "needs_review_count": review_counts.get(sub.id, 0),
                "submitted_at": iso(sub.submitted_at),
                "graded_at": iso(sub.graded_at),
            }
            for sub in subs
        ],
    }


@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    session: SessionDep,
    request: Request,
    user_key: str = Depends(scoped_user_key),
) -> dict:
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise _fail(404, "SUBMISSION_NOT_FOUND", "提交不存在")
    if not _is_teacher(request) and submission.user_key != user_key:
        raise _fail(403, "FORBIDDEN", "只能查看自己的提交")
    return await _submission_payload(session, submission)


@router.patch("/submissions/{submission_id}/items/{item_id}")
async def patch_submission_item(
    submission_id: str,
    item_id: str,
    payload: SubmissionItemPatch,
    session: SessionDep,
    request: Request,
) -> dict:
    _require_teacher_request(request)
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise _fail(404, "SUBMISSION_NOT_FOUND", "提交不存在")
    item = await session.get(AssignmentItem, item_id)
    if item is None or item.assignment_id != submission.assignment_id:
        raise _fail(404, "ITEM_NOT_FOUND", "题目不属于该作业")
    row = (
        await session.execute(
            select(SubmissionItem).where(
                SubmissionItem.submission_id == submission.id, SubmissionItem.item_id == item_id
            )
        )
    ).scalars().first()
    if row is None:
        raise _fail(404, "NOT_SUBMITTED", "该题没有作答记录")

    if payload.score is not None:
        if payload.score > item.score:
            raise _fail(400, "SCORE_OUT_OF_RANGE", f"该题满分 {item.score} 分")
        row.score = payload.score
        row.needs_review = False
    if payload.feedback is not None:
        row.feedback = payload.feedback.strip()[:200]
    row.source = "teacher"
    row.verdict = "correct" if row.score >= item.score else ("wrong" if row.score <= 0 else "partial")

    rows = (
        await session.execute(select(SubmissionItem).where(SubmissionItem.submission_id == submission.id))
    ).scalars().all()
    submission.score = sum(entry.score for entry in rows)
    submission.max_score = sum(entry.max_score for entry in rows)
    submission.source = _summarize_source([entry.source for entry in rows])
    submission.overall_comment = _overall_comment(
        submission.score,
        submission.max_score,
        sum(1 for entry in rows if entry.needs_review),
        len(rows),
    )
    submission.graded_at = utcnow()
    await session.commit()
    return await _submission_payload(session, submission)


@router.post("/submissions/{submission_id}/regrade")
async def regrade_submission(
    submission_id: str,
    session: SessionDep,
    request: Request,
) -> dict:
    _require_teacher_request(request)
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise _fail(404, "SUBMISSION_NOT_FOUND", "提交不存在")
    _, items = await _load_assignment(session, submission.assignment_id)
    rows = (
        await session.execute(select(SubmissionItem).where(SubmissionItem.submission_id == submission.id))
    ).scalars().all()
    answers = {row.item_id: row.answer_text for row in rows}

    try:
        results = await asyncio.wait_for(_grade_all(items, answers), timeout=55)
    except asyncio.TimeoutError:
        results = [
            rule_grade(
                {"type": item.type, "stem": item.stem, "reference": item.reference, "rubric": item.rubric or [], "score": item.score},
                answers.get(item.id, ""),
            )
            for item in items
        ]
    await _persist_grade(session, submission, items, answers, results)
    await session.commit()
    return await _submission_payload(session, submission)


from app.db import SessionFactory as AsyncSessionLocal  # noqa: E402