import logging

from fastapi import APIRouter

from app.api.documents import _error
from app.services import graph_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
async def graph(keyword: str = "", entity_type: str = "", limit: int = 500):
    try:
        return await graph_service.get_graph(keyword=keyword, entity_type=entity_type, limit=limit)
    except RuntimeError:
        # LightRAG 尚未初始化（如未配置密钥）：返回空图谱，前端显示引导空态
        return {"nodes": [], "edges": [], "types": [], "truncated": False}


@router.get("/graph/entity/{name}")
async def entity_detail(name: str):
    try:
        return await graph_service.get_entity_detail(name)
    except KeyError:
        return _error(404, "ENTITY_NOT_FOUND", "实体不存在")
    except RuntimeError:
        return _error(503, "GRAPH_UNAVAILABLE", "知识库尚未初始化，请先上传课程材料")
