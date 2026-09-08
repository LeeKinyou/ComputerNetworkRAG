from pathlib import Path

from app.parsers.base import BaseParser, NotEnabledError, ParsedDocument, register


@register
class PdfParser(BaseParser):
    extensions = [".pdf"]
    enabled = False

    async def parse(self, file_path: Path) -> ParsedDocument:
        raise NotEnabledError("PDF 解析为 P1 预留接口，尚未启用；请先转换为 md/txt/docx")
