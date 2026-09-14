"""健康检查端点测试：/api/health 廉价探测，check_llm=1 时探测 LLM 连通性。"""

from types import SimpleNamespace

from fastapi import FastAPI

from app.api import health as health_module
from app.api.health import health


def fake_request():
    """端点只用 request.app 读控制台挂载状态，未挂载时 enabled=False。"""
    return SimpleNamespace(app=FastAPI())


async def test_health_without_llm_check_is_cheap():
    data = await health(fake_request(), check_llm=False)
    assert data["status"] == "ok"
    assert data["llm"] == "unknown"
    assert data["version"]
    assert data["time"]
    assert data["console"]["enabled"] is False


async def test_health_llm_ok(monkeypatch):
    async def fake_ping():
        return True, "ok"

    monkeypatch.setattr(health_module, "ping_llm", fake_ping)
    data = await health(fake_request(), check_llm=True)
    assert data["status"] == "ok"
    assert data["llm"] == "ok"


async def test_health_llm_degraded_on_401(monkeypatch):
    async def fake_ping():
        return False, "HTTP 401"

    monkeypatch.setattr(health_module, "ping_llm", fake_ping)
    data = await health(fake_request(), check_llm=True)
    assert data["status"] == "degraded"
    assert data["llm"] == "HTTP 401"


async def test_health_llm_degraded_on_timeout(monkeypatch):
    async def fake_ping():
        return False, "超时"

    monkeypatch.setattr(health_module, "ping_llm", fake_ping)
    data = await health(fake_request(), check_llm=True)
    assert data["status"] == "degraded"
    assert data["llm"] == "超时"


async def test_ping_llm_never_leaks_key_in_detail(monkeypatch):
    class FakeResp:
        status_code = 401

    captured = {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["headers"] = headers
            return FakeResp()

    monkeypatch.setattr(health_module.httpx, "AsyncClient", FakeClient)
    ok, detail = await health_module.ping_llm()
    assert ok is False
    assert detail == "HTTP 401"
    assert "sk-" not in detail
    assert "Authorization" not in detail
