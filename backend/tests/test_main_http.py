"""单进程入口契约：静态托管、SPA 回退、统一错误结构与请求 ID。

这里同时锁住一个安全边界：静态目录之外的文件不能通过路径穿越被读取。
"""

from __future__ import annotations

import re

from app.config import PROJECT_DIR, STATIC_DIR
from app.main import app, spa_fallback
from _support import api_harness


async def test_index_and_spa_routes_serve_frontend():
    async with api_harness() as (client, factory):
        root = await client.get("/")
        assert root.status_code == 200
        assert root.headers["content-type"].startswith("text/html")

        asset = await client.get("/index.html")
        assert asset.status_code == 200

        # 前端路由（非文件）回退到 index.html
        route = await client.get("/practice")
        assert route.status_code == 200
        assert route.headers["content-type"].startswith("text/html")


async def test_unknown_api_route_returns_structured_404():
    async with api_harness() as (client, factory):
        response = await client.get("/api/v2/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_http_error_body_and_request_id_are_consistent():
    async with api_harness() as (client, factory):
        response = await client.get(
            "/api/v2/concepts/missing", headers={"x-request-id": "trace-abc"}
        )
        assert response.status_code == 404
        assert response.json()["error"] == {
            "code": "NOT_FOUND",
            "message": "知识点不存在",
            "request_id": "trace-abc",
        }
        assert response.headers["X-Request-ID"] == "trace-abc"


async def test_request_id_is_generated_when_absent():
    async with api_harness() as (client, factory):
        response = await client.get("/api/v2/health")
        assert response.status_code == 200
        generated = response.headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f-]{36}", generated)


async def test_static_traversal_is_blocked_over_http():
    """`/api` 之外的全部路径都走 SPA 回退，必须限制在 STATIC_DIR 内。

    这里用编码点段尝试读取 backend/pyproject.toml：它是静态目录之外的仓库文件。
    """
    async with api_harness() as (client, factory):
        assert (PROJECT_DIR / "backend" / "pyproject.toml").exists()
        response = await client.get("/%2e%2e/%2e%2e/pyproject.toml")

        assert response.status_code == 404
        assert "cnrag-backend" not in response.text


async def test_spa_fallback_handler_rejects_paths_outside_static_root():
    response = await spa_fallback("../../pyproject.toml")
    assert response.status_code == 404
