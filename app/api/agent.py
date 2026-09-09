import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.api.common import error_response
from app.schemas import AgentChatRequest
from app.services.agent_service import get_agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/agent/chat")
async def agent_chat(body: AgentChatRequest):
    service = get_agent_service()
    if service.agent is None:
        return error_response(503, "AGENT_NOT_READY", "智能体尚未初始化，请检查 .env 中的 LLM 配置")

    async def stream():
        try:
            async for ev in service.stream_chat(body.question, body.session_id):
                yield {"event": ev.name, "data": json.dumps(ev.data, ensure_ascii=False)}
        finally:
            logger.info("Agent 流结束 session=%s", body.session_id)

    return EventSourceResponse(stream())
