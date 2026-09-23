import logging

from fastapi import APIRouter

from app.api.common import error_response as _error
from app.services import path_service
from app.storage.sqlite_repo import get_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["path"])


@router.get("/path")
async def path(chapter: int = 0, limit: int = path_service.DEFAULT_TOP_N):
    """章节知识点 DAG（09 §3.4）。chapter=0 即"全部"，每章各取前 limit 个。"""
    return await path_service.get_path(get_repo(), chapter=chapter or None, limit=limit)


@router.get("/path/plan")
async def path_plan(target: str = ""):
    """到目标知识点的必修链，拓扑有序且章号单调不减（09 §3.4）。"""
    try:
        return await path_service.plan(get_repo(), target.strip())
    except KeyError:
        return _error(404, "PATH_TARGET_NOT_FOUND", "目标知识点不在物化快照中，请先运行构建脚本")
