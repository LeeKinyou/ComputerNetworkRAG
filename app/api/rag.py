import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.api.common import error_response
from app.schemas import RAGChatRequest
from app.services.rag_service import get_rag_service, validate_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rag"])


@router.post("/rag/chat")
async def rag_chat(body: RAGChatRequest):
    try:
        validate_question(body.question)
    except ValueError as exc:
        return error_response(422, "QUESTION_TOO_SHORT", str(exc))

    service = get_rag_service()

    async def stream():
        try:
            async for ev in service.stream_answer(body.question, body.mode, body.session_id):
                yield {"event": ev.name, "data": json.dumps(ev.data, ensure_ascii=False)}
        finally:
            logger.info("RAG 流结束 session=%s", body.session_id)

    return EventSourceResponse(stream())
