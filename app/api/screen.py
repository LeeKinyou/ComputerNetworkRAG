from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

SCREEN_HTML = Path(__file__).resolve().parents[2] / "static" / "screen.html"


@router.get("/screen", include_in_schema=False)
async def screen_page() -> FileResponse:
    """数据大屏独立入口（09 §2.2）。普通路由，注册须早于 StaticFiles("/") 兜底。"""
    return FileResponse(SCREEN_HTML, media_type="text/html")
