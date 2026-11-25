"""鉴权契约：登录、角色隔离、越权拦截与退出。

默认测试环境关闭鉴权（见 conftest.py），这里显式打开并还原，
用 httpx 的 cookie jar 模拟真实浏览器会话。
"""

from __future__ import annotations

import pytest

from app.config import settings
from _support import api_harness, seed_course

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


async def login(client, username: str, password: str):
    return await client.post("/api/v2/auth/login", json={"username": username, "password": password})


async def test_anonymous_is_rejected(auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        response = await client.get("/api/v2/learning/next", params={"user_key": "demo_user"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"

        # 健康检查与登录接口保持开放
        assert (await client.get("/api/v2/health")).status_code == 200
        me = await client.get("/api/v2/auth/me")
        assert me.status_code == 200
        assert me.json()["authenticated"] is False


async def test_bad_password_is_rejected(auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        response = await login(client, "demo_user", "wrong")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_student_sees_only_self(auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        assert (await login(client, "stu_lin", "lin-pass")).status_code == 200

        me = (await client.get("/api/v2/auth/me")).json()
        assert me["user"]["username"] == "stu_lin"
        assert me["user"]["role"] == "student"
        assert me["user"]["user_key"] == "stu_lin"
        # 库里没有账号资料时，展示名回退到 user_key
        assert me["user"]["display_name"] == "stu_lin"

        # 不传 user_key：按当前身份落到 stu_lin
        own = await client.get("/api/v2/learning/next")
        assert own.status_code == 200
        assert own.json()["user_key"] == "stu_lin"

        # 显式要看 demo_user：拦下
        other = await client.get("/api/v2/learning/next", params={"user_key": "demo_user"})
        assert other.status_code == 403
        assert other.json()["error"]["code"] == "FORBIDDEN"


async def test_student_cannot_write_as_someone_else(auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await login(client, "stu_lin", "lin-pass")

        payload = {"course_id": "course_cn", "title": "冒名会话", "user_key": "demo_user"}
        response = await client.post("/api/v2/chat-sessions", json=payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

        # 不带 user_key 时绑定到自己
        ok = await client.post("/api/v2/chat-sessions", json={"course_id": "course_cn", "title": "自己的会话"})
        assert ok.status_code == 201


async def test_teacher_can_switch_students(auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        assert (await login(client, "teacher", "teach-pass")).status_code == 200

        me = (await client.get("/api/v2/auth/me")).json()
        assert me["user"]["role"] == "teacher"

        for key in ("demo_user", "stu_lin"):
            response = await client.get("/api/v2/learning/next", params={"user_key": key})
            assert response.status_code == 200
            assert response.json()["user_key"] == key


async def test_teacher_only_endpoint_rejects_student(auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await login(client, "stu_lin", "lin-pass")
        assert (await client.get("/api/v2/analytics/students")).status_code == 403

        await client.post("/api/v2/auth/logout")
        await login(client, "teacher", "teach-pass")
        assert (await client.get("/api/v2/analytics/students")).status_code == 200


async def test_logout_invalidates_session(auth_on):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        await login(client, "demo_user", "demo-pass")
        assert (await client.get("/api/v2/learning/next")).status_code == 200

        assert (await client.post("/api/v2/auth/logout")).status_code == 200
        assert (await client.get("/api/v2/learning/next")).status_code == 401
