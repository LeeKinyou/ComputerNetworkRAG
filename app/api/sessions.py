import logging

from fastapi import APIRouter

from app.api.common import error_response
from app.storage.sqlite_repo import get_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sessions"])


@router.get("/sessions")
async def list_sessions():
    items = await get_repo().list_sessions()
    return {"items": [s.model_dump() for s in items]}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    repo = get_repo()
    session = next(
        (s for s in await repo.list_sessions() if s.session_id == session_id), None
    )
    if session is None:
        return error_response(404, "SESSION_NOT_FOUND", "会话不存在或已被删除")
    messages = await repo.list_messages(session_id)
    return {
        "session": session.model_dump(),
        "messages": [
            {"role": m.role, "content": m.content, "run_id": m.run_id}
            for m in messages
        ],
    }
