from pathlib import Path

from app.parsers.base import BaseParser, NotEnabledError, ParsedDocument, register


@register
class PptxParser(BaseParser):
    extensions = [".pptx"]
    enabled = False

    async def parse(self, file_path: Path) -> ParsedDocument:
        raise NotEnabledError("PPTX 解析为 P1 预留接口，尚未启用；请先转换为 md/txt/docx")
