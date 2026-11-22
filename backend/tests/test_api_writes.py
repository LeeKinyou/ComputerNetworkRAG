"""写接口契约：上传/删除、会话与运行、审批输入、练习作答。

后台执行与事件写入用桩替换，避免测试触发 LangGraph 与真实数据库。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

import app.db  # noqa: F401  先完成 db → seed 的初始化顺序
from app.config import settings
from app.models import Attempt, ChatSession, Chunk, Document, Message, Run
from app.retrieval import Retriever
from app.seed import COURSE_ID
from _support import api_harness, ensure_course, seed_course


async def insert_run(factory, *, run_id: str = "r1", status: str = "queued",
                     pending: dict | None = None, user_key: str = "demo_user") -> None:
    async with factory() as session:
        session.add(ChatSession(id="s1", course_id=COURSE_ID, title="会话", user_key=user_key))
        session.add(
            Run(
                id=run_id,
                session_id="s1",
                course_id=COURSE_ID,
                user_key=user_key,
                question="重建索引",
                status=status,
                pending_input=pending,
            )
        )
        await session.commit()


@pytest.fixture
def stub_agent(monkeypatch):
    calls: dict[str, list] = {"start": [], "emit": [], "execute": []}

    async def start_run(run_id: str):
        calls["start"].append(run_id)

    async def emit(run_id: str, event_type: str, payload: dict):
        calls["emit"].append((run_id, event_type, payload))
        return 1

    async def execute_run(run_id: str, resume: dict | None = None):
        calls["execute"].append((run_id, resume))

    monkeypatch.setattr("app.api.start_run", start_run)
    monkeypatch.setattr("app.api.emit", emit)
    monkeypatch.setattr("app.api.execute_run", execute_run)
    return calls


@pytest.fixture
def fresh_retriever(monkeypatch):
    retriever = Retriever()
    monkeypatch.setattr("app.api.retriever", retriever)
    return retriever


async def test_create_session_then_run_persists_history_and_title(stub_agent):
    async with api_harness() as (client, factory):
        created = await client.post(
            "/api/v2/chat-sessions", json={"course_id": COURSE_ID, "user_key": "demo_user"}
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        response = await client.post(
            f"/api/v2/chat-sessions/{session_id}/runs",
            json={"message": "ARP 是怎么工作的？", "mode": "agent", "user_key": "demo_user"},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert body["events_url"] == f"/api/v2/runs/{body['run_id']}/events"
        assert stub_agent["start"] == [body["run_id"]]

        async with factory() as session:
            run = await session.get(Run, body["run_id"])
            assert run.session_id == session_id
            assert run.status == "queued"
            assert run.mode == "agent"
            chat = await session.get(ChatSession, session_id)
            assert chat.title == "ARP 是怎么工作的？"
            messages = (await session.execute(select(Message))).scalars().all()
            assert [(m.role, m.content) for m in messages] == [("user", "ARP 是怎么工作的？")]


async def test_create_run_cannot_use_another_users_session(stub_agent):
    async with api_harness() as (client, factory):
        async with factory() as session:
            session.add(ChatSession(id="s_stu", course_id=COURSE_ID, title="林晓", user_key="stu_lin"))
            await session.commit()

        response = await client.post(
            "/api/v2/chat-sessions/s_stu/runs",
            json={"message": "偷看别人的会话", "user_key": "demo_user"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
        assert stub_agent["start"] == []


async def test_create_run_rejects_blank_message(stub_agent):
    async with api_harness() as (client, factory):
        async with factory() as session:
            session.add(ChatSession(id="s1", course_id=COURSE_ID, title="会话", user_key="demo_user"))
            await session.commit()

        response = await client.post(
            "/api/v2/chat-sessions/s1/runs", json={"message": "", "user_key": "demo_user"}
        )
        assert response.status_code == 422


async def test_submit_input_requires_matching_pending_id(stub_agent):
    async with api_harness() as (client, factory):
        await insert_run(factory, status="waiting_user", pending={"input_id": "apv_1", "kind": "approval"})

        response = await client.post(
            "/api/v2/runs/r1/inputs",
            params={"user_key": "demo_user"},
            json={"input_id": "apv_other", "approved": True},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "RUN_NOT_WAITING"
        assert stub_agent["execute"] == []

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "waiting_user"


async def test_submit_input_resumes_waiting_run(stub_agent):
    async with api_harness() as (client, factory):
        await insert_run(factory, status="waiting_user", pending={"input_id": "apv_1", "kind": "approval"})

        response = await client.post(
            "/api/v2/runs/r1/inputs",
            params={"user_key": "demo_user"},
            json={"input_id": "apv_1", "approved": True},
        )
        assert response.status_code == 202
        assert response.json() == {"run_id": "r1", "status": "running"}
        assert stub_agent["execute"] == [("r1", {"approved": True})]

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "running"
            assert run.pending_input == {"input_id": "apv_1", "kind": "approval"}


async def test_cancel_marks_run_and_emits_event(stub_agent):
    async with api_harness() as (client, factory):
        await insert_run(factory, status="queued")

        response = await client.post("/api/v2/runs/r1/cancel", params={"user_key": "demo_user"})
        assert response.status_code == 200
        assert response.json() == {"run_id": "r1", "status": "cancelled", "cancel_requested": True}
        assert stub_agent["emit"] == [("r1", "run.cancelled", {"status": "cancelled"})]

        async with factory() as session:
            run = await session.get(Run, "r1")
            assert run.status == "cancelled"
            assert run.pending_input is None


async def test_cancel_is_noop_for_terminal_run(stub_agent):
    async with api_harness() as (client, factory):
        await insert_run(factory, status="completed")

        response = await client.post("/api/v2/runs/r1/cancel", params={"user_key": "demo_user"})
        assert response.status_code == 200
        assert response.json() == {"run_id": "r1", "status": "completed", "cancel_requested": False}
        assert stub_agent["emit"] == []


async def test_upload_markdown_document_and_search_it(stub_agent, fresh_retriever):
    async with api_harness() as (client, factory):
        await ensure_course(factory)
        content = "# 第 4 章 网络层\n\nIPv4 地址由网络位与主机位组成，掩码决定边界。\n".encode("utf-8")
        response = await client.post(
            f"/api/v2/courses/{COURSE_ID}/documents",
            files={"file": ("custom.md", content, "text/markdown")},
            data={"title": "自建讲义", "chapter_id": "ch2"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "自建讲义"
        assert body["status"] == "ready"
        assert body["chunk_count"] == 1

        async with factory() as session:
            document = await session.get(Document, body["id"])
            assert document.chapter_id == "ch2"
            assert document.size == len(content)
            chunks = (
                await session.execute(select(Chunk).where(Chunk.document_id == body["id"]))
            ).scalars().all()
            assert len(chunks) == 1
            assert chunks[0].section_path == ["第 4 章 网络层"]

        search = await client.post("/api/v2/search", json={"query": "IPv4 掩码", "top_k": 2})
        assert search.status_code == 200
        ids = {item["document_id"] for item in search.json()["items"]}
        assert body["id"] in ids


async def test_upload_works_with_foreign_keys_enabled(fresh_retriever):
    """生产 SQLite 开启了外键：上传必须在同一事务里先落文档行再插分块。"""
    async with api_harness(foreign_keys=True) as (client, factory):
        await ensure_course(factory)
        response = await client.post(
            f"/api/v2/courses/{COURSE_ID}/documents",
            files={"file": ("fk.md", "# 标题\n\n子网掩码决定网络地址。".encode(), "text/markdown")},
        )
        assert response.status_code == 201
        assert response.json()["chunk_count"] >= 1


@pytest.mark.parametrize(
    "filename, content, code, message_part",
    [
        ("slides.key", b"binary", "UNSUPPORTED_FILE_TYPE", "格式"),
        ("empty.txt", b"", "VALIDATION_ERROR", "为空"),
    ],
)
async def test_upload_rejects_bad_files(stub_agent, fresh_retriever, filename, content, code, message_part):
    async with api_harness() as (client, factory):
        response = await client.post(
            f"/api/v2/courses/{COURSE_ID}/documents",
            files={"file": (filename, content, "application/octet-stream")},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == code
        assert message_part in response.json()["error"]["message"]

        async with factory() as session:
            assert (await session.execute(select(Document))).scalars().all() == []


async def test_upload_rejects_oversize_file(monkeypatch, stub_agent, fresh_retriever):
    async with api_harness() as (client, factory):
        monkeypatch.setattr(settings, "max_upload_bytes", 8)
        response = await client.post(
            f"/api/v2/courses/{COURSE_ID}/documents",
            files={"file": ("big.md", b"x" * 20, "text/markdown")},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_delete_uploaded_document_removes_chunks_and_index(stub_agent, fresh_retriever):
    async with api_harness() as (client, factory):
        await ensure_course(factory)
        uploaded = await client.post(
            f"/api/v2/courses/{COURSE_ID}/documents",
            files={"file": ("custom.md", "# 标题\n\n子网掩码决定网络地址。".encode(), "text/markdown")},
        )
        document_id = uploaded.json()["id"]

        deleted = await client.delete(f"/api/v2/documents/{document_id}")
        assert deleted.status_code == 204

        async with factory() as session:
            assert await session.get(Document, document_id) is None
            chunks = (
                await session.execute(select(Chunk).where(Chunk.document_id == document_id))
            ).scalars().all()
            assert chunks == []

        search = await client.post("/api/v2/search", json={"query": "子网掩码"})
        assert search.json()["items"] == []


async def test_seed_document_is_protected_from_deletion(stub_agent):
    async with api_harness() as (client, factory):
        await ensure_course(factory)
        async with factory() as session:
            session.add(
                Document(id="doc_seed_01", course_id=COURSE_ID, chapter_id="ch2", title="预置讲义",
                         filename="seed.md", mime="text/markdown", size=10, chunk_count=1)
            )
            await session.commit()

        response = await client.delete("/api/v2/documents/doc_seed_01")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_delete_missing_document_returns_404(stub_agent):
    """删除不存在的文档应与其他按 id 读取的接口一致：404 而不是“预置文档不可删除”。"""
    async with api_harness() as (client, factory):
        response = await client.delete("/api/v2/documents/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_document_chunks_of_missing_document_returns_404(stub_agent):
    async with api_harness() as (client, factory):
        response = await client.get("/api/v2/documents/does-not-exist/chunks")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_practice_attempt_grades_and_returns_explanation(stub_agent):
    async with api_harness() as (client, factory):
        await seed_course(factory)

        response = await client.post(
            "/api/v2/practice/attempts",
            json={"question_id": "q_arp", "answer": " b ", "user_key": "demo_user"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["correct"] is True
        assert body["given"] == "B"
        assert body["expected"] == "B"
        assert body["explanation"] == "ARP 负责地址解析。"
        assert body["stats"] == {"total": 1, "correct": 1, "rate": 100}

        async with factory() as session:
            attempt = (await session.execute(select(Attempt))).scalars().one()
            assert attempt.chapter_id == "ch2"


async def test_practice_attempt_rejects_unknown_question(stub_agent):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        response = await client.post(
            "/api/v2/practice/attempts", json={"question_id": "q_missing", "answer": "A"}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "QUESTION_NOT_FOUND"


async def test_wrongbook_moves_question_out_after_correct_retry(stub_agent):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        for answer in ("C", "D"):
            await client.post("/api/v2/practice/attempts", json={"question_id": "q_arp", "answer": answer})

        wrong = await client.get("/api/v2/practice/wrongbook", params={"user_key": "demo_user"})
        assert wrong.status_code == 200
        body = wrong.json()
        assert body["unresolved"] == 1
        assert body["items"][0]["wrong"] == 2
        assert body["items"][0]["attempts"] == 2
        assert body["groups"][0]["title"] == "ARP"

        correct = await client.post("/api/v2/practice/attempts", json={"question_id": "q_arp", "answer": "B"})
        assert correct.json()["correct"] is True

        solved = await client.get("/api/v2/practice/wrongbook", params={"user_key": "demo_user"})
        body = solved.json()
        assert body["unresolved"] == 0
        assert body["solved"] == 1
        assert body["items"] == []


async def test_attempts_are_scoped_by_user(stub_agent):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await client.post("/api/v2/practice/attempts", json={"question_id": "q_arp", "answer": "B", "user_key": "stu_lin"})

        mine = await client.get("/api/v2/practice/stats", params={"user_key": "demo_user"})
        assert mine.json()["total"] == 0
        theirs = await client.get("/api/v2/practice/stats", params={"user_key": "stu_lin"})
        assert theirs.json()["total"] == 1
