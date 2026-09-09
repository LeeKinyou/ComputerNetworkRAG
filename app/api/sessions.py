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


@router.get("/sessions/{session_id}/runs/{run_id}")
async def get_session_run(session_id: str, run_id: str):
    """单次运行回放（04 §6.4）：run 概要 + 步骤列表，与实时 SSE 复用同一时间线。"""
    repo = get_repo()
    run = await repo.get_run(run_id)
    if run is None or run.session_id != session_id:
        return error_response(404, "RUN_NOT_FOUND", "运行记录不存在")
    steps = await repo.get_run_steps(run_id)
    return {
        "run": {
            "run_id": run.run_id,
            "question": run.question,
            "final_answer": run.final_answer,
            "status": run.status,
            "steps_count": run.steps_count,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        },
        "steps": [
            {
                "step_no": s.step_no,
                "kind": s.kind,
                "tool_name": s.tool_name,
                "tool_args": s.tool_args,
                "content": s.content,
                "structured": s.structured,
                "status": s.status,
                "elapsed_ms": s.elapsed_ms,
            }
            for s in steps
        ],
    }
