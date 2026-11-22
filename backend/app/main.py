"""单进程入口：API + 内嵌执行 + 前端静态托管（单端口 8000）。"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import asyncio

# psycopg 的异步连接不支持 Windows 默认的 ProactorEventLoop；
# 用 PostgreSQL 检查点时必须切到 Selector 事件循环（Linux 上无影响）。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app import agent
from app.api import router
from app.auth import current_account
from app.config import STATIC_DIR, settings
from app.db import SessionFactory, init_db, shutdown_db
from app.retrieval import retriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("cnrag")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("starting: db=%s llm_ready=%s", settings.db_backend, settings.llm_ready)
    await init_db()
    async with SessionFactory() as session:
        await retriever.refresh(session)
    logger.info(
        "retriever ready: %s chunks, vector=%s (%s)",
        len(retriever._records),
        retriever.vector_mode,
        retriever.embedder_label,
    )

    if settings.checkpoint_backend.lower() == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        checkpoint_cm = AsyncPostgresSaver.from_conn_string(settings.checkpoint_dsn)
        checkpointer = await checkpoint_cm.__aenter__()
        await checkpointer.setup()
        agent.bind_checkpointer(checkpointer)
        # 只打印 host/db，避免把凭据写进日志
        logger.info("checkpoint ready: postgres @%s", settings.checkpoint_dsn.split("@")[-1])
    else:
        checkpoint_path = settings.resolve_path(settings.checkpoint_sqlite_path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_cm = AsyncSqliteSaver.from_conn_string(str(checkpoint_path))
        checkpointer = await checkpoint_cm.__aenter__()
        await checkpointer.setup()
        agent.bind_checkpointer(checkpointer)
        logger.info("checkpoint ready: %s", checkpoint_path)
    try:
        yield
    finally:
        await checkpoint_cm.__aexit__(None, None, None)
        await shutdown_db()


app = FastAPI(
    title="智网系统",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.exception_handler(FastAPIHTTPException)
async def http_error_handler(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        body = {"error": {**detail, "request_id": request.headers.get("x-request-id", "")}}
    else:
        body = {"error": {"code": "HTTP_ERROR", "message": str(detail), "request_id": ""}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    from uuid import uuid4

    request_id = request.headers.get("x-request-id") or str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# 登录后才有权访问的接口；其余 /api 一律要求会话
AUTH_PUBLIC_PATHS = {
    "/api/v2/auth/login",
    "/api/v2/auth/me",
    "/api/v2/auth/logout",
    "/api/v2/health",
    "/api/docs",
    "/api/openapi.json",
    "/api/redoc",
}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not settings.auth_enabled:
        return await call_next(request)
    path = request.url.path
    if not path.startswith("/api/") or path in AUTH_PUBLIC_PATHS:
        return await call_next(request)
    account = current_account(request)
    if account is None:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "UNAUTHORIZED", "message": "请先登录"}},
        )
    # 学生不得借 query 参数读别人的数据；教师可指定 student 的 user_key
    if account.role != "teacher":
        requested = request.query_params.get("user_key")
        if requested and requested != account.user_key:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "FORBIDDEN", "message": "只能访问自己的数据"}},
            )
    return await call_next(request)


app.include_router(router)

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

MEDIA_DIR = STATIC_DIR.parent / "media"
if MEDIA_DIR.exists():
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{path:path}")
async def spa_fallback(path: str):
    if path.startswith("api/"):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "接口不存在"}},
        )
    static_root = STATIC_DIR.resolve()
    candidate = (STATIC_DIR / path).resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        # 编码后的点段可能绕过客户端归一化，这里按解析后的真实路径收口
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "资源不存在"}},
        )
    if candidate.is_file():
        return FileResponse(candidate)
    if (static_root / "index.html").exists():
        return FileResponse(static_root / "index.html")
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "STATIC_NOT_BUILT", "message": "前端尚未构建，请先运行 npm run build"}},
    )


if __name__ == "__main__":
    import uvicorn

    # 不用 uvicorn.run()：它在 Windows 上会在内部重建 ProactorEventLoop，
    # 导致 psycopg 的异步检查点连接失败。这里自己建 loop 再交给 Server。
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=8000, reload=False)
    config.load()
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
