from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.services import screen_service
from app.storage.sqlite_repo import get_repo

router = APIRouter()

SCREEN_HTML = Path(__file__).resolve().parents[2] / "static" / "screen.html"


@router.get("/screen", include_in_schema=False)
async def screen_page() -> FileResponse:
    """数据大屏独立入口（09 §2.2）。普通路由，注册须早于 StaticFiles("/") 兜底。"""
    return FileResponse(SCREEN_HTML, media_type="text/html")


@router.get("/api/screen/overview", tags=["screen"])
async def screen_overview():
    """大屏一次性聚合数据（09 §2.4 / Task 5.7）：十个字段，单字段失败只降级自己。"""
    return await screen_service.overview(get_repo())
