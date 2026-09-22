import logging

from fastapi import APIRouter, File, UploadFile

from app.api.common import error_response as _error
from app.parsers import UnsupportedFormatError
from app.services.ingestion_service import FileTooLargeError, get_ingestion_service
from app.services.stats_service import core_stats
from app.storage.sqlite_repo import get_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/upload", status_code=202)
async def upload_document(file: UploadFile = File(...)):
    ingestion = get_ingestion_service()
    content = await file.read()
    try:
        meta = await ingestion.save_upload(file.filename or "", content)
    except UnsupportedFormatError as exc:
        return _error(415, "UNSUPPORTED_FORMAT", str(exc))
    except FileTooLargeError as exc:
        return _error(413, "FILE_TOO_LARGE", str(exc))
    ingestion.schedule_ingest(meta.doc_id)
    return {
        "doc_id": meta.doc_id,
        "filename": meta.filename,
        "ext": meta.ext,
        "status": meta.status,
    }


@router.get("/documents")
async def list_documents():
    docs = await get_repo().list_documents()
    return {"items": [d.model_dump() for d in docs]}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    try:
        await get_ingestion_service().delete(doc_id)
    except KeyError:
        return _error(404, "DOCUMENT_NOT_FOUND", "文档不存在")
    return {"deleted": doc_id}


@router.post("/documents/{doc_id}/reindex", status_code=202)
async def reindex_document(doc_id: str):
    try:
        await get_ingestion_service().reindex(doc_id)
    except KeyError:
        return _error(404, "DOCUMENT_NOT_FOUND", "文档不存在")
    return {"doc_id": doc_id, "status": "pending"}


@router.get("/stats")
async def stats():
    return await core_stats(get_repo())
