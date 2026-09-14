from datetime import datetime

import httpx
from fastapi import APIRouter, Request

from app import __version__
from app.config import get_settings
from app.rag import lightrag_console

router = APIRouter()

# 供应商偶发慢响应（限速/冷启动）会超过 8s，太短会导致状态点误报琥珀色
PING_TIMEOUT = 15.0


async def ping_llm() -> tuple[bool, str]:
    """轻量连通性探测（max_tokens=1）。错误只返回类别，绝不携带 key/日志 Authorization。"""
    settings = get_settings()
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=PING_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            return True, "ok"
        return False, f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return False, "超时"
    except httpx.HTTPError:
        return False, "网络不可达"


@router.get("/api/health")
async def health(request: Request, check_llm: bool = False):
    llm = "unknown"
    if check_llm:
        ok, detail = await ping_llm()
        llm = "ok" if ok else detail
    return {
        "status": "ok" if llm in ("unknown", "ok") else "degraded",
        "version": __version__,
        "llm": llm,
        "console": lightrag_console.public_info(request.app),
        "time": datetime.now().isoformat(timespec="seconds"),
    }
