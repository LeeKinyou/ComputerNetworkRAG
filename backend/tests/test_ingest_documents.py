"""文档解析与入库契约：格式分派、编码回退、分块上限与错误码。

docx/pptx 在内存中现造现解析，不依赖仓库外素材；PDF 只验证失败归一化。
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import func, select

from app.ingest import (
    MAX_CHARS,
    OVERLAP_CHARS,
    IngestError,
    Section,
    chunk_sections,
    ingest_document,
    parse_document,
)
from app.models import Chunk, Course, Document
from app.seed import COURSE_ID
from _support import memory_db


def md_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def build_docx() -> bytes:
    from docx import Document as DocxDocument

    document = DocxDocument()
    document.add_heading("第 4 章 网络层", level=1)
    document.add_paragraph("IPv4 提供无连接的分组交付服务。")
    document.add_heading("4.3 IPv4", level=2)
    document.add_paragraph("地址由网络位与主机位组成，掩码决定边界。")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_pptx() -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    for index, text in enumerate(("第 4 章 网络层", "IPv4 与子网划分"), start=1):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
        box.text_frame.text = f"{text}（第 {index} 页）"
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_markdown_sections_keep_heading_hierarchy():
    sections = parse_document(
        "lesson.md",
        md_bytes("# 第 4 章\n\nIPv4 无连接。\n\n## 4.3 IPv4\n\n掩码决定边界。\n\n### 4.3.1 子网\n\n块大小决定范围。"),
    )
    assert [section.section_path for section in sections] == [
        ["第 4 章"],
        ["第 4 章", "4.3 IPv4"],
        ["第 4 章", "4.3 IPv4", "4.3.1 子网"],
    ]


def test_gb18030_text_falls_back_after_utf8():
    sections = parse_document("note.txt", "中文讲义：三次握手".encode("gb18030"))
    assert sections[0].text == "中文讲义：三次握手"


def test_legacy_ppt_is_rejected_with_actionable_code():
    with pytest.raises(IngestError) as info:
        parse_document("old.ppt", b"binary")
    assert info.value.code == "UNSUPPORTED_FILE_TYPE"
    assert "pptx" in info.value.message


def test_docx_headings_and_body_are_split():
    sections = parse_document("chapter.docx", build_docx())
    assert [section.section_path for section in sections] == [
        ["第 4 章 网络层"],
        ["第 4 章 网络层", "4.3 IPv4"],
    ]
    assert "无连接" in sections[0].text
    assert "掩码" in sections[1].text


def test_pptx_pages_follow_slide_numbers():
    sections = parse_document("slides.pptx", build_pptx())
    assert [section.page for section in sections] == [1, 2]
    assert all(section.section_path == [] for section in sections)
    assert "第 1 页" in sections[0].text


def test_corrupted_pdf_is_normalized_to_ingest_error():
    with pytest.raises(IngestError) as info:
        parse_document("bad.pdf", b"not a real pdf")
    assert info.value.code == "DOCUMENT_PARSE_FAILED"


def test_chunk_sections_splits_oversize_paragraph_with_overlap():
    text = "网络层负责分组转发。" * 250  # 2500 字，单段超上限
    chunks = chunk_sections([Section(section_path=[], page=None, text=text)])
    assert len(chunks) == 3
    assert all(len(item[2]) <= MAX_CHARS for item in chunks)
    assert chunks[1][2].startswith(text[MAX_CHARS - OVERLAP_CHARS : MAX_CHARS])


def test_chunk_sections_skips_blank_sections():
    assert chunk_sections([Section(section_path=["空"], page=None, text="\n \n")]) == []


async def test_ingest_markdown_persists_document_and_ordered_chunks():
    body = ("# 第 4 章 网络层\n\n" + "IPv4 地址由网络位与主机位组成。" * 40 + "\n\n## 4.4 子网\n\n"
            + "块大小决定网络地址与广播地址。" * 40)
    async with memory_db() as factory:
        async with factory() as session:
            session.add(Course(id=COURSE_ID, title="计算机网络", description=""))
            await session.commit()

            document = await ingest_document(
                session,
                course_id=COURSE_ID,
                chapter_id="ch2",
                title="",
                filename="lesson.md",
                data=md_bytes(body),
                max_bytes=10 * 1024 * 1024,
            )

            assert document.title == "lesson.md"
            assert document.status == "ready"
            assert document.mime == "text/markdown"
            assert document.size == len(md_bytes(body))
            assert document.chunk_count >= 2

            chunks = (
                await session.execute(
                    select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.ordinal)
                )
            ).scalars().all()
            assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
            assert all(chunk.text for chunk in chunks)
            assert chunks[0].section_path == ["第 4 章 网络层"]


async def test_ingest_flushes_document_before_chunks_with_foreign_keys():
    """生产连接开启了外键：同一事务里必须先落文档行，再插分块。"""
    body = "# 第 4 章\n\n" + "网络层负责分组转发与路由选择。" * 80
    async with memory_db(foreign_keys=True) as factory:
        async with factory() as session:
            session.add(Course(id=COURSE_ID, title="计算机网络", description=""))
            await session.commit()

            document = await ingest_document(
                session,
                course_id=COURSE_ID,
                chapter_id=None,
                title="讲义",
                filename="lesson.md",
                data=md_bytes(body),
                max_bytes=1024 * 1024,
            )

            chunks = (
                await session.execute(select(Chunk).where(Chunk.document_id == document.id))
            ).scalars().all()
            assert len(chunks) == document.chunk_count >= 1


@pytest.mark.parametrize(
    "data, max_bytes, code, message_part",
    [
        (b"", 1024, "VALIDATION_ERROR", "为空"),
        (b"x" * 20, 10, "FILE_TOO_LARGE", "上限"),
        (b"binary", 1024, "UNSUPPORTED_FILE_TYPE", "格式"),
    ],
    ids=["empty", "oversize", "unsupported"],
)
async def test_ingest_rejects_bad_input_without_writing_rows(data: bytes, max_bytes: int, code: str, message_part: str):
    filename = "note.txt" if code != "UNSUPPORTED_FILE_TYPE" else "slides.key"
    async with memory_db() as factory:
        async with factory() as session:
            session.add(Course(id=COURSE_ID, title="计算机网络", description=""))
            await session.commit()

            with pytest.raises(IngestError) as info:
                await ingest_document(
                    session,
                    course_id=COURSE_ID,
                    chapter_id=None,
                    title="讲义",
                    filename=filename,
                    data=data,
                    max_bytes=max_bytes,
                )
            assert info.value.code == code
            assert message_part in info.value.message

            documents = await session.scalar(select(func.count(Document.id)))
            chunks = await session.scalar(select(func.count(Chunk.id)))
            assert (documents, chunks) == (0, 0)
