"""文档解析与分块：md / txt / pdf / docx / pptx。

分块目标 600–1000 字，相邻重叠不超过 150 字；优先按标题与段落边界切分。
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document
from app.util import new_id

TARGET_CHARS = 800
MAX_CHARS = 1000
OVERLAP_CHARS = 120

SUPPORTED_MIME = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class IngestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class Section:
    section_path: list[str]
    page: int | None
    text: str


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestError("DOCUMENT_TEXT_UNAVAILABLE", "文件无法解码为文本")


def _parse_markdown(text: str) -> list[Section]:
    sections: list[Section] = []
    path: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            body = "\n".join(buffer).strip()
            if body:
                sections.append(Section(section_path=list(path), page=None, text=body))
            buffer.clear()

    for line in text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            path = path[: level - 1] + [title]
        else:
            buffer.append(line)
    flush()
    return sections


def _parse_pdf(data: bytes) -> list[Section]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pragma: no cover - 解析库异常归一化
        raise IngestError("DOCUMENT_PARSE_FAILED", "PDF 解析失败") from exc

    sections: list[Section] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append(Section(section_path=[], page=index, text=text))
    if not sections:
        raise IngestError(
            "DOCUMENT_TEXT_UNAVAILABLE",
            "PDF 没有可提取的文本层，请先做 OCR 或改用 Word 版本",
        )
    return sections


def _parse_docx(data: bytes) -> list[Section]:
    from docx import Document as DocxDocument

    document = DocxDocument(io.BytesIO(data))
    sections: list[Section] = []
    path: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            body = "\n".join(buffer).strip()
            if body:
                sections.append(Section(section_path=list(path), page=None, text=body))
            buffer.clear()

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower()
        if style.startswith("heading") or style.startswith("标题"):
            flush()
            digits = re.findall(r"\d+", style)
            level = int(digits[0]) if digits else len(path) + 1
            path = path[: max(level - 1, 0)] + [text]
        else:
            buffer.append(text)
    flush()
    if not sections:
        raise IngestError("DOCUMENT_TEXT_UNAVAILABLE", "文档没有可提取的正文")
    return sections


def _parse_pptx(data: bytes) -> list[Section]:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    sections: list[Section] = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                body = (shape.text_frame.text or "").strip()
                if body:
                    texts.append(body)
        if texts:
            sections.append(Section(section_path=[], page=index, text="\n".join(texts)))
    if not sections:
        raise IngestError("DOCUMENT_TEXT_UNAVAILABLE", "演示文稿没有可提取的文本")
    return sections


def parse_document(filename: str, data: bytes) -> list[Section]:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in SUPPORTED_MIME:
        raise IngestError("UNSUPPORTED_FILE_TYPE", f"暂不支持 {suffix or '该'} 格式")
    if suffix in (".md", ".markdown", ".txt"):
        return _parse_markdown(_decode(data))
    if suffix == ".pdf":
        return _parse_pdf(data)
    if suffix in (".docx", ".doc"):
        if suffix == ".doc":
            raise IngestError("UNSUPPORTED_FILE_TYPE", "旧版 .doc 请另存为 .docx 后上传")
        return _parse_docx(data)
    if suffix in (".pptx", ".ppt"):
        if suffix == ".ppt":
            raise IngestError("UNSUPPORTED_FILE_TYPE", "旧版 .ppt 请另存为 .pptx 后上传")
        return _parse_pptx(data)
    raise IngestError("UNSUPPORTED_FILE_TYPE", "暂不支持该格式")


def chunk_sections(sections: list[Section]) -> list[tuple[list[str], int | None, str]]:
    """把 section 内段落合并为 600–1000 字的块，块间保留少量重叠。"""
    chunks: list[tuple[list[str], int | None, str]] = []
    for section in sections:
        paragraphs = [p.strip() for p in re.split(r"\n{1,}", section.text) if p.strip()]
        if not paragraphs:
            continue
        buffer = ""
        for paragraph in paragraphs:
            if len(buffer) + len(paragraph) + 1 <= MAX_CHARS:
                buffer = f"{buffer}\n{paragraph}" if buffer else paragraph
                continue
            if buffer:
                chunks.append((section.section_path, section.page, buffer))
                tail = buffer[-OVERLAP_CHARS:] if len(buffer) > OVERLAP_CHARS else buffer
                buffer = f"{tail}\n{paragraph}" if tail else paragraph
            else:
                buffer = paragraph
            while len(buffer) > MAX_CHARS:
                chunks.append((section.section_path, section.page, buffer[:MAX_CHARS]))
                buffer = buffer[MAX_CHARS - OVERLAP_CHARS :]
        if buffer.strip():
            chunks.append((section.section_path, section.page, buffer.strip()))
    return chunks


async def ingest_document(
    session: AsyncSession,
    *,
    course_id: str,
    chapter_id: str | None,
    title: str,
    filename: str,
    data: bytes,
    max_bytes: int,
) -> Document:
    if len(data) > max_bytes:
        raise IngestError("FILE_TOO_LARGE", f"文件超过 {max_bytes // 1024 // 1024} MiB 上限")
    if not data:
        raise IngestError("VALIDATION_ERROR", "文件内容为空")

    sections = parse_document(filename, data)
    chunks = chunk_sections(sections)
    if not chunks:
        raise IngestError("DOCUMENT_TEXT_UNAVAILABLE", "没有切出有效分块")

    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    document = Document(
        id=new_id(),
        course_id=course_id,
        chapter_id=chapter_id,
        title=title or filename,
        filename=filename,
        mime=SUPPORTED_MIME.get(suffix, "application/octet-stream"),
        size=len(data),
        status="ready",
        chunk_count=len(chunks),
    )
    session.add(document)
    for ordinal, (section_path, page, text) in enumerate(chunks):
        session.add(
            Chunk(
                id=new_id(),
                document_id=document.id,
                ordinal=ordinal,
                section_path=section_path,
                page=page,
                text=text,
            )
        )
    await session.commit()
    return document
