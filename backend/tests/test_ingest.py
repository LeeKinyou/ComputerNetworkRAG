import pytest

from app.ingest import MAX_CHARS, OVERLAP_CHARS, Section, chunk_sections, parse_document


def test_markdown_sections_follow_headings():
    text = (
        "# 第 4 章 网络层\n\n"
        "IPv4 提供无连接的分组交付服务。\n\n"
        "## 4.3 IPv4\n\n"
        "地址由网络位与主机位组成，掩码决定边界。\n"
    )
    sections = parse_document("lesson.md", text.encode("utf-8"))
    assert [section.section_path for section in sections] == [
        ["第 4 章 网络层"],
        ["第 4 章 网络层", "4.3 IPv4"],
    ]
    assert "无连接" in sections[0].text
    assert "掩码" in sections[1].text


def test_plain_text_becomes_single_section():
    sections = parse_document("note.txt", b"TCP uses a three-way handshake.")
    assert len(sections) == 1
    assert sections[0].section_path == []
    assert sections[0].page is None


def test_unsupported_extension_is_rejected():
    with pytest.raises(Exception) as info:
        parse_document("slides.key", b"binary")
    assert getattr(info.value, "code", "") == "UNSUPPORTED_FILE_TYPE"


def test_legacy_office_formats_are_rejected():
    with pytest.raises(Exception) as info:
        parse_document("old.doc", b"binary")
    assert getattr(info.value, "code", "") == "UNSUPPORTED_FILE_TYPE"


def test_chunk_sections_keeps_max_chars_and_overlap():
    paragraphs = [f"第{index}段：" + "网络层负责分组转发与路由选择。" * 12 for index in range(14)]
    sections = [Section(section_path=["第 4 章"], page=None, text="\n".join(paragraphs))]

    chunks = chunk_sections(sections)

    assert len(chunks) >= 2
    assert all(len(chunk[2]) <= MAX_CHARS for chunk in chunks)
    assert all(chunk[0] == ["第 4 章"] for chunk in chunks)
    # 第二块开头承接上一块的尾部，保证跨块检索不断裂
    assert chunks[0][2][-OVERLAP_CHARS:] in chunks[1][2]
