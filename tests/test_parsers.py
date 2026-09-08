from pathlib import Path

import pytest
from docx import Document

from app.parsers import get_parser
from app.parsers.base import NotEnabledError, UnsupportedFormatError

MD_SAMPLE = """# 第5章 传输层

传输层提供**端到端**的通信服务。

## 5.1 UDP 协议

UDP 是无连接的传输层协议，首部仅 8 字节。
"""


def _make_sample_docx(path: Path) -> None:
    doc = Document()
    doc.add_heading("第4章 网络层", level=1)
    doc.add_paragraph("网络层负责分组转发与路由选择。")
    doc.add_heading("4.1 IPv4 编址", level=2)
    doc.add_paragraph("CIDR 记法形如 192.168.1.0/24。")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "前缀长度"
    table.rows[0].cells[1].text = "可用主机数"
    table.rows[1].cells[0].text = "/24"
    table.rows[1].cells[1].text = "254"
    doc.save(str(path))


async def test_text_parser_md(tmp_path):
    f = tmp_path / "第5章-传输层.md"
    f.write_text(MD_SAMPLE, encoding="utf-8")
    parsed = await get_parser(str(f)).parse(f)
    assert parsed.title == "第5章 传输层"
    assert "# 第5章 传输层" in parsed.markdown
    assert "UDP 是无连接的传输层协议" in parsed.markdown


async def test_text_parser_gbk_fallback(tmp_path):
    f = tmp_path / "legacy.txt"
    f.write_bytes("子网掩码与 CIDR 记法。".encode("gbk"))
    parsed = await get_parser(str(f)).parse(f)
    assert "子网掩码与 CIDR 记法" in parsed.markdown


async def test_docx_parser(tmp_path):
    f = tmp_path / "第4章-网络层.docx"
    _make_sample_docx(f)
    parsed = await get_parser(str(f)).parse(f)
    assert parsed.title == "第4章 网络层"
    assert "# 第4章 网络层" in parsed.markdown
    assert "## 4.1 IPv4 编址" in parsed.markdown
    assert "网络层负责分组转发与路由选择。" in parsed.markdown
    # 表格按文档顺序转 markdown，且在第二段之后
    assert "| 前缀长度 | 可用主机数 |" in parsed.markdown
    assert "| /24 | 254 |" in parsed.markdown
    assert parsed.markdown.index("4.1 IPv4 编址") < parsed.markdown.index("前缀长度")
    assert parsed.metadata["tables"] == 1


def test_unsupported_format(tmp_path):
    with pytest.raises(UnsupportedFormatError):
        get_parser("photo.png")


def test_reserved_format_raises_not_enabled(tmp_path):
    f = tmp_path / "slides.pptx"
    f.write_bytes(b"fake")
    with pytest.raises(NotEnabledError):
        import asyncio
        asyncio.run(get_parser(str(f)).parse(f))
