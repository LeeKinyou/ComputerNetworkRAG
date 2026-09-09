"""人工审批续跑端点（04 §6.5）：POST /api/agent/runs/{run_id}/resume。

中断时 Checkpointer 已按 thread_id=run_id 持久化图状态，本端点用同一
run_id 以 Command(resume=...) 恢复。响应是新的 SSE 流：首帧 resumed，
后续事件与 /agent/chat 相同，前端追加到原时间线。
"""

import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.api.common import error_response
from app.agent.runner import NoPendingInterruptError
from app.config import get_settings
from app.schemas import ApprovalRequest
from app.services.agent_service import get_agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/agent/runs/{run_id}/resume")
async def agent_resume(run_id: str, body: ApprovalRequest):
    if not get_settings().HITL_ENABLED:
        return error_response(400, "HITL_DISABLED", "人工审批未启用（HITL_ENABLED=false）")
    service = get_agent_service()
    if service.agent is None:
        return error_response(503, "AGENT_NOT_READY", "智能体尚未初始化，请检查 .env 中的 LLM 配置")
    try:
        await service.assert_resumable(run_id)
    except NoPendingInterruptError as exc:
        return error_response(409, "NO_PENDING_INTERRUPT", str(exc))

    async def stream():
        try:
            async for ev in service.stream_resume(run_id, body.decision, body.edited_args):
                yield {"event": ev.name, "data": json.dumps(ev.data, ensure_ascii=False)}
        finally:
            logger.info("Agent 审批续跑流结束 run=%s decision=%s", run_id, body.decision)

    return EventSourceResponse(stream())
