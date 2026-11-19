"""单进程入口：API + 内嵌执行 + 前端静态托管（单端口 8000）。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app import agent
from app.api import router
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
    title="CNRAG 计算机网络智能助教",
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


app.include_router(router)

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


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
    candidate = STATIC_DIR / path
    if candidate.is_file():
        return FileResponse(candidate)
    if (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "STATIC_NOT_BUILT", "message": "前端尚未构建，请先运行 npm run build"}},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
