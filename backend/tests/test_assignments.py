"""作业接口契约：创建/导入、学生提交与批改、教师复核、权限隔离、幂等。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.util import utcnow
from _support import api_harness, seed_course

ACCOUNTS = (
    "teacher:teacher:teach-pass;"
    "demo_user:student:demo-pass;"
    "stu_lin:student:lin-pass"
)

ITEMS = [
    {
        "type": "short",
        "stem": "TCP 第三次握手的 ACK 作用是什么？",
        "reference": "客户端确认收到 SYN+ACK，证明通道可用，并同步序号。",
        "rubric": [
            {"text": "确认接收能力与服务端发送通道", "score": 4},
            {"text": "同步并确认序号", "score": 3},
            {"text": "避免历史重复连接", "score": 3},
        ],
        "score": 10,
        "concept_id": "c_tcp",
    },
    {
        "type": "calc",
        "stem": "192.168.10.0/27 可用主机数？",
        "reference": "块大小 32，可用主机 30 个。",
        "rubric": [
            {"text": "可用主机 30 个", "score": 6},
            {"text": "块大小 32", "score": 4},
        ],
        "score": 10,
        "concept_id": "c_arp",
    },
]

GOOD_ANSWERS = [
    "客户端确认收到了服务端的 SYN+ACK，证明确认接收能力与服务端发送通道可用，并同步并确认序号，避免历史重复连接。",
    "/27 块大小 32，去掉网络与广播地址，可用主机 30 个。",
]


@pytest.fixture
def no_llm(monkeypatch):
    """强制走规则批改，保证用例确定、离线可跑。"""
    monkeypatch.setattr(settings, "llm_api_key", "")


@pytest.fixture
def auth_on():
    original = settings.auth_enabled
    original_accounts = settings.auth_accounts
    settings.auth_enabled = True
    settings.auth_accounts = ACCOUNTS
    try:
        yield
    finally:
        settings.auth_enabled = original
        settings.auth_accounts = original_accounts


async def login(client, username: str, password: str) -> None:
    response = await client.post("/api/v2/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


async def create_assignment(client, *, status: str = "published") -> dict:
    response = await client.post(
        "/api/v2/assignments",
        json={
            "title": "第 3 周作业",
            "chapter_id": "ch2",
            "status": status,
            "due_at": (utcnow() + timedelta(days=1)).isoformat(),
            "items": ITEMS,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_create_submit_and_grade_roundtrip(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        created = await create_assignment(client)
        assert created["total_score"] == 20

        detail = await client.get(f"/api/v2/assignments/{created['id']}")
        assert detail.status_code == 200
        body = detail.json()
        assert len(body["items"]) == 2
        # 关闭鉴权的本地演示按教师视角返回，含参考答案
        assert body["items"][0]["reference"]

        item_ids = [item["id"] for item in body["items"]]
        submit = await client.post(
            f"/api/v2/assignments/{created['id']}/submissions",
            json={"items": [{"item_id": item_ids[0], "answer": GOOD_ANSWERS[0]},
                            {"item_id": item_ids[1], "answer": GOOD_ANSWERS[1]}]},
        )
        assert submit.status_code == 201
        result = submit.json()
        assert result["status"] == "graded"
        assert result["score"] == 20
        assert result["max_score"] == 20
        assert result["source"] in ("rule", "mixed")
        assert len(result["items"]) == 2
        assert all(item["points"] for item in result["items"])

        # 重复提交：复用同一条 submission，不新增记录
        again = await client.post(
            f"/api/v2/assignments/{created['id']}/submissions",
            json={"items": [{"item_id": item_ids[0], "answer": "不知道"}]},
        )
        assert again.status_code == 201
        assert again.json()["submission_id"] == result["submission_id"]
        assert again.json()["score"] < 20

        listing = await client.get("/api/v2/assignments")
        assert listing.status_code == 200
        assert any(row["id"] == created["id"] for row in listing.json()["items"])


async def test_teacher_patch_recalculates_total(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        created = await create_assignment(client)
        detail = (await client.get(f"/api/v2/assignments/{created['id']}")).json()
        item_ids = [item["id"] for item in detail["items"]]
        submission = (
            await client.post(
                f"/api/v2/assignments/{created['id']}/submissions",
                json={"items": [{"item_id": item_ids[0], "answer": "不知道"}]},
            )
        ).json()
        assert submission["score"] == 0

        patch = await client.patch(
            f"/api/v2/submissions/{submission['submission_id']}/items/{item_ids[0]}",
            json={"score": 8, "feedback": "过程基本正确，补上序号同步"},
        )
        assert patch.status_code == 200
        body = patch.json()
        assert body["score"] == 8
        assert body["source"] == "teacher"
        assert body["items"][0]["source"] == "teacher"
        assert body["items"][0]["feedback"].startswith("过程基本正确")

        over = await client.patch(
            f"/api/v2/submissions/{submission['submission_id']}/items/{item_ids[0]}",
            json={"score": 99},
        )
        assert over.status_code == 400
        assert over.json()["error"]["code"] == "SCORE_OUT_OF_RANGE"


async def test_closed_assignment_rejects_submit(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        created = await create_assignment(client, status="closed")
        response = await client.post(
            f"/api/v2/assignments/{created['id']}/submissions", json={"items": []}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "ASSIGNMENT_CLOSED"


async def test_invalid_rubric_is_rejected(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        bad = dict(ITEMS[0], rubric=[{"text": "只给一半", "score": 5}], score=10)
        response = await client.post(
            "/api/v2/assignments", json={"title": "坏作业", "items": [bad]}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_RUBRIC"


async def test_import_markdown_file(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        text = (
            "# 第 4 周作业\n\n"
            "### 题目 1 | 简答 | 10 分\n"
            "为什么需要拥塞控制？\n"
            "参考答案: 保护网络整体负载。\n"
            "评分要点: 保护接收端缓冲区=4; 面向网络整体=3; 避免崩溃=3\n\n"
            "### 题目 2 | 计算 | 10 分\n"
            "10.0.0.0/8 划分 /12 有多少子网？\n"
            "参考答案: 16 个。\n"
            "评分要点: 借 4 位=4; 16 个=4; 2^4=2\n"
        )
        response = await client.post(
            "/api/v2/assignments/import",
            files={"file": ("week4.md", text.encode("utf-8"), "text/markdown")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["item_count"] == 2
        assert body["total_score"] == 20
        assert body["warnings"] == []


async def test_import_rejects_bad_format(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        response = await client.post(
            "/api/v2/assignments/import",
            files={"file": ("bad.md", "随便写点东西".encode("utf-8"), "text/markdown")},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "IMPORT_PARSE_FAILED"


async def test_student_cannot_see_reference_or_others_submission(no_llm, auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)

        await login(client, "teacher", "teach-pass")
        created = await create_assignment(client)

        await login(client, "demo_user", "demo-pass")
        detail = await client.get(f"/api/v2/assignments/{created['id']}")
        assert detail.status_code == 200
        student_view = detail.json()
        assert all("reference" not in item and "rubric" not in item for item in student_view["items"])

        item_ids = [item["id"] for item in student_view["items"]]
        submission = (
            await client.post(
                f"/api/v2/assignments/{created['id']}/submissions",
                json={"items": [{"item_id": item_ids[0], "answer": GOOD_ANSWERS[0]}]},
            )
        ).json()

        # 自己看自己的提交可以
        own = await client.get(f"/api/v2/submissions/{submission['submission_id']}")
        assert own.status_code == 200

        # 另一个学生看别人的提交被拒
        await login(client, "stu_lin", "lin-pass")
        other = await client.get(f"/api/v2/submissions/{submission['submission_id']}")
        assert other.status_code == 403
        assert other.json()["error"]["code"] == "FORBIDDEN"

        # 学生不能建作业
        forbidden = await client.post(
            "/api/v2/assignments", json={"title": "蹭作业", "items": ITEMS}
        )
        assert forbidden.status_code == 403

        # 教师能看全班提交
        await login(client, "teacher", "teach-pass")
        roster = await client.get(f"/api/v2/assignments/{created['id']}/submissions")
        assert roster.status_code == 200
        assert [row["user_key"] for row in roster.json()["items"]] == ["demo_user"]


async def test_assignments_pending_and_learning_path(no_llm, auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)

        await login(client, "teacher", "teach-pass")
        created = await create_assignment(client)

        await login(client, "demo_user", "demo-pass")
        listing = (await client.get("/api/v2/assignments")).json()
        assert listing["pending"] == 1
        assert listing["items"][0]["my_status"] == "todo"

        path = await client.get("/api/v2/learning/next")
        assert path.status_code == 200
        body = path.json()
        assert "stages" in body
        assert [stage["key"] for stage in body["stages"]] == ["this_week", "next"]
        first = body["tasks"][0]
        assert first["kind"] == "assignment"
        assert first["assignment_id"] == created["id"]
        assert first["action"] == "submit"
        assert "截止" in first["reason"] or "逾期" in first["reason"]
        assert body["stages"][0]["goal"].startswith("先把")


async def test_status_patch_and_delete(no_llm, auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await login(client, "teacher", "teach-pass")
        created = await create_assignment(client)

        await login(client, "demo_user", "demo-pass")
        detail = (await client.get(f"/api/v2/assignments/{created['id']}")).json()
        item_id = detail["items"][0]["id"]
        await client.post(
            f"/api/v2/assignments/{created['id']}/submissions",
            json={"items": [{"item_id": item_id, "answer": "只知道一点"}]},
        )

        await login(client, "teacher", "teach-pass")
        closed = await client.patch(f"/api/v2/assignments/{created['id']}", json={"status": "closed"})
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"

        renamed = await client.patch(
            f"/api/v2/assignments/{created['id']}", json={"title": "改过名的作业"}
        )
        assert renamed.json()["title"] == "改过名的作业"

        await login(client, "demo_user", "demo-pass")
        denied = await client.post(
            f"/api/v2/assignments/{created['id']}/submissions", json={"items": []}
        )
        assert denied.status_code == 400
        assert denied.json()["error"]["code"] == "ASSIGNMENT_CLOSED"

        await login(client, "teacher", "teach-pass")
        deleted = await client.delete(f"/api/v2/assignments/{created['id']}")
        assert deleted.status_code == 204
        assert (await client.get(f"/api/v2/assignments/{created['id']}")).status_code == 404
        listing = (await client.get("/api/v2/assignments")).json()
        assert all(row["id"] != created["id"] for row in listing["items"])


async def test_draft_is_hidden_from_students(no_llm, auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await login(client, "teacher", "teach-pass")
        created = await create_assignment(client, status="draft")

        await login(client, "demo_user", "demo-pass")
        listing = (await client.get("/api/v2/assignments")).json()
        assert all(row["id"] != created["id"] for row in listing["items"])

        assert (await client.get(f"/api/v2/assignments/{created['id']}")).status_code == 404
        submit = await client.post(
            f"/api/v2/assignments/{created['id']}/submissions", json={"items": []}
        )
        assert submit.status_code == 400
        assert submit.json()["error"]["code"] == "ASSIGNMENT_NOT_PUBLISHED"

        await login(client, "teacher", "teach-pass")
        assert (await client.get(f"/api/v2/assignments/{created['id']}")).status_code == 200


async def test_naive_due_at_is_teacher_local_time(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        response = await client.post(
            "/api/v2/assignments",
            json={"title": "本地时间作业", "due_at": "2026-11-29T23:59", "items": ITEMS},
        )
        assert response.status_code == 201
        detail = (await client.get(f"/api/v2/assignments/{response.json()['id']}")).json()
        local = datetime.fromisoformat(detail["due_at"]).astimezone()
        assert (local.hour, local.minute) == (23, 59)


async def test_detail_stats_counts_needs_review(no_llm):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        created = await create_assignment(client)
        detail = (await client.get(f"/api/v2/assignments/{created['id']}")).json()
        item_ids = [item["id"] for item in detail["items"]]
        await client.post(
            f"/api/v2/assignments/{created['id']}/submissions",
            json={"items": [{"item_id": item_ids[0], "answer": "只答了一半"}]},
        )
        graded = (await client.get(f"/api/v2/assignments/{created['id']}")).json()
        assert graded["stats"]["needs_review"] >= 1

