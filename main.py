import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.agent import router as agent_router
from app.api.approval import router as approval_router
from app.api.documents import router as documents_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.rag import router as rag_router
from app.api.sessions import router as sessions_router
from app.agent.builder import build_agent, close_checkpointer, open_checkpointer
from app.agent.tools import create_registry
from app.config import get_settings
from app.rag import lightrag_factory
from app.services.agent_service import get_agent_service, init_agent_service
from app.services.ingestion_service import get_ingestion_service, init_ingestion_service
from app.services.rag_service import get_rag_service, init_rag_service
from app.storage.sqlite_repo import get_repo, init_repo

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = init_repo(DATA_DIR / "app.db")
    await repo.init()
    init_ingestion_service(repo, DATA_DIR)
    init_rag_service(repo)
    try:
        await lightrag_factory.init_lightrag()
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "LightRAG 初始化失败，知识库功能暂不可用：%s", exc
        )
    try:
        await open_checkpointer()
        init_agent_service(repo, build_agent(create_registry(get_rag_service())))
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Agent 初始化失败，智能体功能暂不可用：%s", exc
        )
    yield
    await get_ingestion_service().close()
    await close_checkpointer()
    await lightrag_factory.close_lightrag()
    await repo.close()


app = FastAPI(title="计算机网络课程智能问答系统", lifespan=lifespan)
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(graph_router)
app.include_router(rag_router)
app.include_router(agent_router)
app.include_router(approval_router)
app.include_router(sessions_router)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT)
