from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.config import get_settings
from app.storage.sqlite_repo import get_repo, init_repo

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = init_repo(DATA_DIR / "app.db")
    await repo.init()
    yield
    await repo.close()


app = FastAPI(title="计算机网络课程智能问答系统", lifespan=lifespan)
app.include_router(health_router)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT)
