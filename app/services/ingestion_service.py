import asyncio
import logging
import re
import uuid
from pathlib import Path

from app.config import get_settings
from app.parsers import NotEnabledError, UnsupportedFormatError, get_parser
from app.parsers.base import PARSER_REGISTRY
from app.rag import lightrag_factory
from app.schemas import DocumentMeta
from app.storage.repository import Repository

logger = logging.getLogger(__name__)

_UPLOAD_EXTS = tuple(
    ext for ext, cls in PARSER_REGISTRY.items() if cls.enabled
)

# 页码 / 页眉页脚类噪音行，建库前剔除（如 "- 12 -"、"第 3 页"、"12/45"）
_NOISE_LINE = re.compile(
    r"^[-—–_=·\s]*(第\s*\d+\s*页|\d{1,4}\s*/\s*\d{1,4}|[-—–_]*\s*\d{1,4}\s*[-—–_]*)$"
)


class FileTooLargeError(Exception):
    def __init__(self, size_mb: float, max_mb: int):
        super().__init__(f"文件大小 {size_mb:.1f}MB 超过限制 {max_mb}MB")
        self.size_mb = size_mb
        self.max_mb = max_mb


def clean_text(text: str) -> str:
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _NOISE_LINE.match(line.strip()):
            continue
        lines.append(line.rstrip())
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return out.strip() + "\n"


def _repair_filename(name: str) -> str:
    """修复 Windows 客户端（curl/PowerShell）以 GBK 发送、被按 latin-1 解码的文件名。
    浏览器上传的 UTF-8 文件名含非 latin-1 字符，encode 必然失败，原样返回。"""
    try:
        return name.encode("latin-1").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


class IngestionService:
    def __init__(self, repo: Repository, data_dir: Path):
        self._repo = repo
        self._uploads = data_dir / "uploads"
        self._parsed = data_dir / "parsed"
        self._uploads.mkdir(parents=True, exist_ok=True)
        self._parsed.mkdir(parents=True, exist_ok=True)
        self._tasks: set[asyncio.Task] = set()
        self._ingest_lock = asyncio.Lock()

    # ----- 上传 -----

    async def save_upload(self, filename: str, content: bytes) -> DocumentMeta:
        filename = _repair_filename(filename)
        ext = Path(filename).suffix.lower()
        if ext not in _UPLOAD_EXTS:
            raise UnsupportedFormatError(
                f"不支持的文件格式：{ext or '（无扩展名）'}，当前支持 {' / '.join(_UPLOAD_EXTS)}"
            )
        max_bytes = get_settings().UPLOAD_MAX_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise FileTooLargeError(len(content) / 1024 / 1024, get_settings().UPLOAD_MAX_MB)

        doc_id = f"d_{uuid.uuid4().hex[:8]}"
        safe_name = f"{doc_id}{ext}"
        raw_path = self._uploads / safe_name
        raw_path.write_bytes(content)

        meta = DocumentMeta(
            doc_id=doc_id,
            filename=filename,
            safe_name=safe_name,
            ext=ext,
            size_bytes=len(content),
            parser=type(get_parser(filename)).__name__,
            status="pending",
            raw_path=str(raw_path),
        )
        await self._repo.upsert_document(meta)
        return meta

    # ----- 建库流水线 -----

    def schedule_ingest(self, doc_id: str) -> None:
        task = asyncio.create_task(self.ingest(doc_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def ingest(self, doc_id: str) -> None:
        meta = await self._find(doc_id)
        if meta is None:
            logger.warning("ingest: 文档 %s 不存在", doc_id)
            return
        # 串行建库：LightRAG 忙时会"入队即返回"，并发 ainsert 会导致状态误判并触发 API 限流
        async with self._ingest_lock:
            try:
                markdown, parsed_path = await self._ensure_parsed(meta)
                await self._repo.set_document_status(
                    doc_id, "parsed", parsed_path=str(parsed_path), error=None
                )
                cleaned = clean_text(markdown)
                if not cleaned.strip():
                    raise RuntimeError("文档解析后内容为空，无法建库")
                await lightrag_factory.ainsert_text(cleaned, doc_id, meta.filename)
                status = await lightrag_factory.get_doc_status(doc_id)
                if status is None:
                    raise RuntimeError("文档内容与知识库中已有文档重复，未重复建库")
                if status.get("status") != "processed":
                    raise RuntimeError(str(status.get("error") or "建库未完成"))
                chunk_count = int(status.get("chunks_count") or 0)
                await self._repo.set_document_status(
                    doc_id, "indexed", chunk_count=chunk_count, error=None
                )
                logger.info(
                    "文档 %s（%s）建库完成，chunk_count=%d", doc_id, meta.filename, chunk_count
                )
            except (NotEnabledError, UnsupportedFormatError) as exc:
                logger.warning("文档 %s 格式未启用：%s", doc_id, exc)
                await self._repo.set_document_status(doc_id, "unsupported", error=str(exc))
            except Exception as exc:
                logger.exception("文档 %s（%s）建库失败", doc_id, meta.filename)
                await self._repo.set_document_status(
                    doc_id, "failed", error=str(exc) or type(exc).__name__
                )

    async def _ensure_parsed(self, meta: DocumentMeta) -> tuple[str, Path]:
        """优先复用 data/parsed/{doc_id}.md 缓存；缺失则重新解析并写缓存。"""
        cache = self._parsed / f"{meta.doc_id}.md"
        if cache.exists():
            return cache.read_text(encoding="utf-8"), cache
        parser = get_parser(meta.filename)
        parsed = await parser.parse(Path(meta.raw_path))
        cache.write_text(parsed.markdown, encoding="utf-8")
        return parsed.markdown, cache

    # ----- 重建 / 删除 -----

    async def reindex(self, doc_id: str) -> None:
        meta = await self._find(doc_id)
        if meta is None:
            raise KeyError(doc_id)
        # 先移除旧图谱数据，否则未变更的内容会被 LightRAG 去重拒收
        try:
            await lightrag_factory.adelete_document(doc_id)
        except Exception:
            logger.warning("文档 %s 旧图谱数据删除失败，将直接重建", doc_id, exc_info=True)
        await self._repo.set_document_status(doc_id, "pending", error=None)
        self.schedule_ingest(doc_id)

    async def delete(self, doc_id: str) -> None:
        meta = await self._find(doc_id)
        if meta is None:
            raise KeyError(doc_id)
        try:
            await lightrag_factory.adelete_document(doc_id)
        except Exception:
            logger.warning("文档 %s 的图谱数据删除失败", doc_id, exc_info=True)
        for p in (meta.raw_path, meta.parsed_path):
            if p and Path(p).exists():
                Path(p).unlink()
        await self._repo.delete_document(doc_id)

    async def _find(self, doc_id: str) -> DocumentMeta | None:
        for meta in await self._repo.list_documents():
            if meta.doc_id == doc_id:
                return meta
        return None

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()


_service: IngestionService | None = None


def init_ingestion_service(repo: Repository, data_dir: Path) -> IngestionService:
    global _service
    _service = IngestionService(repo, data_dir)
    return _service


def get_ingestion_service() -> IngestionService:
    if _service is None:
        raise RuntimeError("IngestionService 尚未初始化")
    return _service
