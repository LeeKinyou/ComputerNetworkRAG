"""用户资料与内容隔离契约：姓名来自库里、学生只能看到自己的数据。"""

from __future__ import annotations

import pytest

from app.config import settings
from app.models import User
from _support import add_attempt, api_harness, seed_course

ACCOUNTS = (
    "teacher:teacher:teach-pass;"
    "demo_user:student:demo-pass;"
    "stu_lin:student:lin-pass"
)


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


async def seed_users(factory) -> None:
    async with factory() as session:
        session.add_all(
            [
                User(user_key="teacher", display_name="教师", role="teacher"),
                User(user_key="demo_user", display_name="李金洋", role="student", note="主账号"),
                User(user_key="stu_lin", display_name="林晓", role="student"),
            ]
        )
        await session.commit()


async def login(client, username: str, password: str) -> dict:
    response = await client.post("/api/v2/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


async def logout(client) -> None:
    await client.post("/api/v2/auth/logout")


async def test_login_and_me_return_display_name(auth_on):
    async with api_harness() as (client, factory):
        await seed_users(factory)
        user = await login(client, "demo_user", "demo-pass")
        assert user["display_name"] == "李金洋"
        assert user["note"] == "主账号"

        me = (await client.get("/api/v2/auth/me")).json()
        assert me["user"]["display_name"] == "李金洋"


async def test_users_endpoint_scopes_by_role(auth_on):
    async with api_harness() as (client, factory):
        await seed_users(factory)

        await login(client, "teacher", "teach-pass")
        items = (await client.get("/api/v2/users")).json()["items"]
        assert {"teacher", "demo_user", "stu_lin"} <= {row["user_key"] for row in items}

        await logout(client)
        await login(client, "stu_lin", "lin-pass")
        items = (await client.get("/api/v2/users")).json()["items"]
        assert [row["user_key"] for row in items] == ["stu_lin"]
        assert items[0]["display_name"] == "林晓"


async def test_attempts_and_stats_are_scoped(auth_on):
    async with api_harness() as (client, factory):
        await seed_users(factory)
        await seed_course(factory)
        await add_attempt(
            factory, attempt_id="a1", question_id="q_arp", chapter_id="ch2", correct=True, user_key="demo_user"
        )
        await add_attempt(
            factory, attempt_id="a2", question_id="q_tcp", chapter_id="ch2", correct=False, user_key="stu_lin"
        )

        await login(client, "stu_lin", "lin-pass")
        items = (await client.get("/api/v2/practice/attempts")).json()["items"]
        assert [row["attempt_id"] for row in items] == ["a2"]
        assert (await client.get("/api/v2/practice/stats")).json()["total"] == 1

        # 学生显式索取别人的数据必须被拒
        forbidden = await client.get("/api/v2/practice/attempts?user_key=demo_user")
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "FORBIDDEN"

        # 教师可以指定查看某个学生
        await logout(client)
        await login(client, "teacher", "teach-pass")
        items = (await client.get("/api/v2/practice/attempts?user_key=demo_user")).json()["items"]
        assert [row["attempt_id"] for row in items] == ["a1"]


async def test_analytics_concepts_teacher_sees_class_student_sees_self(auth_on):
    async with api_harness() as (client, factory):
        await seed_users(factory)
        await seed_course(factory)
        await add_attempt(
            factory, attempt_id="a1", question_id="q_arp", chapter_id="ch2", correct=True, user_key="demo_user"
        )
        await add_attempt(
            factory, attempt_id="a2", question_id="q_arp", chapter_id="ch2", correct=False, user_key="stu_lin"
        )

        await login(client, "teacher", "teach-pass")
        teacher_items = (await client.get("/api/v2/analytics/concepts")).json()["items"]
        arp = next(item for item in teacher_items if item["concept_id"] == "c_arp")
        assert arp["attempts"] == 2
        assert arp["students"] == 2

        await logout(client)
        await login(client, "stu_lin", "lin-pass")
        student_items = (await client.get("/api/v2/analytics/concepts")).json()["items"]
        arp = next(item for item in student_items if item["concept_id"] == "c_arp")
        assert arp["attempts"] == 1
        assert arp["students"] == 1
        assert arp["weak_students"] == 1

        # 学生指定别人同样越权
        forbidden = await client.get("/api/v2/analytics/concepts?user_key=demo_user")
        assert forbidden.status_code == 403
