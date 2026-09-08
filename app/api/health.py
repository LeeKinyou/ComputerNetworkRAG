from datetime import datetime

from fastapi import APIRouter

from app import __version__

router = APIRouter()


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "llm": "unknown",
        "time": datetime.now().isoformat(timespec="seconds"),
    }
